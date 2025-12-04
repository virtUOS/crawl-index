import sys

sys.path.append("/app/src")

import re
import asyncio
from typing import List, Optional

from logger.crawl_logger import logger
from src.db.process_web_content import split_embed_to_db
from src.db.postgres_client import get_postgres_client
from src.config.models import CrawlSettings
from tqdm import tqdm
from src.models import CrawlReusltsCustom
from config.core_config import settings
from src.ragflow.client import ragflow_object

from crawl4ai import AsyncWebCrawler

# TODO crawler does not process pdf files (they need to be downloaded and processed separately)

QUEUE_MAX_SIZE = 30000
NUM_WORKERS = 10


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
        self.count_visited = 0
        self.urls = {self.crawl_config.start_url}
        self.results = []

    async def worker(self):
        while True:
            # Get the extracted data from the queue
            result_data = await self.data_queue.get()
            if result_data is None:
                break  # Exit the loop if a sentinel value is received

            # save data to postgres
            pg_client = await get_postgres_client()

            # check if the content is useful

            extrated_data = CrawlReusltsCustom(
                url=result_data.url,
                html=result_data.html,
                cleaned_html=result_data.cleaned_html,
                media=result_data.media,
                downloaded_files=result_data.downloaded_files,
                markdown=result_data.markdown,
                title=result_data.metadata["title"],
                description=result_data.metadata["description"],
                keywords=result_data.metadata["keywords"],
                author=result_data.metadata["author"],
                status_code=result_data.status_code,
                links=result_data.links,
                response_headers=result_data.response_headers,
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

    async def data_processor(self) -> None:
        while True:
            # Get the extracted data from the queue
            result_data = await self.data_queue.get()
            if result_data is None:
                break  # Exit the loop if a sentinel value is received

            # Chunking, embedding generating, and saving to the vector DB
            await split_embed_to_db(result_data)

            # Mark the task as done
            self.data_queue.task_done()
            logger.debug(
                f"Remaining tasks in the (Embedding) queue: {self.data_queue.qsize()}"
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

    async def crawl_sequential(
        self,
        urls: List[str],
        over_all_progress: tqdm,
        crawl_config,
        browser_config,
        dispatcher,
        session_id,
    ):

        found_urls = set()

        # Get PostgreSQL client for URL existence checking
        pg_client = await get_postgres_client()

        # filter out urls that are already in the database
        existing_urls = await pg_client.urls_exist(urls)
        urls = list(set(urls) - existing_urls)

        with tqdm(
            total=len(urls), desc="Crawling URLs (Internal)", leave=False
        ) as url_progress_bar:

            async with AsyncWebCrawler(config=browser_config) as crawler:

                results = await crawler.arun_many(
                    urls=urls, config=crawl_config, dispatcher=dispatcher
                )
            for result in results:

                if result.success:
                    self.count_visited += 1
                    for link in result.links.get("internal", []):
                        found_urls.add(CrawlApp.remove_fragment_from_url(link["href"]))
                    for link in result.links.get("external", []):
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
                    await self.data_queue.put(result)

                else:
                    logger.error(
                        f"[FAIL-SCRAPING] Failed: {result.url} - Error: {result.error_message}"
                    )
                url_progress_bar.update(1)
                over_all_progress.update(1)

                if (
                    self.count_visited >= self.crawl_config.max_urls_to_visit
                ):  # Use self.crawl_config
                    break

        self.urls = list(found_urls)
        # TODO Delete this line to allow full crawling
        # self.urls = self.urls[0:1]

    async def main(self):
        # Start the data processor in the background
        # processor_task = asyncio.create_task(self.data_processor())
        workers = [asyncio.create_task(self.worker()) for _ in range(NUM_WORKERS)]
        from src.config.core_config import settings
        from src.db.postgres_client import close_postgres_client

        try:
            crawler_config, browser_config, dispatcher, session_id = (
                settings.get_crawler()
            )
            # await crawler.start()

            with tqdm(
                total=self.crawl_config.max_urls_to_visit,
                desc="Overall Progress (MAX_URLS)",
            ) as over_all_progress:
                while self.count_visited <= self.crawl_config.max_urls_to_visit:
                    if self.urls:
                        await self.crawl_sequential(
                            self.urls,
                            over_all_progress,
                            crawler_config,
                            browser_config,
                            dispatcher,
                            session_id,
                        )
                    else:
                        logger.debug("No more URLs to crawl. Exiting...")
                        break

            # Stop the processor worker
            # await self.data_queue.put(None)

            await self.data_queue.join()
            [w.cancel() for w in workers]
            logger.debug(
                "Crawling finished. Waiting for the processor (Indexing and Storing) to finish..."
            )

            # await processor_task
            await crawler.close()
            await close_postgres_client()

        except Exception as e:
            logger.error(f"An error occurred during crawling: {e}")
            await close_postgres_client()


if __name__ == "__main__":
    # TODO allow the drop collection argument to be passed via api call
    crawl_app = CrawlApp()  # Drop the old (Vector DB) collection if it exists
    asyncio.run(crawl_app.main())
    print()
