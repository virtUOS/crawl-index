# import sys

# sys.path.append("/app/src")
# import types

# import asyncio

# from typing import List, Callable, Optional

# from logger.crawl_logger import logger
# from config.core_config import settings
# from src.db.process_web_content import split_embed_to_db


# # /root/.crawl4ai/crawl4ai.db   vs code  `code /root/.crawl4ai/`
# # DB_PATH = os.path.join(os.getenv("CRAWL4_AI_BASE_DIRECTORY", Path.home()), ".crawl4ai")
# # DB_PATH = os.path.join(DB_PATH, "crawl4ai.db")


# QUEUE_MAX_SIZE = 5000


# class BaseCrawl:

#     def __init__(self):

#         self.session_id = "session1"

#         self.data_queue = asyncio.Queue(
#             maxsize=QUEUE_MAX_SIZE
#         )  # Create an async queue for data processing

#         browser_config = BrowserConfig(
#             headless=True,
#             verbose=True,
#         )

#         self.crawl_config = CrawlerRunConfig(
#             cache_mode=CacheMode.ENABLED,
#             target_elements=settings.crawl_settings.target_elements or None,
#             scan_full_page=True,
#             verbose=settings.crawl_settings.debug,
#             exclude_domains=settings.crawl_settings.exclude_domains or [],
#             stream=False,
#         )
#         dispatcher = MemoryAdaptiveDispatcher(
#             memory_threshold_percent=70.0,
#             check_interval=1.0,
#             max_session_permit=10,
#             monitor=CrawlerMonitor(),
#         )

#         # self.crawl_config = CrawlerRunConfig(
#         #     markdown_generator=DefaultMarkdownGenerator(),
#         #     cache_mode=CacheMode.ENABLED,  # Avoid redundant requests
#         #     scan_full_page=True,  # crawler tryes to scroll the entire page
#         #     scroll_delay=0.5,
#         #     exclude_domains=EXCLUDE_DOMAINS,
#         # )

#         self.crawler = AsyncWebCrawler(config=browser_config)

#     async def data_processor(self) -> None:
#         while True:
#             # Get the extracted data from the queue
#             result_data = await self.data_queue.get()
#             if result_data is None:
#                 break  # Exit the loop if a sentinel value is received

#             # Chunking, embedding generating, and saving to the vector DB
#             await split_embed_to_db(result_data)

#             # Mark the task as done
#             self.data_queue.task_done()
#             logger.debug(
#                 f"Remaining tasks in the (Embedding) queue: {self.data_queue.qsize()}"
#             )
