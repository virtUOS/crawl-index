import asyncio
import sys
import time

import aiohttp
import aiosqlite

# At the beginning of your script
import colorama
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, ProxyConfig
from crawl4ai.async_crawler_strategy import AsyncCrawlResponse
from crawl4ai.async_database import DB_PATH, async_db_manager
from crawl4ai.async_dispatcher import *  # noqa: F403
from crawl4ai.cache_context import CacheContext, CacheMode, _legacy_to_cache_mode
from crawl4ai.chunking_strategy import *  # noqa: F403
from crawl4ai.content_filter_strategy import *  # noqa: F403
from crawl4ai.extraction_strategy import *  # noqa: F403
from crawl4ai.models import (
    CrawlResult,
    CrawlResultContainer,
    MarkdownGenerationResult,
    RunManyReturn,
    StringCompatibleMarkdown,
)
from crawl4ai.utils import create_box_message, get_error_context, sanitize_input_encode

# /root/.crawl4ai/crawl4ai.db   vs code  `code /root/.crawl4ai/`


colorama.init(strip=True)

# This code overrides the arun method of the AsyncWebCrawler class


async def custom_aget_cached_url(self, url: str) -> Optional[CrawlResult]:
    """Modified version of aget_cached_url that adds timestamp to the CrawlResult"""

    async def _get(db):
        async with db.execute(
            "SELECT * FROM crawled_data WHERE url = ?", (url,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

            # Get column names
            columns = [description[0] for description in cursor.description]
            # Create dict from row data
            row_dict = dict(zip(columns, row))

            # Extract timestamp if present (for our content change detection)
            timestamp = row_dict.get("timestamp", 0)

            # Load content from files using stored hashes
            content_fields = {
                "html": row_dict["html"],
                "cleaned_html": row_dict["cleaned_html"],
                "markdown": row_dict["markdown"],
                "extracted_content": row_dict["extracted_content"],
                "screenshot": row_dict["screenshot"],
                "screenshots": row_dict["screenshot"],
            }

            for field, hash_value in content_fields.items():
                if hash_value:
                    content = await self._load_content(
                        hash_value,
                        field.split("_")[0],  # Get content type from field name
                    )
                    row_dict[field] = content or ""
                else:
                    row_dict[field] = ""

            # Parse JSON fields
            json_fields = [
                "media",
                "links",
                "metadata",
                "response_headers",
                "markdown",
            ]
            for field in json_fields:
                try:
                    row_dict[field] = (
                        json.loads(row_dict[field]) if row_dict[field] else {}
                    )
                except json.JSONDecodeError:
                    if field == "markdown" and isinstance(row_dict[field], str):
                        row_dict[field] = MarkdownGenerationResult(
                            raw_markdown=row_dict[field] or "",
                            markdown_with_citations="",
                            references_markdown="",
                            fit_markdown="",
                            fit_html="",
                        )
                    else:
                        row_dict[field] = {}

            if isinstance(row_dict["markdown"], Dict):
                if row_dict["markdown"].get("raw_markdown"):
                    row_dict["markdown"] = row_dict["markdown"]["raw_markdown"]

            # Parse downloaded_files
            try:
                row_dict["downloaded_files"] = (
                    json.loads(row_dict["downloaded_files"])
                    if row_dict["downloaded_files"]
                    else []
                )
            except json.JSONDecodeError:
                row_dict["downloaded_files"] = []

            # Remove any fields not in CrawlResult model
            valid_fields = CrawlResult.__annotations__.keys()
            filtered_dict = {k: v for k, v in row_dict.items() if k in valid_fields}
            filtered_dict["markdown"] = row_dict["markdown"]

            # Create the CrawlResult object
            result = CrawlResult(**filtered_dict)

            # Store timestamp in metadata instead of as a direct attribute
            if not hasattr(result, "metadata") or result.metadata is None:
                result.metadata = {}

            # Add timestamp to metadata
            result.metadata["_timestamp"] = timestamp

            return result

    try:
        return await self.execute_with_retry(_get)
    except Exception as e:
        self.logger.error(
            message="Error retrieving cached URL: {error}",
            tag="ERROR",
            force_verbose=True,
            params={"error": str(e)},
        )
        return None


async def custom_ainit_db(self):
    """Initialize database schema with timestamp column"""
    async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS crawled_data (
                url TEXT PRIMARY KEY,
                html TEXT,
                cleaned_html TEXT,
                markdown TEXT,
                extracted_content TEXT,
                success BOOLEAN,
                media TEXT DEFAULT "{}",
                links TEXT DEFAULT "{}",
                metadata TEXT DEFAULT "{}",
                screenshot TEXT DEFAULT "",
                response_headers TEXT DEFAULT "{}",
                downloaded_files TEXT DEFAULT "{}",
                timestamp REAL DEFAULT 0
            )
        """
        )

        # Check if timestamp column exists, add it if it doesn't
        cursor = await db.execute("PRAGMA table_info(crawled_data)")
        columns = await cursor.fetchall()
        column_names = [column[1] for column in columns]

        if "timestamp" not in column_names:
            await db.execute(
                "ALTER TABLE crawled_data ADD COLUMN timestamp REAL DEFAULT 0"
            )
            self.logger.info(
                message="Added timestamp column to the database", tag="INIT"
            )

        await db.commit()


async def custom_acache_url(self, result: CrawlResult):
    """Modified cache function that adds timestamp"""
    # Store content files and get hashes
    content_map = {
        "html": (result.html, "html"),
        "cleaned_html": (result.cleaned_html or "", "cleaned"),
        "markdown": None,
        "extracted_content": (result.extracted_content or "", "extracted"),
        "screenshot": (result.screenshot or "", "screenshots"),
    }

    # Process markdown content (keeping original logic)
    try:

        if isinstance(result.markdown, StringCompatibleMarkdown):
            content_map["markdown"] = (result.markdown, "markdown")
        elif isinstance(result.markdown, MarkdownGenerationResult):
            content_map["markdown"] = (result.markdown.model_dump_json(), "markdown")
        elif isinstance(result.markdown, str):
            markdown_result = MarkdownGenerationResult(raw_markdown=result.markdown)
            content_map["markdown"] = (markdown_result.model_dump_json(), "markdown")
        else:
            content_map["markdown"] = (
                MarkdownGenerationResult().model_dump_json(),
                "markdown",
            )
    except Exception as e:
        self.logger.warning(
            message=f"Error processing markdown content: {str(e)}", tag="WARNING"
        )
        content_map["markdown"] = (
            MarkdownGenerationResult().model_dump_json(),
            "markdown",
        )

    content_hashes = {}
    for field, (content, content_type) in content_map.items():
        content_hashes[field] = await self._store_content(content, content_type)

    # Add timestamp to the data being saved
    current_timestamp = time.time()

    async def _cache(db):
        await db.execute(
            """
            INSERT INTO crawled_data (
                url, html, cleaned_html, markdown,
                extracted_content, success, media, links, metadata,
                screenshot, response_headers, downloaded_files, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                html = excluded.html,
                cleaned_html = excluded.cleaned_html,
                markdown = excluded.markdown,
                extracted_content = excluded.extracted_content,
                success = excluded.success,
                media = excluded.media,
                links = excluded.links,
                metadata = excluded.metadata,
                screenshot = excluded.screenshot,
                response_headers = excluded.response_headers,
                downloaded_files = excluded.downloaded_files,
                timestamp = excluded.timestamp
        """,
            (
                result.url,
                content_hashes["html"],
                content_hashes["cleaned_html"],
                content_hashes["markdown"],
                content_hashes["extracted_content"],
                result.success,
                json.dumps(result.media),
                json.dumps(result.links),
                json.dumps(result.metadata or {}),
                content_hashes["screenshot"],
                json.dumps(result.response_headers or {}),
                json.dumps(result.downloaded_files or []),
                current_timestamp,
            ),
        )

    try:
        await self.execute_with_retry(_cache)
    except Exception as e:
        self.logger.error(
            message="Error caching URL: {error}",
            tag="ERROR",
            force_verbose=True,
            params={"error": str(e)},
        )


async def _check_content_changed(self, cached_result, url, config):
    """
    Determines if the content at a URL has changed since it was last cached.
    Uses a multi-tiered approach prioritizing low-latency methods.

    Returns:
        bool: True if content has changed (or we can't determine), False if unchanged
    """
    # Skip change detection for certain protocols or configurations
    if url.startswith(("file:", "raw:")) or config.cache_mode == CacheMode.DISABLED:
        return True

    try:
        # Extract cached response metadata
        cached_headers = cached_result.response_headers or {}
        etag = cached_headers.get("etag")
        last_modified = cached_headers.get("last-modified")
        # Get timestamp from metadata
        cached_time = 0
        if hasattr(cached_result, "metadata") and cached_result.metadata:
            cached_time = cached_result.metadata.get("_timestamp", 0)

        # Strategy 1: Use max-age from Cache-Control if available
        cache_control = cached_headers.get("cache-control", "")
        if "max-age=" in cache_control:
            try:
                max_age = int(cache_control.split("max-age=")[1].split(",")[0])
                current_time = time.time()
                if current_time - cached_time < max_age:
                    self.logger.debug(
                        message="Content fresh according to max-age",
                        tag="CACHE",
                        params={"url": url, "max_age": max_age},
                    )
                    return False
            except (ValueError, IndexError):
                pass  # Invalid max-age format, continue to other strategies

        # Strategy 2: Conditional request with ETag/Last-Modified
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        if headers:
            # Use HEAD request with a short timeout to minimize latency
            timeout = aiohttp.ClientTimeout(total=config.head_request_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.head(
                        url, headers=headers, allow_redirects=True
                    ) as response:
                        # 304 Not Modified means content is unchanged
                        if response.status == 304:
                            self.logger.debug(
                                message="Content unchanged (304 Not Modified)",
                                tag="CACHE",
                                params={"url": url},
                            )
                            return False

                        # Check if ETag matches
                        new_etag = response.headers.get("etag")
                        if etag and new_etag and etag == new_etag:
                            self.logger.debug(
                                message="Content unchanged (ETag match)",
                                tag="CACHE",
                                params={"url": url},
                            )
                            return False
                except Exception as e:
                    # If HEAD request fails, fallback to using cache
                    self.logger.warning(
                        message="HEAD request failed, assuming content unchanged",
                        tag="CACHE",
                        params={"url": url, "error": str(e)},
                    )
                    return False

        # Strategy 3: Check default cache TTL
        # If no cache headers or ETag/Last-Modified, check default TTL
        if config.default_cache_ttl_seconds:
            current_time = time.time()
            if current_time - cached_time < config.default_cache_ttl_seconds:
                self.logger.debug(
                    message="Using cached content based on TTL",
                    tag="CACHE",
                    params={"url": url, "ttl": config.default_cache_ttl_seconds},
                )
                return False

        # Default: assume content has changed if we can't prove otherwise
        return True

    except Exception as e:
        self.logger.error(
            message="Error checking content change",
            tag="CACHE",
            params={"url": url, "error": str(e)},
        )
        # On error, assume content has changed to be safe
        return True


async def delete_cached_result(self, db, sql_query):
    await db.execute(sql_query)


async def arun(
    self,
    url: str,
    config: CrawlerRunConfig = None,
    **kwargs,
) -> RunManyReturn:
    """
    Runs the crawler for a single source: URL (web, local file, or raw HTML).

    Migration Guide:
    Old way (deprecated):
        result = await crawler.arun(
            url="https://example.com",
            word_count_threshold=200,
            screenshot=True,
            ...
        )

    New way (recommended):
        config = CrawlerRunConfig(
            word_count_threshold=200,
            screenshot=True,
            ...
        )
        result = await crawler.arun(url="https://example.com", crawler_config=config)

    Args:
        url: The URL to crawl (http://, https://, file://, or raw:)
        crawler_config: Configuration object controlling crawl behavior
        [other parameters maintained for backwards compatibility]

    Returns:
        CrawlResult: The result of crawling and processing
    """
    # Auto-start if not ready
    if not self.ready:
        await self.start()

    config = config or CrawlerRunConfig()
    if not isinstance(url, str) or not url:
        raise ValueError("Invalid URL, make sure the URL is a non-empty string")

    async with self._lock or self.nullcontext():
        try:
            self.logger.verbose = config.verbose

            # Default to ENABLED if no cache mode specified
            if config.cache_mode is None:
                config.cache_mode = CacheMode.ENABLED

            # Create cache context
            cache_context = CacheContext(url, config.cache_mode, False)

            # Initialize processing variables
            async_response: AsyncCrawlResponse = None
            cached_result: CrawlResult = None
            html = None
            content_changed = True
            screenshot_data = None
            pdf_data = None
            extracted_content = None
            start_time = time.perf_counter()

            # Try to get cached result if appropriate
            if cache_context.should_read():
                cached_result = await async_db_manager.aget_cached_url(url)

            if cached_result:

                if config.check_content_changed:
                    # check if content change
                    content_changed = await self._check_content_changed(
                        cached_result, url, config
                    )
                else:
                    content_changed = False

                if not content_changed:
                    # Content has not changed, use cached version
                    html = sanitize_input_encode(cached_result.html)
                    extracted_content = sanitize_input_encode(
                        cached_result.extracted_content or ""
                    )
                    extracted_content = (
                        None
                        if not extracted_content or extracted_content == "[]"
                        else extracted_content
                    )
                    screenshot_data = cached_result.screenshot
                    pdf_data = cached_result.pdf

                    # Check if requested media is missing from cache
                    if (config.screenshot and not screenshot_data) or (
                        config.pdf and not pdf_data
                    ):
                        cached_result = None
                        content_changed = True  # Force recrawl for missing media
                    else:
                        self.logger.url_status(
                            url=cache_context.display_url,
                            success=bool(html),
                            timing=time.perf_counter() - start_time,
                            tag="FETCH-CACHED",
                        )

                else:
                    # Content has changed, invalidate cache
                    sql_query = f"DELETE FROM crawled_data WHERE url = '{url}'"
                    await async_db_manager.execute_with_retry(
                        self.delete_cached_result,
                        sql_query,
                    )
                    cached_result = None
                    self.logger.info(
                        message="Content changed, recrawling",
                        tag="CACHE",
                        params={"url": url},
                    )

            # Update proxy configuration from rotation strategy if available
            if config and config.proxy_rotation_strategy:
                next_proxy: ProxyConfig = (
                    await config.proxy_rotation_strategy.get_next_proxy()
                )
                if next_proxy:
                    self.logger.info(
                        message="Switch proxy: {proxy}",
                        tag="PROXY",
                        params={"proxy": next_proxy.server},
                    )
                    config.proxy_config = next_proxy
                    # config = config.clone(proxy_config=next_proxy)

            # Fetch fresh content if needed
            if (not cached_result or not html) and content_changed:
                t1 = time.perf_counter()

                if config.user_agent:
                    self.crawler_strategy.update_user_agent(config.user_agent)

                # Check robots.txt if enabled
                if config and config.check_robots_txt:
                    if not await self.robots_parser.can_fetch(
                        url, self.browser_config.user_agent
                    ):
                        return CrawlResult(
                            url=url,
                            html="",
                            success=False,
                            status_code=403,
                            error_message="Access denied by robots.txt",
                            response_headers={
                                "X-Robots-Status": "Blocked by robots.txt"
                            },
                        )

                ##############################
                # Call CrawlerStrategy.crawl #
                ##############################
                async_response = await self.crawler_strategy.crawl(
                    url,
                    config=config,  # Pass the entire config object
                )

                html = sanitize_input_encode(async_response.html)
                screenshot_data = async_response.screenshot
                pdf_data = async_response.pdf_data
                js_execution_result = async_response.js_execution_result

                t2 = time.perf_counter()
                self.logger.url_status(
                    url=cache_context.display_url,
                    success=bool(html),
                    timing=t2 - t1,
                    tag="FETCH",
                )

                ###############################################################
                # Process the HTML content, Call CrawlerStrategy.process_html #
                ###############################################################
                crawl_result: CrawlResult = await self.aprocess_html(
                    url=url,
                    html=html,
                    extracted_content=extracted_content,
                    config=config,  # Pass the config object instead of individual parameters
                    screenshot_data=screenshot_data,
                    pdf_data=pdf_data,
                    verbose=config.verbose,
                    is_raw_html=True if url.startswith("raw:") else False,
                    redirected_url=async_response.redirected_url,
                    **kwargs,
                )

                crawl_result.status_code = async_response.status_code
                crawl_result.redirected_url = async_response.redirected_url or url
                crawl_result.response_headers = async_response.response_headers
                crawl_result.downloaded_files = async_response.downloaded_files
                crawl_result.js_execution_result = js_execution_result
                crawl_result.mhtml = async_response.mhtml_data
                crawl_result.ssl_certificate = async_response.ssl_certificate
                # Add captured network and console data if available
                crawl_result.network_requests = async_response.network_requests
                crawl_result.console_messages = async_response.console_messages

                crawl_result.success = bool(html)
                crawl_result.session_id = getattr(config, "session_id", None)

                self.logger.url_status(
                    url=cache_context.display_url,
                    success=crawl_result.success,
                    timing=time.perf_counter() - start_time,
                    tag="COMPLETE",
                )

                # Update cache if appropriate
                if cache_context.should_write() and not bool(cached_result):
                    await async_db_manager.acache_url(crawl_result)

                return CrawlResultContainer(crawl_result)

            else:
                self.logger.url_status(
                    url=cache_context.display_url,
                    success=True,
                    timing=time.perf_counter() - start_time,
                    tag="COMPLETE",
                )
                cached_result.success = bool(html)
                cached_result.session_id = getattr(config, "session_id", None)
                cached_result.redirected_url = cached_result.redirected_url or url
                return CrawlResultContainer(cached_result)

        except Exception as e:
            error_context = get_error_context(sys.exc_info())

            error_message = (
                f"Unexpected error in _crawl_web at line {error_context['line_no']} "
                f"in {error_context['function']} ({error_context['filename']}):\n"
                f"Error: {str(e)}\n\n"
                f"Code context:\n{error_context['code_context']}"
            )

            self.logger.error_status(
                url=url,
                error=error_message,
                tag="ERROR",
            )

            return CrawlResultContainer(
                CrawlResult(
                    url=url, html="", success=False, error_message=error_message
                )
            )


if __name__ == "__main__":
    import asyncio
    import types

    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
    from crawl4ai.deep_crawling import BFSDeepCrawlStrategy

    AsyncWebCrawler.arun = arun
    AsyncWebCrawler.delete_cached_result = delete_cached_result
    AsyncWebCrawler._check_content_changed = _check_content_changed

    # For AsyncDatabaseManager
    async_db_manager.ainit_db = types.MethodType(custom_ainit_db, async_db_manager)
    async_db_manager.acache_url = types.MethodType(custom_acache_url, async_db_manager)
    async_db_manager.aget_cached_url = types.MethodType(
        custom_aget_cached_url, async_db_manager
    )

    CrawlerRunConfig.check_content_changed = True
    CrawlerRunConfig.head_request_timeout = 3.0
    CrawlerRunConfig.default_cache_ttl_seconds = 60 * 60 * 24  # 1 day

    async def main():
        # Configure a 2-level deep crawl
        config = CrawlerRunConfig(
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=7,
                include_external=False,
                max_pages=50,  # Limit to 1000 pages
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            cache_mode=CacheMode.ENABLED,
            target_elements=["main", "div#content"],
            verbose=True,
        )

        async with AsyncWebCrawler() as crawler:
            results = await crawler.arun(
                "https://www.uni-osnabrueck.de/lehren/lehren-ein-ueberblick",
                config=config,
            )

            print(f"Crawled {len(results)} pages in total")

            # Access individual results
            for result in results[:3]:  # Show first 3 results
                print(f"URL: {result.url}")
                print(f"Depth: {result.metadata.get('depth', 0)}")

    asyncio.run(main())
