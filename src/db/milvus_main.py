# from pymilvus import MilvusClient
import os
import logging
from typing import List, Tuple
from dotenv import load_dotenv
from logger.crawl_logger import logger

import hashlib
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.documents.base import Document
from langchain_milvus import Milvus
from .web_schema import metadate_schema

from crawl4ai import CrawlResult

# Configurations
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
DEFAULT_DATA_DIR = "./data/documents/"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 0


# Initialize embeddings
embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)


load_dotenv()
URI = os.getenv("MILVUS_URL")


class ProcessEmbedMilvus:
    """
    A class to process and embed documents into a Milvus vector store.

    Methods
    -------
    __init__(collection_name: str)
        Initializes the Milvus vector store and text splitter.

    get_internal_external_links(result: CrawlResult) -> Tuple[List[str], List[str]]
        Extracts internal and external links from a CrawlResult object.

    async split_embed_to_db(result: CrawlResult) -> None
        Splits the content of a CrawlResult into smaller documents, embeds them, and stores them in the Milvus vector store.

    generate_unique_id(url: str, index: int) -> str
        Generates a unique SHA-256 hash ID for a given URL and index.
    """

    # Function to create or load the database client
    def __init__(self, collection_name: str):

        self.vector_store = Milvus(
            embedding_function=embeddings,
            connection_args={"uri": URI},
            primary_field="url_id",
            # collection_properties=collection_properties,
            metadata_schema=metadate_schema,
            collection_name=collection_name,
            # enable_dynamic_field=True, # if True the metadata schema will be ignored
            # auto_id=True,
            drop_old=True,  # Drop the old collection if it exists #TODO change to False
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )

    @staticmethod
    def get_internal_external_links(result: CrawlResult) -> Tuple[List[str], List[str]]:

        internal = {
            l["href"]
            for l in result.links.get("internal", [])
            if isinstance(l, dict) and "href" in l
        }
        external = {
            l["href"]
            for l in result.links.get("external", [])
            if isinstance(l, dict) and "href" in l
        }
        return list(internal), list(external)

    async def split_embed_to_db(self, result: CrawlResult) -> None:
        # TODO it is possible to get result.markdown_v2.markdown_with_citations and then result.markdown_v2.references_markdown
        # TODO concatenate them and save to db as page_content (downside context is to long, and single langchain documents
        # wouldnt have the references)
        # result.json(); then save to db as metadata (used for seach with filters)
        page_content = result.markdown_v2.raw_markdown
        # TODO every langchain Document will have all of these metadata fields (think of some relational strategy
        # where there is like a parent object that contains all metadata and then the subdocuments i.e. Langchain Document)

        metadata = {
            "url": result.url,
            "response_headers_date": result.response_headers.get("date", ""),
            "response_headers_content_type": result.response_headers.get(
                "content-type", ""
            ),
            "response_headers_content_language": result.response_headers.get(
                "content-language", ""
            ),
            "response_headers_etag": result.response_headers.get(
                "etag", " "
            ),  # to check if the page has changed
            "response_headers_last_modified": result.response_headers.get(
                "last-modified", ""
            ),
            "internal_links": ProcessEmbedMilvus.get_internal_external_links(result)[0],
            "external_links": ProcessEmbedMilvus.get_internal_external_links(result)[1],
            "title": result.metadata.get("title", ""),
            "meta_keywords": result.metadata.get("keywords", ""),
        }

        documents = None
        # TODO: Instead of passing just one page_content, pass a list of page_contents (Documents)
        data = [
            Document(
                page_content=page_content,
                metadata=metadata,
            )
        ]
        documents = self.text_splitter.split_documents(data)

        # Assign unique IDs to documents
        # url_id ex. [0]https://www.example.com
        url_id = [
            ProcessEmbedMilvus.generate_unique_id(result.url, index)
            for index in range(len(documents))
        ]

        # Add documents to the vector store
        await self.vector_store.aadd_documents(documents=documents, ids=url_id)

    @staticmethod
    def generate_unique_id(url: str, index: int) -> str:
        # Create a unique string for hashing
        unique_string = f"[{index}]{url}"
        # Create a SHA-256 hash of the unique string
        return hashlib.sha256(unique_string.encode()).hexdigest()
