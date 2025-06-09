import sys
import shutil
from pathlib import Path

sys.path.append("/app/src")
import os

import asyncio
from typing import List, Callable, Optional
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)

from crawl4ai.database import init_db
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from src.db.process_web_content import ProcessEmbedMilvus
from logger.crawl_logger import logger
from config.core_config import settings

# Load settings


COLLECTION_NAME = settings.indexing_storage_settings.collection_name
EXCLUDE_DOMAINS = settings.crawl_settings.exclude_domains
# /root/.crawl4ai/crawl4ai.db   vs code  `code /root/.crawl4ai/`
DB_PATH = os.path.join(os.getenv("CRAWL4_AI_BASE_DIRECTORY", Path.home()), ".crawl4ai")
DB_PATH = os.path.join(DB_PATH, "crawl4ai.db")
QUEUE_MAX_SIZE = 3000


class BaseCrawl(ProcessEmbedMilvus):
    """
    Base class for crawling and processing web data, inheriting from ProcessEmbedMilvus.

    Attributes:
        session_id (str): Identifier for the session.
        data_queue (asyncio.Queue): Asynchronous queue for data processing.
        crawl_config (CrawlerRunConfig): Configuration for the crawler.
        crawler (AsyncWebCrawler): Asynchronous web crawler instance.

    Args:
        delete_old_collection (bool): Flag to indicate whether to delete the old collection in the Vector database.

    Methods:
        data_processor():
            Asynchronous method to process data from the queue, chunk it, generate embeddings, and save to the vector database.
    """

    def __init__(self, delete_old_collection: bool = False):

        super().__init__(
            collection_name=COLLECTION_NAME, delete_old_collection=delete_old_collection
        )
        init_db()

        self.session_id = "session1"

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
            logger.debug(
                f"Remaining tasks in the (Embedding) queue: {self.data_queue.qsize()}"
            )
