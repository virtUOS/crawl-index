import sys

sys.path.append("/app/src")

import asyncio
from typing import List, Optional

from base import BaseCrawl, DB_PATH
from logger.crawl_logger import logger
from config.core_config import settings
import sqlite3
from tqdm import tqdm

# Load settings

START_URL = settings.crawl_settings.start_url
MAX_URLS = settings.crawl_settings.max_urls_to_visit
ALLOWED_DOMAINS = settings.crawl_settings.allowed_domains


# TODO crawler does not process pdf files (they need to be downloaded and processed separately)


class CrawlApp(BaseCrawl):
    def __init__(self):

        super().__init__()

        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()
        self.count_visited = 0
        self.urls = {START_URL}
        self.results = []

    def is_url_visited(self, url):
        self.cursor.execute("SELECT 1 FROM crawled_data WHERE url = ?", (url,))
        return self.cursor.fetchone() is not None

    async def crawl_sequential(self, urls: List[str], over_all_progress: tqdm):
        await self.crawler.start()

        found_urls = set()

        with tqdm(
            total=len(urls), desc="Crawling URLs (Internal)", leave=False
        ) as url_pogress_bar:
            for url in urls:

                # TODO if url endswith .pdf download and process separately (take code from askUOS)

                # TODO THIS SLOWING DOWN THE CRAWLING
                if self.is_url_visited(url):
                    logger.debug(f"Skipping visited URL: {url}")
                    continue

                result = await self.crawler.arun(
                    url=url, config=self.crawl_config, session_id=self.session_id
                )
                if result.success:
                    self.count_visited += 1
                    for link in result.links.get("internal", []):
                        found_urls.add(link["href"])
                    for link in result.links.get("external", []):
                        if link["base_domain"] in ALLOWED_DOMAINS:
                            found_urls.add(link["href"])

                    # Put the extracted data into the queue for processing
                    if self.data_queue.full():
                        logger.warning("Data queue is full. Waiting for space...")
                    # await: if queue is full, wait until there is space.
                    await self.data_queue.put(result)

                else:
                    logger.error(f"Failed: {url} - Error: {result.error_message}")
                url_pogress_bar.update(1)
                over_all_progress.update(1)

                if self.count_visited >= MAX_URLS:
                    break

        self.urls = list(found_urls)

    async def main(self):

        # Start the data processor in the background
        processor_task = asyncio.create_task(self.data_processor())

        with tqdm(
            total=MAX_URLS, desc="Overall Progress (MAX_URLS)"
        ) as over_all_progress:
            while self.count_visited < MAX_URLS:
                if self.urls:
                    await self.crawl_sequential(self.urls, over_all_progress)
                else:
                    logger.debug("No more URLs to crawl. Exiting...")
                    break

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
