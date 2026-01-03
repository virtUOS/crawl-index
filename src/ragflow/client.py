import os
import threading
from typing import Any, List, Optional
import json
import requests
from logger.crawl_logger import logger
from dotenv import load_dotenv
from ragflow_sdk import RAGFlow
from src.models import CrawlReusltsCustom
import aiohttp
import asyncio
import uuid
from slugify import slugify
from src.config.core_config import settings
from src.config.models import RAGFlowSettings


class RAGFlowSingleton:
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    _init_lock = asyncio.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(RAGFlowSingleton, cls).__new__(cls)
        return cls._instance

    async def _ensure_initialized(self, ragflow_settings: RAGFlowSettings):
        """Ensure the instance is initialized (async-safe)."""

        async with self._init_lock:
            if not self._initialized:
                self.api_key = ragflow_settings.api_key
                self.base_url = ragflow_settings.base_url
                self.dbs = {}
                self._aio_session = aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                self._initialized = True
                logger.debug("RAGFlowSingleton initialized")

    async def close(self):
        if (
            hasattr(self, "_aio_session")
            and self._aio_session
            and not self._aio_session.closed
        ):
            await self._aio_session.close()
            self._initialized = False

    async def get_docs_count(self, db_id: str) -> int:
        """Get the document count for a given database ID."""
        # make sure this method was run, before executing this function await self._ensure_initialized()

        try:
            async with self._aio_session.get(
                f"{self.base_url}/api/v1/datasets/{db_id}/documents"
            ) as resp:
                if resp.status == 200:
                    res = await resp.json()

                    return len(res["data"]["docs"])
                else:
                    text = await resp.text()
                    logger.error(f"Failed to fetch document count: {resp.status}")
                    raise ValueError(
                        f"Failed to fetch document count: {resp.status} - {text}"
                    )
        except Exception as e:
            logger.error(f"Network error while fetching document count: {e}")
            raise ValueError(f"Network error: {e}")

    async def get_db_id(self, db_name: str) -> str:
        """Get the database ID for a given database name."""
        # make sure this method was run, before executing this function await self._ensure_initialized()

        if db_name in self.dbs:
            return self.dbs[db_name]

        try:
            async with self._aio_session.get(
                f"{self.base_url}/api/v1/datasets", params={"name": db_name}
            ) as resp:
                if resp.status == 200:
                    datasets = await resp.json()
                    if datasets and "data" in datasets and datasets["data"]:
                        self.dbs[db_name] = datasets["data"][0]["id"]
                        logger.debug(
                            f"Database ID for '{db_name}': {self.dbs[db_name]}"
                        )
                        return datasets["data"][0]["id"]
                    else:
                        logger.error(f"Database '{db_name}' not found.")
                        raise ValueError(f"Database '{db_name}' not found.")
                else:
                    text = await resp.text()
                    logger.error(f"Failed to fetch database ID: {resp.status}")
                    raise ValueError(
                        f"Failed to fetch database ID: {resp.status} - {text}"
                    )
        except Exception as e:
            logger.error(f"Network error while fetching database ID: {e}")
            raise ValueError(f"Network error: {e}")

    @staticmethod
    def generate_file_name(url: str) -> str:
        uuid_str = str(uuid.uuid4())[:8]
        file_name = (
            url.replace("https://", "")
            .replace("http://", "")
            .replace("www.", "")
            .replace("www", "")
            .replace("/", "_")[:92]
        )
        return f"{file_name}_{uuid_str}"

    async def save_to_ragflow_async(self, db_id: str, document: CrawlReusltsCustom):
        """Upload a document asynchronously using in-memory buffer."""
        # ensure this method was called before await self._ensure_initialized()

        url = f"{self.base_url}/api/v1/datasets/{db_id}/documents"
        try:
            file_name = self.generate_file_name(document.url)
            markdown_bytes = document.formatted_markdown.encode("utf-8")
            data = aiohttp.FormData()
            data.add_field(
                "file",
                markdown_bytes,
                filename=f"{file_name}.md",
                content_type="text/markdown",
            )
            async with self._aio_session.post(url, data=data) as response:
                if response.status in (200, 201):
                    result = await response.json()
                    # logger.info(f"Successfully uploaded document: {file_name}")
                    return result
                else:
                    text = await response.text()
                    logger.error(
                        f"Failed to upload document: {response.status} - {text}"
                    )
                    raise ValueError(f"Upload failed: {response.status}")
        except Exception as e:
            logger.error(f"Error uploading document to RAGFlow: {e}")
            return None

    async def save_metadata(
        self, doc_id: str, db_id: str, document: CrawlReusltsCustom
    ):
        # await self._ensure_initialized()

        update_url = f"{self.base_url}/api/v1/datasets/{db_id}/documents/{doc_id}"
        # TODO : Add date
        metadata = {
            "url": document.url,
            "title": document.title or "",
            "description": document.description or "",
            "keywords": document.keywords or "",
            "author": document.author or "",
        }
        try:
            async with self._aio_session.put(
                update_url, json={"meta_fields": metadata}
            ) as response:
                res = await response.json()
                if res["code"] == 0:

                    # logger.info(f"Successfully updated metadata for doc ID: {doc_id}")
                    return True
                else:
                    text = await response.text()
                    logger.error(
                        f"Failed to update metadata: {response.status} - {text}"
                    )
        except Exception as e:
            logger.error(f"Error updating metadata in RAGFlow: {e}")
        return False

    async def start_parsing(self, doc_id: str, db_id: str):
        # await self._ensure_initialized()

        parse_url = f"{self.base_url}/api/v1/datasets/{db_id}/chunks"
        try:
            async with self._aio_session.post(
                parse_url, json={"document_ids": [doc_id]}
            ) as response:
                if response.status in (200, 202):
                    res = await response.json()
                    if res["code"] == 0:
                        return True

                else:
                    text = await response.text()
                    logger.error(f"Failed to start parsing: {response.status} - {text}")
        except Exception as e:
            logger.error(f"Error starting parsing in RAGFlow: {e}")
        return False

    async def get_ragflow_doc(self, db_id, url):

        doc_url = f"{self.base_url}/api/v1/datasets/{db_id}/documents"
        # await self._ensure_initialized()

        # Match the curl example
        metadata_condition = {
            "logic": "and",
            "conditions": [
                {"name": "url", "comparison_operator": "is", "value": url},
            ],
        }

        params = {"metadata_condition": json.dumps(metadata_condition)}
        try:
            async with self._aio_session.get(doc_url, params=params) as response:
                if response.status in (200, 202):
                    res = await response.json()
                    doc_ids = [d["id"] for d in res["data"]["docs"]]
                    return doc_ids
                else:
                    text = await response.text()
                    logger.error(f"Failed to start parsing: {response.status} - {text}")
        except Exception as e:
            logger.error(f"Error starting parsing in RAGFlow: {e}")
        return False

    async def delete_doc_ragflow(self, db_id, doc_ids):
        # ensure this method was called before await self._ensure_initialized()

        delete_url = f"{self.base_url}/api/v1/datasets/{db_id}/documents"
        try:
            async with self._aio_session.delete(
                delete_url, json={"ids": doc_ids}
            ) as response:

                res = await response.json()
                if res["code"] == 0:
                    logger.info(f"Successfully deleted documents: {doc_ids}")
                    return True

                else:

                    text = await response.text()
                    logger.error(
                        f"Failed to delete document: {response.status} - {text}"
                    )
        except Exception as e:
            logger.error(f"Error deleting document in RAGFlow: {e}")
        return False

    async def process_ragflow(
        self,
        result: CrawlReusltsCustom,
        ragflow_settings: RAGFlowSettings,
        # collection_name: Optional[str] = None,
        update_data: bool = False,
    ):

        await self._ensure_initialized(ragflow_settings)

        # db_name = collection_name or settings.ragflow.collection_name
        db_name = ragflow_settings.collection_name
        if not db_name:
            raise ValueError(
                "Collection name must be provided either as an argument or in settings."
            )
        db_id = await self.get_db_id(db_name)
        if update_data:
            # Check if document exists
            # existing_doc_ids = await self.get_ragflow_doc(db_id, result.url)
            # if existing_doc_ids:
            # Delete existing document
            await self.delete_doc_ragflow(db_id, [result.ragflow_doc_id])

        res = await self.save_to_ragflow_async(db_id, result)
        if res:
            doc_id = res["data"][0]["id"]
            save_metadata = await self.save_metadata(doc_id, db_id, result)
            if save_metadata:
                logger.info(f"Starting parsing for document in RAGFlow.")
                parsed = await self.start_parsing(doc_id, db_id)

            return doc_id, save_metadata, parsed

        logger.error(f"Failed to process document in RAGFlow.")
        return None, False, False


# to use the singleton you need to await ragflow_object._ensure_initialized(ragflow_settings) first
ragflow_object = RAGFlowSingleton()


# Example async usage for testing
async def main():
    # Replace with actual CrawlReusltsCustom instance and valid args
    # result = CrawlReusltsCustom(...)
    # await ragflow_object.process_ragflow(result)
    pass


if __name__ == "__main__":
    asyncio.run(main())
