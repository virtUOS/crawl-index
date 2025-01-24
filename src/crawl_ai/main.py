import asyncio
from typing import List
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from indexer.milvus_main import ProcessEmbedMilvus

# from indexer.milvus_optional import ProcessEmbedMilvusNative


START_URL = "https://teaching-toolbox.uni-osnabrueck.de/"
# START_URL = "https://www.uni-osnabrueck.de/studieninteressierte/"
MAX_URLS = 5
ALLOWED_DOMAINS = ["uni-osnabrueck.de", "uos.de"]
COLLECTION_NAME = "uni_web_index_v1"


class CrawlApp(ProcessEmbedMilvus):
    def __init__(self):
        print("\n=== Sequential Crawling with Session Reuse ===")

        super().__init__(collection_name=COLLECTION_NAME)
        self.count_visited = 0
        self.urls = {START_URL}
        # TODO Queue limit? if object is too bing and does not fit in memory??
        self.data_queue = asyncio.Queue()  # Create an async queue for data processing
        browser_config = BrowserConfig(
            headless=True,
            extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
        )

        self.crawl_config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator()
        )

        self.crawler = AsyncWebCrawler(config=browser_config)

    async def crawl_sequential(self, urls: List[str]):
        await self.crawler.start()

        session_id = "session1"

        found_urls = set()
        for url in urls:
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

                print(f"Successfully crawled: {url}")
                print(f"Markdown length: {len(result.markdown_v2.raw_markdown)}")

                # Put the extracted data into the queue for processing
                # TODO pass metadata to the queue
                await self.data_queue.put(result)

            else:
                print(f"Failed: {url} - Error: {result.error_message}")
        self.urls = list(found_urls)

    async def data_processor(self):
        while True:
            # Get the extracted data from the queue
            markdown_data = await self.data_queue.get()
            if markdown_data is None:
                break  # Exit the loop if a sentinel value is received

            # Here you would do the embedding generation and save to the vector DB
            await self.split_embed_to_db(markdown_data)

            # Mark the task as done
            self.data_queue.task_done()

    async def main(self):
        # Start the data processor in the background
        processor_task = asyncio.create_task(self.data_processor())

        while self.urls and self.count_visited < MAX_URLS:
            await self.crawl_sequential(self.urls)

        # Stop the processor worker
        await self.data_queue.put(None)  # Sending sentinel to stop the worker
        await processor_task  # Wait for the processor to finish

        await self.crawler.close()


if __name__ == "__main__":
    crawl_app = CrawlApp()
    asyncio.run(crawl_app.main())
    print()
