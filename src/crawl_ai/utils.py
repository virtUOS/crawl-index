import json
from src.config.core_config import settings
from logger.crawl_logger import logger
from typing import List, Optional, Callable, Awaitable, Tuple
import os
import asyncio
from typing import Awaitable, Callable, Tuple
from src.config.core_config import settings
from src.ragflow.client import ragflow_object
from src.db.postgres.postgres_client import close_postgres_client
from src.models import CrawlReusltsCustom, RAGFlowProcessInfo
from src.db.milvus.process_web_content import split_embed_to_db
from src.db.postgres.postgres_client import get_postgres_client
from src.config.models import RAGFlowSettings, CrawlSettings

CRAWL_API_URL = os.getenv("CRAWL_API_URL", "http://crawl-api:8000") + "/crawl"
NUM_PROCESS_RETRY_WORKERS = 3


async def _process_ragflow(
    extrated_data: CrawlReusltsCustom,
    update_data: bool,
    config_data_processing: RAGFlowSettings,
):
    ragflow_doc_id, save_metadata, parsing_started = (
        await ragflow_object.process_ragflow(
            result=extrated_data,
            update_data=update_data,
            ragflow_settings=config_data_processing,
        )
    )
    return ragflow_doc_id, save_metadata, parsing_started


async def _retry_failed_docs_ragflow(
    extrated_data: CrawlReusltsCustom,
    update_data: bool,
    config_data_processing: RAGFlowSettings,
):
    ragflow_doc_id = extrated_data.ragflow_process_info.ragflow_doc_id
    save_metadata = extrated_data.ragflow_process_info.save_metadata
    parsing_started = extrated_data.ragflow_process_info.parsing_started
    if ragflow_doc_id:
        await ragflow_object._ensure_initialized(config_data_processing)
        db_id = (
            await ragflow_object.get_db_id(config_data_processing.collection_name),
        )

        if not save_metadata:
            # update metadata only
            save_metadata = await ragflow_object.save_metadata(
                doc_id=extrated_data.ragflow_process_info.ragflow_doc_id,
                db_id=db_id,
            )
        if not parsing_started:
            # start parsing only
            parsing_started = await ragflow_object.start_parsing(
                doc_id=extrated_data.ragflow_process_info.ragflow_doc_id,
                db_id=db_id,
            )
    else:  # retry processing failed docs
        ragflow_doc_id, save_metadata, parsing_started = (
            await ragflow_object.process_ragflow(
                result=extrated_data,
                update_data=update_data,
                ragflow_settings=config_data_processing,
            )
        )
    return ragflow_doc_id, save_metadata, parsing_started


