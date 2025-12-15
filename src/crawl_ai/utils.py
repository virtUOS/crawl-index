from src.config.core_config import settings
from logger.crawl_logger import logger
from typing import List, Optional
import os
from src.ragflow.client import ragflow_object
from src.db.postgres_client import close_postgres_client
from src.models import CrawlReusltsCustom
from src.db.process_web_content import split_embed_to_db
from src.db.postgres_client import get_postgres_client

CRAWL_API_URL = os.getenv("CRAWL_API_URL", "http://crawl-api:8000") + "/crawl"


class CrawlHelperMixin:

    async def crawl_urls_via_api(
        self, urls: List[str], crawl_payload: Optional[dict] = None
    ) -> List[dict]:
        """
        Crawl multiple URLs using the API endpoint.
        Returns a list of crawl results.
        """

        try:
            if not crawl_payload:
                # doc https://www.postman.com/pixelao/pixel-public-workspace/documentation/c26yn3l/crawl4ai-api?entity=request-24060341-db21f4c1-3760-4a21-abad-3c07a90e08da
                payload = {
                    "urls": urls,
                    "browser_config": {
                        "type": "BrowserConfig",
                        "params": {"headless": True},
                    },
                    "crawler_config": {
                        "type": "CrawlerRunConfig",
                        "params": {
                            "stream": False,
                            "cache_mode": {"type": "CacheMode", "params": "bypass"},
                            "word_count_threshold": 100,
                            "target_elements": settings.crawl_settings.target_elements
                            or [],
                            "scan_full_page": True,
                            "exclude_domains": settings.crawl_settings.exclude_domains
                            or [],
                        },
                    },
                }
            else:
                payload = crawl_payload
                payload["urls"] = urls
                payload["crawler_config"]["params"][
                    "stream"
                ] = False  # ensure non-streaming mode

            async with self.session.post(
                CRAWL_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 200:
                    # Wait for the complete response
                    response_data = await response.json()

                    # Extract results from the response
                    if response_data.get("success") is False:
                        logger.error("Crawl API reported failure: ")
                        return []

                    results = response_data.get("results", [])

                    return results
        except Exception as e:
            logger.error(f"Exception while crawling via API: {e}")
            # retry
            await self.url_queue.put(urls)
            return []

    async def worker(self, update_data: bool = False):
        while True:
            # Get the extracted data from the queue
            result_data = await self.data_queue.get()

            if result_data is None:
                self.data_queue.task_done()
                break  # Exit the loop if a sentinel value is received

            # Get PostgreSQL client
            pg_client = await get_postgres_client()

            extrated_data = CrawlReusltsCustom(
                url=result_data["url"],
                html=result_data["html"],
                cleaned_html=result_data["cleaned_html"],
                media=result_data["media"],
                downloaded_files=result_data["downloaded_files"],
                markdown=result_data["markdown"]["raw_markdown"],
                title=result_data["metadata"]["title"],
                description=result_data["metadata"]["description"],
                keywords=result_data["metadata"]["keywords"],
                author=result_data["metadata"]["author"],
                status_code=result_data["status_code"],
                links=result_data["links"],
                response_headers=result_data["response_headers"],
                ragflow_doc_id=result_data.get("ragflow_doc_id", None),
            )

            if not extrated_data.is_content_useful or extrated_data.is_content_pdf:
                await pg_client.add_scraped_result(extrated_data)
                self.data_queue.task_done()
                continue

            if settings.milvus is not None:
                # Chunking, embedding generating, and saving to the vector DB
                await split_embed_to_db(result_data)

            elif settings.ragflow is not None:
                doc_id = await ragflow_object.process_ragflow(
                    result=extrated_data, update_data=update_data
                )
                extrated_data.ragflow_doc_id = doc_id

                # TODO: SAVING TO RAGFLOW AND POSTGRES SHOULD BE ONE TRANSACTION, SO IF ONE FAILS, THE OTHER ROLLBACKS
                await pg_client.add_scraped_result(extrated_data)

            else:

                raise ValueError("No vector database configuration found")

            # Mark the task as done
            self.data_queue.task_done()

            logger.debug(
                f"Remaining tasks in the (Vector DB) queue: {self.data_queue.qsize()}"
            )
