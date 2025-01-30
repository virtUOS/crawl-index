import sys
import shutil
from pathlib import Path

sys.path.append("/app/src")
import os
import pickle
import asyncio
from typing import List, Callable, Optional
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)
import sqlite3
from crawl4ai.database import init_db
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from db.milvus_main import ProcessEmbedMilvus
from logger.crawl_logger import logger
from config.core_config import settings

# Load settings

START_URL = settings.crawl_settings.start_url
MAX_URLS = settings.crawl_settings.max_urls_to_visit
ALLOWED_DOMAINS = settings.crawl_settings.allowed_domains
EXCLUDE_DOMAINS = settings.crawl_settings.exclude_domains
COLLECTION_NAME = settings.indexing_storage_settings.collection_name
SAVE_TO_PICKLE = settings.indexing_storage_settings.save_to_pickle
SAVE_TO_PICKLE_INTERVAL = settings.indexing_storage_settings.save_to_pickle_interval
# /root/.crawl4ai/crawl4ai.db   vs code  `code code /root/.crawl4ai/`
DB_PATH = os.path.join(os.getenv("CRAWL4_AI_BASE_DIRECTORY", Path.home()), ".crawl4ai")
DB_PATH = os.path.join(DB_PATH, "crawl4ai.db")
QUEUE_MAX_SIZE = 3000

# TODO crawler does not process pdf files (they need to be downloaded and processed separately)


class CrawlApp(ProcessEmbedMilvus):
    def __init__(self):
        logger.debug("\n=== Sequential Crawling with Session Reuse ===")

        super().__init__(collection_name=COLLECTION_NAME)

        init_db()
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()

        self.count_visited = 0
        self.urls = {START_URL}
        self.results = []

        # TODO if self.data_queue is too big, the program will crash (very unlikely)
        self.data_queue = asyncio.Queue(
            maxsize=QUEUE_MAX_SIZE
        )  # Create an async queue for data processing

        browser_config = BrowserConfig(
            headless=True,
            extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
        )

        self.crawl_config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(),
            cache_mode=CacheMode.ENABLED,  # Avoid redundant requests
            scan_full_page=True,  # crawler tryes to scroll the entire page
            scroll_delay=0.5,
            exclude_domains=EXCLUDE_DOMAINS,
        )

        self.crawler = AsyncWebCrawler(config=browser_config)

    def is_url_visited(self, url):
        self.cursor.execute("SELECT 1 FROM crawled_data WHERE url = ?", (url,))
        return self.cursor.fetchone() is not None

    async def crawl_sequential(self, urls: List[str]):
        await self.crawler.start()

        session_id = "session1"

        found_urls = set()
        for url in urls:

            # TODO if url endswith .pdf download and process separately (take code from askUOS)

            if self.is_url_visited(url):
                logger.debug(f"Skipping visited URL: {url}")
                continue

            result = await self.crawler.arun(
                url=url, config=self.crawl_config, session_id=session_id
            )
            if result.success:
                self.count_visited += 1
                for link in result.links.get("internal", []):
                    found_urls.add(link["href"])
                for link in result.links.get("external", []):
                    if link["base_domain"] in ALLOWED_DOMAINS:
                        found_urls.add(link["href"])

                # Put the extracted data into the queue for processing
                # await: if queue is full, wait until there is space.
                if self.data_queue.full():
                    logger.warning("Data queue is full. Waiting for space...")
                await self.data_queue.put(result)

            else:
                logger.error(f"Failed: {url} - Error: {result.error_message}")
        self.urls = list(found_urls)

    async def data_processor(self):
        while True:
            # Get the extracted data from the queue
            result_data = await self.data_queue.get()
            if result_data is None:
                break  # Exit the loop if a sentinel value is received

            # Chunking, embedding generating, and saving to the vector DB
            await self.split_embed_to_db(result_data)

            # Mark the task as done
            self.data_queue.task_done()

    async def main(self):
        # Start the data processor in the background
        processor_task = asyncio.create_task(self.data_processor())

        # TODO make sure that the url is not already in the db (has been crawled before)
        while self.urls and self.count_visited < MAX_URLS:
            await self.crawl_sequential(self.urls)

        # Stop the processor worker
        await self.data_queue.put(None)  # Sending sentinel to stop the worker
        logger.debug(
            "Crawling finished. Waiting for the processor (Indexing and Storing) to finish..."
        )

        await processor_task  # Wait for the processor to finish

        await self.crawler.close()


if __name__ == "__main__":
    crawl_app = CrawlApp()
    asyncio.run(crawl_app.main())
    print()
