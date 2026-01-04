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


from src.db.postgres.postgres_client import get_postgres_client
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from logger.crawl_logger import logger
from src.models import RAGFlowProcessInfo
from src.config.models import ReCrawlSettings
from src.ragflow.client import ragflow_object
from src.config.core_config import settings
from tqdm import tqdm
from src.crawl_ai.utils import (
    CrawlHelperMixin,
    _process_ragflow,
)

BATCH_SIZE_PAGINATION = 30  # Cannot be greater than 100 due to crawl4ai API limits
NUM_PROCESS_WORKERS = 3
NUM_SCRAPE_WORKERS = 3
NUM_NEW_URL_SCRAPE_WORKERS = 2
URL_BATCH_SIZE = 30


class ReCrawlApp(CrawlHelperMixin):

    def __init__(self):
        self.new_urls_queue: asyncio.Queue = asyncio.Queue(
            maxsize=100
        )  # New URLs found during re-crawl
        self.rows_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self.data_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.url_queue: asyncio.Queue = asyncio.Queue(
            maxsize=100
        )  # These urls couldnot be crawled in the first attempt, retry them later

        # Collect URLs to mark as inactive - process after all workers complete
        self.urls_to_deactivate: set = set()
        self.deactivate_lock = asyncio.Lock()

        self.progress_lock = asyncio.Lock()

        self.fail_to_update = (
            {}
        )  # keep track of URLs that failed to update in vector db
        self.fail_to_update_lock = asyncio.Lock()

        self.fail_to_crawl_new_links = (
            {}
        )  # keep track of new links that failed to crawl
        self.fail_to_crawl_new_links_lock = asyncio.Lock()

    async def new_links_scraper(
        self, overall_progress=None, crawl_payload: Optional[dict] = None
    ):

        async def _increase_progress():
            async with self.progress_lock:
                if overall_progress:
                    overall_progress.update(1)

        while True:

            urls = await self.new_urls_queue.get()
            if urls is None:
                self.new_urls_queue.task_done()
                break
            api_results = await self.crawl_urls_via_api(
                urls=urls, crawl_payload=crawl_payload
            )

            for result_data in api_results:
                if result_data.get("success") is False:
                    async with self.fail_to_crawl_new_links_lock:
                        self.fail_to_crawl_new_links.add(result_data.get("url"))
                    logger.error(
                        f"Failed to crawl new link {result_data.get('url')}: {result_data.get('error_message')}"
                    )
                    continue

                await self.data_queue.put(result_data)
            await _increase_progress()

    async def scrape(self, overall_progress=None, crawl_payload: Optional[dict] = None):

        async def _increase_progress():
            async with self.progress_lock:
                if overall_progress:
                    overall_progress.update(1)

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
                    if result_data["status_code"] in [404, 410]:
                        logger.info(
                            f"[DEACTIVATE] URL returned {result_data['status_code']}, marking inactive: {result_data['url']}"
                        )
                        # Mark as inactive in DB
                        async with self.deactivate_lock:
                            self.urls_to_deactivate.add(result_data["url"])
                        await _increase_progress()
                        continue

                    if result_data.get("success") is False:
                        async with self.fail_to_update_lock:
                            self.fail_to_update.add(result_data.get("url"))
                        logger.error(
                            f"Failed to crawl {result_data.get('url')}: {result_data.get('error_message')}"
                        )
                        await _increase_progress()
                        continue

                    content_for_hash = (
                        result_data["markdown"]["raw_markdown"]
                        or result_data["cleaned_html"]
                        or result_data["html"]
                        or ""
                    )
                    content_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()
                    url = result_data["url"]
                    # Find the corresponding stored row for this URL in the batch coming from the db
                    stored_row = next((row for row in rows if row["url"] == url), None)
                    if not stored_row:
                        continue

                    sotored_raw_content_hash = stored_row[
                        "content_hash"
                    ]  # content_hash column
                    if content_hash != sotored_raw_content_hash:
                        # get the existing RAGFlow doc ID for update (this id has been stored in ragflow_process_info dict in the DB)
                        ragflow_process_info = json.loads(
                            stored_row["ragflow_process_info"]
                        )
                        result_data["ragflow_process_info"] = ragflow_process_info
                        # Content has changed, mark for re-crawl
                        logger.info(f"[UPDATE] Content changed, updating URL: {url}")

                        await self.data_queue.put(result_data)

                    # check if new URLs are found in links and add them to new_urls_queue queue
                    links_stored = json.loads(stored_row["links"])  # links stored in db
                    internal_links_stored = [
                        link["href"] for link in links_stored.get("internal", [])
                    ]

                    fresh_links = result_data.get("links", {})
                    internal_links_fresh = [
                        link["href"] for link in fresh_links.get("internal", [])
                    ]

                    new_links = [
                        link
                        for link in internal_links_fresh
                        if link not in internal_links_stored
                    ]
                    if new_links:
                        if (
                            len(new_links) > 100
                        ):  # by the time this was written, crawl4ai can only process max 100 urls at once.
                            # crate batches of URL_BATCH_SIZE urls
                            for i in range(0, len(new_links), URL_BATCH_SIZE):
                                batch = new_links[i : i + URL_BATCH_SIZE]
                                if batch:
                                    await self.new_urls_queue.put(batch)
                        else:
                            await self.new_urls_queue.put(new_links)

                    for link in internal_links_stored:
                        if link not in internal_links_fresh:
                            logger.info(
                                f"[DEACTIVATE] URL no longer found, marking inactive: {link}"
                            )
                            # Mark as inactive in DB
                            async with self.deactivate_lock:
                                self.urls_to_deactivate.add(link)

                    await _increase_progress()

            finally:
                self.rows_queue.task_done()

    async def load_snapshot(self, restore_snapshot: str):
        """Load snapshot from file if it exists."""

        with open("re_crawl_snapshot.json", "r") as f:
            data = json.load(f)

        self.urls_to_deactivate = data["urls_to_deactivate"]
        self.fail_to_update = data["fail_to_update"]
        self.fail_to_crawl_new_links = data["fail_to_crawl_new_links"]

        self.current_batch_num = data["current_batch_num"]
        self.total_batches = data["total_batches"]

        # Restore queues
        for url in data.get("new_urls_in_queue", []):
            await self.new_urls_queue.put(url)
        for row in data.get("rows_in_queue", []):
            await self.rows_queue.put(row)
        for item in data.get("data_in_queue", []):
            await self.data_queue.put(item)
        for url in data.get("urls_in_queue", []):
            await self.url_queue.put(url)

    async def save_snapshot(self):
        data = {
            "urls_to_deactivate": list(self.urls_to_deactivate),
            "fail_to_update": self.fail_to_update,
            "fail_to_crawl_new_links": self.fail_to_crawl_new_links,
            "new_urls_in_queue": list(self.new_urls_queue._queue),
            "rows_in_queue": list(self.rows_queue._queue),
            "data_in_queue": list(self.data_queue._queue),
            "urls_in_queue": list(self.url_queue._queue),
            "current_batch_num": self.current_batch_num,
            "total_batches": self.total_batches,
        }
        with open("re_crawl_snapshot.json", "w") as f:
            json.dump(data, f, indent=4)

    async def _deactivate_delete_urls(self, data_processing_settings):
        logger.info(f"Marking {len(self.urls_to_deactivate)} URLs as inactive")
        pg_client = await get_postgres_client()
        # delete these from vector db as well
        ragflow_ids = await pg_client.mark_urls_inactive(list(self.urls_to_deactivate))
        if ragflow_ids and len(ragflow_ids) > 0:
            db_name = data_processing_settings.collection_name
            # ensure ragflow_object is initialized
            await ragflow_object._ensure_initialized(data_processing_settings)
            db_id = await ragflow_object.get_db_id(db_name)

            await ragflow_object.delete_doc_ragflow(db_id, ragflow_ids)

    async def _process_new_urls(self, data_processing_settings, crawl_ai_payload):
        logger.info(
            f"Processing new URLs found during re-crawl: {self.new_urls_queue.qsize()} URLs"
        )
        # create new workers to process new URLs, set update_data=False
        _workers = [
            asyncio.create_task(
                self.worker(
                    config_data_processing=data_processing_settings,
                    process_ragflow_function=_process_ragflow,
                    update_data=False,
                )
            )
            for _ in range(NUM_PROCESS_WORKERS)
        ]

        with tqdm(
            total=self.new_urls_queue.qsize(),
            desc="Overall Progress (New URLs)",
        ) as overall_progress:
            new_link_scrapers = [
                asyncio.create_task(
                    self.new_links_scraper(overall_progress, crawl_ai_payload)
                )
                for _ in range(NUM_NEW_URL_SCRAPE_WORKERS)
            ]

            await self.new_urls_queue.join()

            # send sentinel values to stop new link scrapers
            for _ in range(NUM_NEW_URL_SCRAPE_WORKERS):
                await self.new_urls_queue.put(None)

            # Wait for all new link scrapers to complete
            await asyncio.gather(*new_link_scrapers)

            await self.data_queue.join()
            # send sentinel values to stop workers
            for _ in range(NUM_PROCESS_WORKERS):
                await self.data_queue.put(None)

            # Wait for all workers to complete
            await asyncio.gather(*_workers)

    async def main(
        self,
        recrawl_settings: Optional[ReCrawlSettings] = ReCrawlSettings(),
        restore_snapshot: Optional[str] = None,  # path to snapshot file
    ):

        # TODO: enclose in try catch finally, in case the app crashes, save the current state of the app to a picke file and restart later
        _crawl_ai_payload = (
            recrawl_settings.crawl_payload or settings.re_crawl_settings.crawl_payload
        )
        _data_processing_settings = (
            recrawl_settings.ragflow_settings or settings.ragflow
        )

        if not all([_crawl_ai_payload, _data_processing_settings]):
            raise ValueError(
                "Crawl configuration is incomplete. Please make sure you provided the correct re_crawl_settings with crawl_payload and ragflow_settings."
            )

        # Start worker tasks to process data from the queue
        workers = [
            asyncio.create_task(
                self.worker(
                    config_data_processing=_data_processing_settings,
                    process_ragflow_function=_process_ragflow,
                    update_data=True,
                )
            )
            for _ in range(NUM_PROCESS_WORKERS)
        ]

        # Create aiohttp session
        timeout = aiohttp.ClientTimeout(
            total=300, connect=60, sock_read=300
        )  # 5 min total, 5 min read
        self.session = aiohttp.ClientSession(timeout=timeout)

        pg_client = await get_postgres_client()

        self.current_batch_num = 0

        if restore_snapshot:
            await self.load_snapshot(restore_snapshot)
        else:
            total_urls = await pg_client.get_total_url_count(only_useful=True)
            _total_batches = (
                total_urls + BATCH_SIZE_PAGINATION - 1
            ) // BATCH_SIZE_PAGINATION

            logger.info(
                f"Processing {total_urls} URLs in {_total_batches} batches of {BATCH_SIZE_PAGINATION}"
            )
            self.total_batches = _total_batches

        try:
            with tqdm(
                total=total_urls,
                desc="Overall Progress (MAX_URLS)",
                initial=self.current_batch_num
                * BATCH_SIZE_PAGINATION,  # Resume progress bar
            ) as over_all_progress:

                scrapers = [
                    asyncio.create_task(
                        self.scrape(over_all_progress, _crawl_ai_payload)
                    )
                    for _ in range(NUM_SCRAPE_WORKERS)
                ]

                for batch_num in range(self.current_batch_num, self.total_batches):
                    offset = batch_num * BATCH_SIZE_PAGINATION
                    rows = await pg_client.get_urls_batch(
                        limit=BATCH_SIZE_PAGINATION, offset=offset, only_useful=True
                    )

                    logger.debug(
                        f"Processing batch {batch_num + 1}/{self.total_batches} ({len(rows)} URLs)"
                    )

                    await self.rows_queue.put(rows)
                    self.current_batch_num = (
                        batch_num  # Track current batch (done after putting to queue)
                    )

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

            # Batch mark collected URLs as inactive
            if self.urls_to_deactivate:
                self._deactivate_delete_urls(_data_processing_settings)

            if self.new_urls_queue.qsize() > 0:
                self._process_new_urls(_data_processing_settings, _crawl_ai_payload)

            await self.retry_failed_docs(_data_processing_settings)
        except Exception as e:
            logger.error(f"Exception during re-crawl: {e}")
            await self.save_snapshot()
            raise KeyboardInterrupt("Crawl interrupted, snapshot saved.")

        finally:
            # save fail urls to pickle
            logger.info(f"Failed to update: {self.fail_to_update}")
            logger.info(f"Failed to crawl new links: {self.fail_to_crawl_new_links}")

            print("Saving failed URLs to pickle files...")

            import pickle

            with open("fail_to_update.pkl", "wb") as f:
                pickle.dump(self.fail_to_update, f)

            with open("fail_to_crawl_new_links.pkl", "wb") as f:
                pickle.dump(self.fail_to_crawl_new_links, f)

            # Close session
            await self.session.close()

        logger.info("Re-crawl completed successfully")

    def run(self):
        asyncio.run(self.main())


if __name__ == "__main__":
    re_crawl_app = ReCrawlApp()  # Drop the old (Vector DB) collection if it exists
    asyncio.run(re_crawl_app.main())
    print()
