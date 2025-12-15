# Updates the existing crawled data by re-crawling URLs, if url is marked as is_content_useful=False do not scrape again
# Compare the new content hash with the stored one, if different re-scrape and update both postgres and vector db
# If a url has been deleted from the website (404), mark it as is_active=False in Postgres DB and remove from vector db

import sys
import asyncio
import aiohttp
import aiosqlite
import json
from pathlib import Path
import hashlib

sys.path.append("/app/src")

import asyncio
from typing import List, Callable, Optional

# from base import BaseCrawl, DB_PATH
from src.db.postgres_client import get_postgres_client
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from logger.crawl_logger import logger
from src.crawl_ai.utils import CrawlHelperMixin
from src.config.models import ReCrawlSettings

BATCH_SIZE_PAGINATION = 30
NUM_PROCESS_WORKERS = 3
NUM_SCRAPE_WORKERS = 3


class ReCrawlApp(CrawlHelperMixin):

    def __init__(self):
        self.rows_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self.data_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.url_queue: asyncio.Queue = asyncio.Queue(
            maxsize=100
        )  # These urls couldnot be crawled in the first attempt, retry them later

    async def scrape(self, crawl_payload: Optional[dict] = None):

        while True:

            rows: List[dict] = await self.rows_queue.get()

            # Check for sentinel value
            if rows is None:
                self.rows_queue.task_done()
                break

            try:

                urls = [row["url"] for row in rows]
                api_results = await self.crawl_urls_via_api(
                    urls=urls, crawl_payload=crawl_payload
                )

                for result_data in api_results:
                    if result_data.get("success") is False:
                        logger.error(
                            f"Failed to crawl {result_data.get('url')}: {result_data.get('error_message')}"
                        )
                        continue

                    content_for_hash = (
                        result_data["markdown"]["raw_markdown"]
                        or result_data["cleaned_html"]
                        or result_data["html"]
                        or ""
                    )
                    content_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()
                    url = result_data["url"]
                    stored_row = next((row for row in rows if row["url"] == url), None)
                    if not stored_row:
                        continue

                    sotored_raw_content_hash = stored_row[
                        "content_hash"
                    ]  # content_hash column
                    if content_hash != sotored_raw_content_hash:
                        # Content has changed, mark for re-crawl
                        result_data["ragflow_doc_id"] = stored_row[
                            "ragflow_doc_id"
                        ]  # Pass the existing RAGFlow doc ID for update
                        await self.data_queue.put(result_data)
            finally:
                self.rows_queue.task_done()

    async def main(
        self, recrawl_settings: Optional[ReCrawlSettings] = ReCrawlSettings()
    ):

        _crawl_ai_payload = recrawl_settings.crawl_payload
        # Start worker tasks to process data from the queue
        workers = [
            asyncio.create_task(self.worker(update_data=True))
            for _ in range(NUM_PROCESS_WORKERS)
        ]

        # Create aiohttp session
        timeout = aiohttp.ClientTimeout(
            total=300, connect=60, sock_read=300
        )  # 5 min total, 5 min read
        self.session = aiohttp.ClientSession(timeout=timeout)

        pg_client = await get_postgres_client()

        scrapers = [
            asyncio.create_task(self.scrape(_crawl_ai_payload))
            for _ in range(NUM_SCRAPE_WORKERS)
        ]
        total_urls = await pg_client.get_total_url_count(only_useful=True)
        total_batches = (
            total_urls + BATCH_SIZE_PAGINATION - 1
        ) // BATCH_SIZE_PAGINATION

        logger.info(
            f"Processing {total_urls} URLs in {total_batches} batches of {BATCH_SIZE_PAGINATION}"
        )

        for batch_num in range(total_batches):
            offset = batch_num * BATCH_SIZE_PAGINATION
            rows = await pg_client.get_urls_batch(
                limit=BATCH_SIZE_PAGINATION, offset=offset, only_useful=True
            )

            logger.info(
                f"Processing batch {batch_num + 1}/{total_batches} ({len(rows)} URLs)"
            )

            await self.rows_queue.put(rows)

        # Send sentinel values to stop scrapers
        for _ in range(NUM_SCRAPE_WORKERS):
            await self.rows_queue.put(None)

        # Wait for all scraping to complete
        await asyncio.gather(*scrapers)

        # Send sentinel values to stop workers
        for _ in range(NUM_PROCESS_WORKERS):
            await self.data_queue.put(None)

        # Wait for all workers to complete
        await asyncio.gather(*workers)

        # Close session
        await self.session.close()

        logger.info("Re-crawl completed successfully")

    def run(self):
        asyncio.run(self.main())


if __name__ == "__main__":
    re_crawl_app = ReCrawlApp()  # Drop the old (Vector DB) collection if it exists
    asyncio.run(re_crawl_app.main())
    print()