class CrawlHelperMixin:

    async def crawl_urls_via_api(
        self, urls: List[str], crawl_payload: Optional[dict] = None
    ) -> List[dict]:
        """
        Crawl multiple URLs using the API endpoint.
        Returns a list of crawl results.
        """

        try:

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

    def _get_extracted_data(self, result_data):
        if type(result_data) is CrawlReusltsCustom:
            self.extrated_data = result_data
        else:
            self.extrated_data = CrawlReusltsCustom(
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
                ragflow_process_info=result_data.get("ragflow_process_info", None),
            )

    async def retry_failed_docs(self, config_data_processing: RAGFlowSettings):
        # retry saving to RAGFlow, where ragflow_doc_id is missing
        logger.info("Processing documents failed to be saved to RAGFlow...")

        # Start worker tasks to process data from the queue
        workers = [
            asyncio.create_task(
                self.worker(
                    config_data_processing=config_data_processing,
                    process_ragflow_function=_retry_failed_docs_ragflow,
                    force_update=True,
                )
            )
            for _ in range(NUM_PROCESS_RETRY_WORKERS)
        ]
        pg_client = await get_postgres_client()
        async for result_data in pg_client.get_not_processed_ragflow_docs():
            # Parse JSON string fields to dictionaries
            if isinstance(result_data.get("media"), str):
                result_data["media"] = json.loads(result_data["media"])
            if isinstance(result_data.get("links"), str):
                result_data["links"] = json.loads(result_data["links"])
            if isinstance(result_data.get("response_headers"), str):
                result_data["response_headers"] = json.loads(
                    result_data["response_headers"]
                )
            if isinstance(result_data.get("downloaded_files"), str):
                result_data["downloaded_files"] = json.loads(
                    result_data["downloaded_files"]
                )
            if isinstance(result_data.get("ragflow_process_info"), str):
                ragflow_process_info = json.loads(result_data["ragflow_process_info"])
                result_data["ragflow_process_info"] = RAGFlowProcessInfo(
                    **ragflow_process_info
                )

            result = CrawlReusltsCustom(**result_data)
            await self.data_queue.put(result)

        await self.data_queue.join()
        for _ in range(NUM_PROCESS_RETRY_WORKERS):
            await self.data_queue.put(None)  # Sentinel values to stop workers

        await asyncio.gather(*workers, return_exceptions=True)

    async def worker(
        self,
        config_data_processing: RAGFlowSettings,
        process_ragflow_function: Callable[
            [CrawlReusltsCustom, bool, RAGFlowSettings],
            Awaitable[Tuple[str, bool, bool]],
        ],
        update_data: bool = False,  # whether to update existing data in RAGFlow
        force_update: bool = False,  # whether to force update existing data in Postgres
    ):
        """
        Worker to process extracted data from the crawl and save to vector DB or RAGFlow.

        """
        logger.info(
            f"Worker started with function: {process_ragflow_function.__name__}"
        )

        while True:
            # Get the extracted data from the queue
            logger.debug("Worker waiting for data from queue...")
            result_data = await self.data_queue.get()

            if result_data is None:
                self.data_queue.task_done()
                break  # Exit the loop if a sentinel value is received

            # Get PostgreSQL client
            pg_client = await get_postgres_client()

            self._get_extracted_data(result_data)

            if (
                not self.extrated_data.is_content_useful
                or self.extrated_data.is_content_pdf
            ):
                await pg_client.add_scraped_result(self.extrated_data)
                self.data_queue.task_done()
                continue

            if settings.milvus is not None:
                # Chunking, embedding generating, and saving to the vector DB
                await split_embed_to_db(result_data)

            elif settings.ragflow is not None:
                ragflow_doc_id, save_metadata, parsing_started = (
                    await process_ragflow_function(
                        extrated_data=self.extrated_data,
                        update_data=update_data,
                        config_data_processing=config_data_processing,
                    )
                )
                self.extrated_data.ragflow_process_info = RAGFlowProcessInfo(
                    ragflow_doc_id=ragflow_doc_id,
                    save_metadata=save_metadata,
                    parsing_started=parsing_started,
                )

                # TODO: SAVING TO RAGFLOW AND POSTGRES SHOULD BE ONE TRANSACTION, SO IF ONE FAILS, THE OTHER ROLLBACKS
                await pg_client.add_scraped_result(
                    data=self.extrated_data, force_update=force_update
                )

            else:

                raise ValueError("No vector database configuration found")

            # Mark the task as done
            self.data_queue.task_done()

            logger.debug(
                f"Remaining tasks in the (Vector DB) queue: {self.data_queue.qsize()}"
            )

    def get_configs(
        self, crawl_config: CrawlSettings, data_processing_settings: RAGFlowSettings
    ):

        # if configs are not provided through API, use configuration form config.yaml and env vars
        crawl_config = CrawlSettings(
            start_url=crawl_config.start_url or settings.crawl_settings.start_url,
            max_urls_to_visit=crawl_config.max_urls_to_visit
            or settings.crawl_settings.max_urls_to_visit,
            crawl_payload=crawl_config.crawl_payload
            or settings.crawl_settings.crawl_payload,
            allowed_domains=crawl_config.allowed_domains
            or settings.crawl_settings.allowed_domains,
        )

        # Validate required fields
        crawl_config.validate_required_fields()

        config_data_processing = RAGFlowSettings(
            base_url=data_processing_settings.base_url or settings.ragflow.base_url,
            collection_name=data_processing_settings.collection_name
            or settings.ragflow.collection_name,
        )
        config_data_processing.validate_required_fields()

        return crawl_config, config_data_processing
