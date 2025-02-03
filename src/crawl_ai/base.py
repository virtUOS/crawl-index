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
from db.milvus_main import ProcessEmbedMilvus
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

    def __init__(self):

        super().__init__(collection_name=COLLECTION_NAME)
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
