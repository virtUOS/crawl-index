import sys
import asyncio
import aiohttp
import aiosqlite
import json
from pathlib import Path

sys.path.append("/app/src")

import asyncio
from typing import List, Callable, Optional

from base import BaseCrawl, DB_PATH
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from logger.crawl_logger import logger


class ReCrawlApp(BaseCrawl):

    def __init__(self):

        super.__init__()

    async def fetch(self, session, url, stored_etag, stored_last_modified):
        # Prepare headers for conditional request
        headers = {}
        if stored_etag:
            headers["If-None-Match"] = stored_etag
        elif stored_last_modified:
            headers["If-Modified-Since"] = stored_last_modified
        else:
            # Neither ETag nor Last-Modified is present; skip crawling
            print(f"Skipping {url}; no ETag or Last-Modified header stored.")
            return None, None

        try:
            # Make a HEAD request with conditional headers
            async with session.head(url, headers=headers, timeout=10) as response:
                status = response.status
                new_headers = response.headers
                return status, new_headers
        except Exception as e:
            logger.error(f"Error accessing {url}: {e}")
            return None, None

    async def crawl(self, url):
        # TODO move these configurations to a parent class

        await self.crawler.start()

        # returns a CrawlResult object
        return await self.crawler.arun(
            url=url,
            config=self.crawl_config,
            session_id=self.session_id,
        )

    async def process_url(self, db, session, row):
        url, stored_headers_json = row
        stored_headers = json.loads(stored_headers_json)
        stored_etag = stored_headers.get("etag")
        stored_last_modified = stored_headers.get("last-modified")

        status, new_headers = await self.fetch(
            session, url, stored_etag, stored_last_modified
        )
        if status is None:
            return

        if status == 304:
            # Content has not changed; no need to re-crawl
            logger.debug(f"No changes detected for {url}.")
        elif status == 200:
            # Content has changed; update stored headers and mark for re-crawl

            await db.execute(
                """
                DELETE FROM crawled_data
                WHERE url = ?
                """,
                (url,),
            )
            await db.commit()

            # TODO if this is to slow, use the url_id instead in conjunction with the num_chunks field
            query_string = f'url == "{url}"'
            await self.vector_store.adelete(kwargs={"filter": query_string})

            # Crawl the URL
            result = await self.crawl(url)

            if result.success:
                if self.data_queue.full():
                    logger.warning("Data queue is full. Waiting for space...")
                # await: if queue is full, wait until there is space.
                await self.data_queue.put(result)
        else:
            logger.error(f"Failed: {url} - Error: {result.error_message}")

    async def main(self):
        processor_task = asyncio.create_task(self.data_processor())

        async with aiosqlite.connect(DB_PATH) as db:
            # TODO process the rows in batches, if row object is too big (memmory efficiency)
            async with db.execute(
                "SELECT url, response_headers FROM crawled_data"
            ) as cursor:
                rows = await cursor.fetchall()

            async with aiohttp.ClientSession() as session:
                tasks = [self.process_url(db, session, row) for row in rows]
                await asyncio.gather(*tasks)

        await processor_task

        # Stop the processor worker
        await self.data_queue.put(None)  # Sending sentinel to stop the worker
        logger.debug(
            "Crawling finished. Waiting for the processor (Indexing and Storing) to finish..."
        )

        await processor_task  # Wait for the processor to finish

        await self.crawler.close()

    def run(self):
        asyncio.run(self.main())


if __name__ == "__main__":
    re_crawl_app = ReCrawlApp(
        delete_old_collection=False
    )  # Drop the old (Vector DB) collection if it exists
    asyncio.run(re_crawl_app.main())
    print()
