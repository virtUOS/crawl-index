import sys

sys.path.append("/app/src")
import os
import re
import asyncio
from typing import List, Optional
import aiohttp
from logger.crawl_logger import logger

# from src.db.milvus.process_web_content import split_embed_to_db
from src.db.postgres.postgres_client import get_postgres_client
from src.config.models import CrawlSettings, RAGFlowSettings
from tqdm import tqdm
from src.models import CrawlReusltsCustom
from config.core_config import settings
from src.config.core_config import settings
from src.db.postgres.postgres_client import close_postgres_client
from src.crawl_ai.utils import (
    CrawlHelperMixin,
    _process_ragflow,
    _retry_failed_docs_ragflow,
)
import pickle
from datetime import datetime


# TODO crawler does not process pdf files (they need to be downloaded and processed separately)

QUEUE_MAX_SIZE = 30000
NUM_PROCESS_WORKERS = 2  # Number of concurrent data processing workers
NUM_SCRAPE_WORKERS = 3  # Number of concurrent scraping workers
URL_BATCH_SIZE = 30  # Number of URLs to process in each batchS
CRAWL_API_URL = os.getenv("CRAWL_API_URL", "http://crawl-api:8000") + "/crawl"


class CrawlApp(CrawlHelperMixin):

    def __init__(self):

        self.data_queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self.url_queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self.count_visited = 0
        self.count_lock = asyncio.Lock()
        self.over_all_progress_lock = asyncio.Lock()
        self.session = None  # aiohttp session
        self.results = []

    @staticmethod
    def remove_fragment_from_url(url: str) -> str:
        """
        Remove traditional fragment identifiers (like #section, #top) but preserve SPA routes (like #/path).
        """
        # Pattern to match fragments that are NOT SPA routes (don't start with #/)
        # This matches # followed by anything that doesn't start with /
        pattern = r"#(?!/)[^#]*$"
        return re.sub(pattern, "", url)

    async def crawl_sequential_worker(
        self,
        over_all_progress: tqdm,
        config: CrawlSettings,
    ):

        while True:

            # async with self.count_lock:
            #     if self.count_visited >= config.max_urls_to_visit:
            #         return

            try:

                urls: List = await asyncio.wait_for(
                    self.url_queue.get(), timeout=4 * 60
                )
            except asyncio.TimeoutError:
                logger.info("Crawl worker timed out waiting for URLs. Exiting.")
                return

            async with self.count_lock:
                if self.count_visited >= config.max_urls_to_visit:
                    self.url_queue.task_done()
                    return

            if urls is None:
                self.url_queue.task_done()
                return  # Exit the loop if a sentinel value is received

            found_urls = set()

            # Get PostgreSQL client for URL existence checking
            pg_client = await get_postgres_client()

            # filter out urls that are already in the database
            existing_urls = await pg_client.urls_exist(urls)
            urls = list(set(urls) - existing_urls)

            async with self.count_lock:
                if self.count_visited + len(urls) > config.max_urls_to_visit:
                    urls = urls[: config.max_urls_to_visit - self.count_visited]

            if len(urls) == 0:
                continue

            # Crawl all URLs in this batch via API
            logger.debug(f"Crawling {len(urls)} URLs via API...")
            api_results: List[dict] = await self.crawl_urls_via_api(
                urls, config.crawl_payload
            )

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
                            if link["base_domain"] in config.allowed_domains:
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

                found_urls = list(found_urls)
                # only add urls that do not exceed the max_urls_to_visit limit
                async with self.count_lock:
                    if self.count_visited + len(found_urls) > config.max_urls_to_visit:
                        found_urls = found_urls[
                            : config.max_urls_to_visit - self.count_visited
                        ]
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

    async def save_snapshot(self, crawl_payload: Optional[dict] = None):
        # todo save the crawl config as well
        queues = {
            "url_queue_items": list(
                self.url_queue._queue
            ),  # where each element is a list of urls (batches)
            "data_queue_items": list(self.data_queue._queue),
            "count_visited": self.count_visited,
            "crawl_payload": crawl_payload,
        }

        with open(f"crawl_snapshot_{datetime.now().isoformat()}.pkl", "wb") as f:
            pickle.dump(queues, f)

    async def main(
        self,
        first_crawl_config: CrawlSettings = CrawlSettings(),
        data_processing_settings: RAGFlowSettings = RAGFlowSettings(),
        restore_snapshot: Optional[str] = None,
    ):

        # makes sure required fields are present
        crawl_config, config_data_processing = self.get_configs(
            first_crawl_config, data_processing_settings
        )

        # Start worker tasks to process data from the queue
        workers = [
            asyncio.create_task(self.worker(config_data_processing, _process_ragflow))
            for _ in range(NUM_PROCESS_WORKERS)
        ]

        # Create aiohttp session
        timeout = aiohttp.ClientTimeout(
            total=300, connect=60, sock_read=300
        )  # 5 min total, 5 min read
        self.session = aiohttp.ClientSession(timeout=timeout)

        if restore_snapshot:
            # Load snapshot
            with open(restore_snapshot, "rb") as f:
                queues = pickle.load(f)

            for item in queues["url_queue_items"]:
                await self.url_queue.put(item)

            for item in queues["data_queue_items"]:
                await self.data_queue.put(item)

            self.count_visited = queues["count_visited"]
            crawl_config.crawl_payload = queues["crawl_payload"]
            logger.info(
                f"Restored snapshot from {restore_snapshot}. URLs in queue: {self.url_queue.qsize()}, Data items in queue: {self.data_queue.qsize()}, Count visited: {self.count_visited}, Crawl payload: {config.crawl_payload is not None}"
            )
        try:

            with tqdm(
                total=crawl_config.max_urls_to_visit,
                initial=self.count_visited if restore_snapshot else 0,
                desc="Overall Progress (MAX_URLS)",
            ) as over_all_progress:

                scrape_workers = [
                    asyncio.create_task(
                        self.crawl_sequential_worker(
                            over_all_progress,
                            crawl_config,
                        )
                    )
                    for _ in range(NUM_SCRAPE_WORKERS)
                ]

                await self.url_queue.put(crawl_config.start_url)
                await asyncio.gather(*scrape_workers, return_exceptions=True)

                await self.data_queue.join()
                logger.info("All data has been processed.")

                for _ in range(NUM_PROCESS_WORKERS):
                    await self.data_queue.put(
                        None
                    )  # Send sentinel values to stop workers
                await asyncio.gather(*workers)
                logger.info("Crawl completed successfully.")

            await self.retry_failed_docs(config_data_processing)

        except Exception as e:
            logger.error(f"An error occurred during crawling: {e}")
            await self.save_snapshot(crawl_config.crawl_payload)

        finally:
            await close_postgres_client()
            # Close aiohttp session
            if self.session:
                await self.session.close()


if __name__ == "__main__":
    # TODO allow the drop collection argument to be passed via api call
    crawl_app = CrawlApp()  # Drop the old (Vector DB) collection if it exists
    asyncio.run(crawl_app.main())
    print()
