import os
import re
import threading
from typing import Any, List, NamedTuple, Optional

import numpy as np
import requests
from logger.crawl_logger import logger
from dotenv import load_dotenv
from pydantic import BaseModel
from ragflow_sdk import RAGFlow
from src.models import CrawlReusltsCustom
import aiohttp
import asyncio
import uuid
from slugify import slugify  # This needs to be installed
from src.config.core_config import settings


class RAGFlowSingleton:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(RAGFlowSingleton, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("RAGFLOW_API_KEY")
        self.base_url = base_url or settings.ragflow.base_url
        self.dbs = {}
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def __del__(self) -> None:
        if self._session:
            self._session.close()

    def get_db_id(self, db_name: str, session) -> str:
        """Get the database ID for a given database name."""
        if db_name in self.dbs.keys():
            return self.dbs[db_name]

        try:
            resp = self._session.get(
                f"{self.base_url}/api/v1/datasets", params={"name": db_name}
            )
            if resp.status_code == 200:
                datasets = resp.json()
                if datasets and "data" in datasets and datasets["data"]:
                    self.dbs[db_name] = datasets["data"][0]["id"]
                    logger.debug(f"Database ID for '{db_name}': {self.dbs[db_name]}")
                    return datasets["data"][0]["id"]
                else:
                    logger.error(f"Database '{db_name}' not found.")
                    raise ValueError(f"Database '{db_name}' not found.")
            else:
                logger.error(f"Failed to fetch database ID: {resp.status_code}")
                raise ValueError(
                    f"Failed to fetch database ID: {resp.status_code} - {resp.text}"
                )
        except requests.RequestException as e:
            logger.error(f"Network error while fetching database ID: {e}")
            raise ValueError(f"Network error: {e}")

    def generate_file_name(url: str) -> str:
        # to ensure uniqueness, append a short uuid
        uuid_str = str(uuid.uuid4())[:8]
        file_name = (
            url.replace("https://", "")
            .replace("http://", "")
            .replace("www", "")
            .replace("/", "_")[:92]
        )
        return f"{file_name}_{uuid_str}"

    async def save_to_ragflow_async(self, db_id: str, document: CrawlReusltsCustom):
        """Upload a document asynchronously using in-memory buffer."""

        url = f"{self.base_url}/api/v1/datasets/{db_id}/documents"

        try:
            file_name = self.generate_file_name(document.url)

            # Create in-memory buffer
            markdown_bytes = document.formatted_markdown.encode("utf-8")

            # Use aiohttp FormData
            data = aiohttp.FormData()
            data.add_field(
                "file",
                markdown_bytes,
                filename=f"{file_name}.md",
                content_type="text/markdown",
            )

            headers = {"Authorization": f"Bearer {self.api_key}"}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as response:
                    if response.status in (200, 201):
                        result = await response.json()
                        logger.info(f"Successfully uploaded document: {file_name}")
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

        update_url = f"{self.base_url}/api/v1/datasets/{db_id}/documents/{doc_id}"
        metadata = {
            "url": document.url,
            "title": document.title or "",
            "description": document.description or "",
            "keywords": document.keywords or "",
            "author": document.author or "",
        }

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    update_url, headers=headers, json={"meta_fields": metadata}
                ) as response:
                    if response.status in (200, 204):
                        logger.info(
                            f"Successfully updated metadata for doc ID: {doc_id}"
                        )
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
        parse_url = f"{self.base_url}/api/v1/datasets/{db_id}/chunks"
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    parse_url, headers=headers, json={"document_ids": [doc_id]}
                ) as response:
                    if response.status in (200, 202):
                        logger.info(f"Started parsing for doc ID: {doc_id}")
                        return True
                    else:
                        text = await response.text()
                        logger.error(
                            f"Failed to start parsing: {response.status} - {text}"
                        )
        except Exception as e:
            logger.error(f"Error starting parsing in RAGFlow: {e}")
        return False

    async def process_ragflow(
        self,
        result: CrawlReusltsCustom,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        if api_key or base_url:
            self._initialize(api_key, base_url)

        db_name = collection_name or settings.ragflow.collection_name
        if not db_name:
            raise ValueError(
                "Collection name must be provided either as an argument or in settings."
            )
        db_id = self.get_db_id(db_name)
        res = await self.save_to_ragflow_async(db_id, result)
        if res:
            doc_id = res["data"][0]["id"]
            save_metadata = await self.save_metadata(doc_id, db_id, result)
            if save_metadata:
                # parse the document in RAGFlow
                logger.info(f"Starting parsing for document in RAGFlow.")
                self.start_parsing(doc_id, db_id)


ragflow_object = RAGFlowSingleton()

if __name__ == "__main__":
    # for testing purposes
    ragflowretriever = RAGFlowSingleton()

    r1 = ragflowretriever("Credit points computer science", "UOS_PO")
    r2 = ragflowretriever("Credit points biology", "UOS_PO")
    r3 = ragflowretriever("Leistungspunkte Informatik", "UOS_PO")

    print(r1, r2, r3)
