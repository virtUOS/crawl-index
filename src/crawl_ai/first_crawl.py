import sys

sys.path.append("/app/src")

import re
import asyncio
from typing import List, Optional

from src.crawl_ai.base import BaseCrawl
from logger.crawl_logger import logger
from config.core_config import settings
from tqdm import tqdm

# Load settings


# TODO crawler does not process pdf files (they need to be downloaded and processed separately)


class CrawlApp(BaseCrawl):

    def __init__(self):

        super().__init__()

        self.count_visited = 0
        self.urls = {settings.crawl_settings.start_url}
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

    async def crawl_sequential(self, urls: List[str], over_all_progress: tqdm):
        await self.crawler.start()

        found_urls = set()

        with tqdm(
            total=len(urls), desc="Crawling URLs (Internal)", leave=False
        ) as url_progress_bar:
            for url in urls:

                result = await self.crawler.arun(
                    url=url, config=self.crawl_config, session_id=self.session_id
                )
                if result.success:
                    self.count_visited += 1
                    for link in result.links.get("internal", []):
                        found_urls.add(CrawlApp.remove_fragment_from_url(link["href"]))
                    for link in result.links.get("external", []):
                        if (
                            link["base_domain"]
                            in settings.crawl_settings.allowed_domains
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
                    logger.error(f"Failed: {url} - Error: {result.error_message}")
                url_progress_bar.update(1)
                over_all_progress.update(1)

                if self.count_visited >= settings.crawl_settings.max_urls_to_visit:
                    break

        self.urls = list(found_urls)

    async def main(self):

        # Start the data processor in the background
        processor_task = asyncio.create_task(self.data_processor())

        with tqdm(
            total=settings.crawl_settings.max_urls_to_visit,
            desc="Overall Progress (MAX_URLS)",
        ) as over_all_progress:
            while self.count_visited <= settings.crawl_settings.max_urls_to_visit:
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
    # TODO allow the drop collection argument to be passed via api call
    crawl_app = CrawlApp()  # Drop the old (Vector DB) collection if it exists
    asyncio.run(crawl_app.main())
    print()
