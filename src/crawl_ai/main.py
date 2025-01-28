import os
import pickle
import asyncio
from typing import List, Callable, Optional
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from db.milvus_main import ProcessEmbedMilvus

# from indexer.milvus_optional import ProcessEmbedMilvusNative
# TODO Execute this in Dockerfile playwright install (Needed  crawl4ai)

START_URL = "https://teaching-toolbox.uni-osnabrueck.de/"
# START_URL = "https://www.uni-osnabrueck.de/studieninteressierte/"
MAX_URLS = 5
ALLOWED_DOMAINS = ["uni-osnabrueck.de", "uos.de"]
COLLECTION_NAME = "uni_web_index_v1"

SAVE_TO_PICKLE_INTERVAL = 2

# TODO crawler does not process pdf files (they need to be downloaded and processed separately)

downloads_path = os.path.join(os.getcwd(), "downloads")  # Custom download path
os.makedirs(downloads_path, exist_ok=True)
pkl_path = os.path.join(os.getcwd(), "pkl")
os.makedirs(pkl_path, exist_ok=True)


class CrawlApp(ProcessEmbedMilvus):
    def __init__(self):
        print("\n=== Sequential Crawling with Session Reuse ===")

        super().__init__(collection_name=COLLECTION_NAME)
        self.count_visited = 0
        self.count_pkl_files = 0
        self.urls = {START_URL}
        self.results = []
        # TODO Queue limit? if object is too bing and does not fit in memory??
        self.data_queue = asyncio.Queue()  # Create an async queue for data processing
        browser_config = BrowserConfig(
            headless=True,
            extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
        )

        self.crawl_config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(),
            cache_mode=CacheMode.ENABLED,  # Avoid redundant requests
            scan_full_page=True,  # crawler tryes to scroll the entire page
            scroll_delay=0.5,
        )

        self.crawler = AsyncWebCrawler(config=browser_config)

    async def save_to_pickle(self, results, pkl_file):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_to_pickle, results, pkl_file)

    def _write_to_pickle(self, results, pkl_file):
        with open(pkl_file, "wb") as f:
            pickle.dump(results, f)

    @staticmethod
    def read_from_pickle(
        process_pickle: Optional[Callable] = None, pkl_path: str = pkl_path
    ):
        """
        Reads data from pickle files in the specified directory and processes each item.

        Args:
            process_pickle (Optional[Callable]): A function to process each item from the pickle file.
                                                 If None, the function will stop after loading the first item.
            pkl_path (str): The path to the directory containing the pickle files.

            example:
            def process_pickle(result):
                print(result["markdown_v2"]["raw_markdown"])

            CrawlApp.read_from_pickle(process_pickle=process_pickle)

        """
        for file in os.listdir(pkl_path):
            file_path = os.path.join(pkl_path, file)
            with open(file_path, "rb") as f:
                loaded = pickle.load(f)
                for result in loaded:
                    if process_pickle is not None:
                        process_pickle(result)
                    else:
                        break

    async def crawl_sequential(self, urls: List[str]):
        await self.crawler.start()

        session_id = "session1"

        found_urls = set()
        for url in urls:

            # TODO if url endswith .pdf download and process separately (take code from askUOS)

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
                await self.data_queue.put(result)

                self.results.append(result.model_dump())

                if len(self.results) >= SAVE_TO_PICKLE_INTERVAL:
                    results_copy = self.results.copy()
                    self.results.clear()
                    self.count_pkl_files += 1
                    pkl_file = os.path.join(
                        pkl_path, f"results_{self.count_pkl_files}.pkl"
                    )
                    await self.save_to_pickle(results_copy, pkl_file)

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
        # TODO make sure that the url is not already in the db (has been crawled before)
        while self.urls and self.count_visited < MAX_URLS:
            await self.crawl_sequential(self.urls)

        # Stop the processor worker
        await self.data_queue.put(None)  # Sending sentinel to stop the worker
        print(
            "Crawling finished. Waiting for the processor (Indexing and Storing) to finish..."
        )

        if self.results:
            await self.save_to_pickle(self.results)

        await processor_task  # Wait for the processor to finish

        await self.crawler.close()


if __name__ == "__main__":
    crawl_app = CrawlApp()
    asyncio.run(crawl_app.main())
    print()
