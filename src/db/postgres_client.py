import os
import asyncpg
import hashlib
import json
from typing import Optional, List, Any
from datetime import datetime
from dotenv import load_dotenv
from src.logger.crawl_logger import logger
from src.models import CrawlReusltsCustom

load_dotenv()


class PostgresClient:
    """
    PostgreSQL client for managing scraped website data.
    Handles connection pooling and URL existence checks.
    """

    def __init__(
        self,
        postgres_host: str = None,
        posgres_port: str = None,
        posgres_db: str = "crawl_ai",
        postgres_user: str = None,
        posgres_password: str = None,
    ):
        self.pool: Optional[asyncpg.Pool] = None
        # Docker service name 'postgres' is used as hostname within the Docker network
        self.host = os.getenv("POSTGRES_HOST", postgres_host)
        self.port = int(os.getenv("POSTGRES_PORT", posgres_port))
        self.database = os.getenv("POSTGRES_DB", posgres_db)
        self.user = os.getenv("POSTGRES_USER", postgres_user)
        self.password = os.getenv("POSTGRES_PASSWORD", posgres_password)

    async def connect(self):
        """
        Establish connection pool to PostgreSQL database.
        """
        try:
            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=5,
                max_size=10,
            )
            logger.info(
                f"PostgreSQL connection pool established: {self.user}@{self.host}:{self.port}/{self.database}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    async def close(self):
        """
        Close the connection pool.
        """
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def url_exists(self, url: str) -> bool:
        """
        Check if a URL already exists in the scraped_websites table.

        Args:
            url: The URL to check

        Returns:
            bool: True if URL exists, False otherwise
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM scraped_websites WHERE url = $1)",
                    url,
                )
                return result
        except Exception as e:
            logger.error(f"Error checking URL existence for {url}: {e}")
            return False

    async def urls_exist(self, urls: List[str]) -> dict[str, bool]:
        """
        Check multiple URLs for existence in batch.

        Args:
            urls: List of URLs to check

        Returns:
            dict: Set of URLs that exist in the database
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                # Use ANY operator for efficient batch checking
                results = await conn.fetch(
                    "SELECT url FROM scraped_websites WHERE url = ANY($1::text[])",
                    urls,
                )
                existing_urls = {row["url"] for row in results}
                return existing_urls
        except Exception as e:
            logger.error(f"Error checking multiple URLs: {e}")
            return {url: False for url in urls}

    async def get_url_info(self, url: str) -> Optional[dict]:
        """
        Get information about a scraped URL.

        Args:
            url: The URL to look up

        Returns:
            dict: URL information including last_scraped_at, scrape_count, etc.
                  None if URL doesn't exist
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT id, url, title, description, content_hash, 
                           http_status_code, scrape_count, last_scraped_at,
                           created_at, updated_at
                    FROM scraped_websites 
                    WHERE url = $1
                    """,
                    url,
                )
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error fetching URL info for {url}: {e}")
            return None

    async def add_scraped_result(
        self,
        data: CrawlReusltsCustom,
    ) -> Optional[str]:
        """
        Add or update a scraped result in the database.
        If URL exists, increments scrape_count and updates content if changed.

        Args:
            data: CrawlReusltsCustom object containing scraped data

        Returns:
            str: The UUID of the inserted/updated record, None if failed
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        # Calculate content hash from markdown (or cleaned_html if markdown not available)
        content_for_hash = data.markdown or data.cleaned_html or data.html or ""
        content_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()

        try:
            async with self.pool.acquire() as conn:
                # Check if URL already exists
                existing = await conn.fetchrow(
                    "SELECT id, content_hash, scrape_count FROM scraped_websites WHERE url = $1",
                    data.url,
                )

                if existing:
                    # URL exists - check if content changed
                    if existing["content_hash"] == content_hash:
                        logger.info(
                            f"Content unchanged for {data.url}, skipping update"
                        )
                        return str(existing["id"])

                    # Content changed - update record
                    result = await conn.fetchrow(
                        """
                    UPDATE scraped_websites
                    SET html = $2,
                        cleaned_html = $3,
                        markdown = $4,
                        links = $5::jsonb,
                        title = $6,
                        description = $7,
                        author = $8,
                        keywords = $9,
                        content_hash = $10,
                        status_code = $11,
                        response_headers = $12::jsonb,
                        media = $13::jsonb,
                        downloaded_files = $14::jsonb,
                        is_content_useful = $15,
                        formatted_markdown = $16,
                        is_content_pdf = $17,
                        scrape_count = scrape_count + 1,
                        last_scraped_at = CURRENT_TIMESTAMP
                    WHERE url = $1
                    RETURNING id
                    """,
                        data.url,
                        data.html,
                        data.cleaned_html,
                        data.markdown,
                        json.dumps(data.links) if data.links else None,
                        data.title,
                        data.description,
                        data.author,
                        data.keywords,
                        content_hash,
                        data.status_code,
                        (
                            json.dumps(data.response_headers)
                            if data.response_headers
                            else None
                        ),
                        json.dumps(data.media) if data.media else None,
                        (
                            json.dumps(data.downloaded_files)
                            if data.downloaded_files
                            else None
                        ),
                        data.is_content_useful,
                        data.formatted_markdown,
                        data.is_content_pdf,
                    )
                    logger.info(
                        f"Updated scraped result for {data.url} (scrape count: {existing['scrape_count'] + 1})"
                    )
                    return str(result["id"])

                else:
                    # New URL - insert record
                    result = await conn.fetchrow(
                        """
                    INSERT INTO scraped_websites 
                    (url, html, cleaned_html, markdown, links, title, description, 
                     author, keywords, content_hash, status_code, response_headers, media, downloaded_files, is_content_useful, formatted_markdown, is_content_pdf)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb, $14::jsonb, $15, $16, $17)
                    RETURNING id
                    """,
                        data.url,
                        data.html,
                        data.cleaned_html,
                        data.markdown,
                        json.dumps(data.links) if data.links else None,
                        data.title,
                        data.description,
                        data.author,
                        data.keywords,
                        content_hash,
                        data.status_code,
                        (
                            json.dumps(data.response_headers)
                            if data.response_headers
                            else None
                        ),
                        json.dumps(data.media) if data.media else None,
                        (
                            json.dumps(data.downloaded_files)
                            if data.downloaded_files
                            else None
                        ),
                        data.is_content_useful,
                        data.formatted_markdown,
                        data.is_content_pdf,
                    )
                # logger.info(f"Inserted new scraped result for {data.url}")
                return str(result["id"])

        except Exception as e:
            logger.error(f"Error adding/updating scraped result for {data.url}: {e}")
            return None


# Singleton instance
_postgres_client: Optional[PostgresClient] = None


async def get_postgres_client() -> PostgresClient:
    """
    Get or create the singleton PostgreSQL client instance.

    Returns:
        PostgresClient: The initialized client instance
    """
    global _postgres_client
    if _postgres_client is None:
        _postgres_client = PostgresClient()
        await _postgres_client.connect()
    return _postgres_client


async def close_postgres_client():
    """
    Close the singleton PostgreSQL client if it exists.
    """
    global _postgres_client
    if _postgres_client:
        await _postgres_client.close()
        _postgres_client = None
