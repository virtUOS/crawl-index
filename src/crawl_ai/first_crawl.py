import sys

sys.path.append("/app/src")
import os
import re
import asyncio
from typing import List, Optional
import aiohttp
import json
from logger.crawl_logger import logger
from src.db.process_web_content import split_embed_to_db
from src.db.postgres_client import get_postgres_client
from src.config.models import CrawlSettings
from tqdm import tqdm
from src.models import CrawlReusltsCustom
from config.core_config import settings
from src.ragflow.client import ragflow_object
from src.config.core_config import settings
from src.db.postgres_client import close_postgres_client
from crawl4ai import AsyncWebCrawler

# TODO crawler does not process pdf files (they need to be downloaded and processed separately)

QUEUE_MAX_SIZE = 30000
NUM_PROCESS_WORKERS = 2  # Number of concurrent data processing workers
NUM_SCRAPE_WORKERS = 3  # Number of concurrent scraping workers
URL_BATCH_SIZE = 30  # Number of URLs to process in each batchS
CRAWL_API_URL = os.getenv("CRAWL_API_URL", "http://crawl-api:8000") + "/crawlai/crawl"


class CrawlApp:

    def __init__(self, crawl_config: Optional[CrawlSettings] = None):
        # Use provided config or get from settings
        if crawl_config is None:
            from src.config.core_config import settings

            if settings.crawl_settings is None:
                raise ValueError(
                    "No crawl configuration provided and none found in settings"
                )
            crawl_config = settings.crawl_settings

        self.crawl_config = crawl_config
        self.data_queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self.url_queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self.count_visited = 0
        self.count_lock = asyncio.Lock()
        self.over_all_progress_lock = asyncio.Lock()
        self.session = None  # aiohttp session
        self.results = []

    async def worker(self):
        while True:
            # Get the extracted data from the queue
            result_data = await self.data_queue.get()

            if result_data is None:
                self.data_queue.task_done()
                break  # Exit the loop if a sentinel value is received

            # Get PostgreSQL client
            pg_client = await get_postgres_client()

            extrated_data = CrawlReusltsCustom(
                url=result_data["url"],
                html=result_data["html"],
                cleaned_html=result_data["cleaned_html"],
                media=result_data["media"],
                downloaded_files=result_data["downloaded_files"],
                markdown=result_data["markdown"]["raw_markdown"],
                title=result_data["metadata"]["title"],
                description=result_data["metadata"]["description"],
                keywords=result_data["metadata"]["keywords"],
                author=result_data["metadata"]["author"],
                status_code=result_data["status_code"],
                links=result_data["links"],
                response_headers=result_data["response_headers"],
            )
            await pg_client.add_scraped_result(extrated_data)

            if not extrated_data.is_content_useful:

                self.data_queue.task_done()
                continue

            if settings.milvus is not None:
                # Chunking, embedding generating, and saving to the vector DB
                await split_embed_to_db(result_data)

            elif settings.ragflow is not None:
                await ragflow_object.process_ragflow(result=extrated_data)

            else:

                raise ValueError("No vector database configuration found")
            # Mark the task as done
            self.data_queue.task_done()

            logger.debug(
                f"Remaining tasks in the (Vector DB) queue: {self.data_queue.qsize()}"
            )

    @staticmethod
    def remove_fragment_from_url(url: str) -> str:
        """
        Remove traditional fragment identifiers (like #section, #top) but preserve SPA routes (like #/path).
        """
        # Pattern to match fragments that are NOT SPA routes (don't start with #/)
        # This matches # followed by anything that doesn't start with /
        pattern = r"#(?!/)[^#]*$"
        return re.sub(pattern, "", url)

    async def crawl_urls_via_api(self, urls: List[str]) -> List[dict]:
        """
        Crawl multiple URLs using the API endpoint.
        Returns a list of crawl results.
        """

        try:

            payload = {
                "urls": urls,
                "browser_config": {
                    "type": "BrowserConfig",
                    "params": {"headless": True},
                },
                "crawler_config": {
                    "type": "CrawlerRunConfig",
                    "params": {
                        "stream": False,
                        "cache_mode": {"type": "CacheMode", "params": "bypass"},
                        "word_count_threshold": 100,
                        "target_elements": settings.crawl_settings.target_elements
                        or [],
                        "scan_full_page": True,
                        "exclude_domains": settings.crawl_settings.exclude_domains
                        or [],
                    },
                },
            }

            async with self.session.post(
                CRAWL_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 200:
                    # Wait for the complete response
                    response_data = await response.json()

                    # Extract results from the response
                    if response_data.get("success") is False:
                        logger.error("Crawl API reported failure: ")
                        return []

                    results = response_data.get("results", [])

                    return results
        except Exception as e:
            logger.error(f"Exception while crawling via API: {e}")
            # retry
            await self.url_queue.put(urls)
            return []

    async def crawl_sequential_worker(
        self,
        over_all_progress: tqdm,
    ):

        while True:

            async with self.count_lock:
                if self.count_visited >= self.crawl_config.max_urls_to_visit:
                    return

            # TODO: add a timeout here to prevent deadlocks
            urls: List = await self.url_queue.get()

            if urls is None:
                self.url_queue.task_done()
                return  # Exit the loop if a sentinel value is received

            found_urls = set()

            # Get PostgreSQL client for URL existence checking
            pg_client = await get_postgres_client()

            # filter out urls that are already in the database
            existing_urls = await pg_client.urls_exist(urls)
            urls = list(set(urls) - existing_urls)

            # Crawl all URLs in this batch via API
            logger.debug(f"Crawling {len(urls)} URLs via API...")

            api_results: List[dict] = await self.crawl_urls_via_api(urls)

            if api_results:
                for api_result in api_results:

                    if api_result["success"]:
                        # prevents race condition on count_visited
                        async with self.count_lock:
                            self.count_visited += 1
                        for link in api_result["links"].get("internal", []):
                            found_urls.add(
                                CrawlApp.remove_fragment_from_url(link["href"])
                            )
                        for link in api_result["links"].get("external", []):
                            if (
                                link["base_domain"]
                                in self.crawl_config.allowed_domains  # Use self.crawl_config
                            ):
                                found_urls.add(
                                    CrawlApp.remove_fragment_from_url(link["href"])
                                )

                        # Put the extracted data into the queue for processing
                        if self.data_queue.full():
                            logger.warning("Data queue is full. Waiting for space...")
                        # await: if queue is full, wait until there is space.
                        await self.data_queue.put(api_result)

                    else:
                        # TODO: handle failed scraping attempts, e.g., log them or retry
                        logger.error(
                            f"[FAIL-SCRAPING] Failed: {api_result.url} - Error: {api_result.error_message}"
                        )

                    async with self.over_all_progress_lock:
                        over_all_progress.update(1)

                if not found_urls:
                    for _ in range(NUM_SCRAPE_WORKERS - 1):
                        await self.url_queue.put(
                            None
                        )  # Send sentinel values to stop workers
                    self.url_queue.task_done()
                    return  # No new URLs found, exit the loop

                if self.url_queue.full():
                    logger.warning("URL queue is full. Waiting for space...")
                # await: if queue is full, wait until there is space.
                found_urls = list(found_urls)
                if len(found_urls) > 100:
                    # crate batches of URL_BATCH_SIZE urls
                    for i in range(0, len(found_urls), URL_BATCH_SIZE):
                        batch = found_urls[i : i + URL_BATCH_SIZE]
                        if batch:
                            await self.url_queue.put(batch)

                else:
                    await self.url_queue.put(found_urls)
                # await self.url_queue.put(list(found_urls))
                logger.debug(
                    f"Remaining tasks in the (URLS) queue: {self.url_queue.qsize()}"
                )
                self.url_queue.task_done()

    async def main(self):
        # Start worker tasks to process data from the queue
        _ = [asyncio.create_task(self.worker()) for _ in range(NUM_PROCESS_WORKERS)]

        # Create aiohttp session
        timeout = aiohttp.ClientTimeout(
            total=300, connect=60, sock_read=300
        )  # 5 min total, 5 min read
        self.session = aiohttp.ClientSession(timeout=timeout)

        try:
            # crawler, crawl_config, session_id = settings.get_crawler()
            # await crawler.start()

            with tqdm(
                total=self.crawl_config.max_urls_to_visit,
                desc="Overall Progress (MAX_URLS)",
            ) as over_all_progress:

                scrape_workers = [
                    asyncio.create_task(
                        self.crawl_sequential_worker(
                            over_all_progress,
                        )
                    )
                    for i in range(NUM_SCRAPE_WORKERS)
                ]

                await self.url_queue.put([self.crawl_config.start_url])
                await asyncio.gather(*scrape_workers, return_exceptions=True)

                await self.data_queue.join()
                logger.info("All data has been processed.")
                for _ in range(NUM_PROCESS_WORKERS):
                    await self.data_queue.put(
                        None
                    )  # Send sentinel values to stop workers

                # await processor_task

                await close_postgres_client()

        except Exception as e:
            logger.error(f"An error occurred during crawling: {e}")
            await close_postgres_client()


if __name__ == "__main__":
    # TODO allow the drop collection argument to be passed via api call
    crawl_app = CrawlApp()  # Drop the old (Vector DB) collection if it exists
    asyncio.run(crawl_app.main())
    print()
