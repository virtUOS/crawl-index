# from pymilvus import MilvusClient
import os
from uuid import uuid4

import dotenv

dotenv.load_dotenv()

import logging
import os
from typing import List, Optional


from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

from langchain_core.documents.base import Document
from langchain_milvus import Milvus

from crawl4ai import CrawlResult

# Configurations
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
DEFAULT_DATA_DIR = "./data/documents/"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize embeddings
embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)


# URI = os.getenv("MILVUS_URL")
# URI = "http://test-cmchatbot.virtuos.uni-osnabrueck.de"
URI = "http://milvus-test-virtuos-openstack.uni-osnabrueck.de"


class ProcessEmbedMilvus:

    # Function to create or load the database client
    def __init__(self, collection_name: str):

        self.vector_store = Milvus(
            embedding_function=embeddings,
            connection_args={"uri": URI},
            collection_name=collection_name,
            enable_dynamic_field=True,
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )

    async def split_embed_to_db(self, result: CrawlResult) -> None:
        # TODO it is possible to get result.markdown_v2.markdown_with_citations and then result.markdown_v2.references_markdown
        # TODO concatenate them and save to db as page_content (downside context is to long, and single langchain documents
        # wouldnt have the references)
        # result.json(); then save to db as metadata (used for seach with filters)
        page_content = result.markdown_v2.raw_markdown
        # TODO every langchain Document will have all of these metadata fields (think of some relational strategy
        # where there is like a parten object that contains all metadata and then the subdocuments i.e. Langchain Document)
        # TODO make urls the id, maybe hashed urls, or make index the url field to improve search speed
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
                "etag", ""
            ),  # to check if the page has changed
            "response_headers_last_modified": result.response_headers.get(
                "last-modified", ""
            ),
            "internal_links": result.links.get("internal", []),
            "external_links": result.links.get("external", []),
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
        uuids = [str(uuid4()) for _ in range(len(documents))]

        # Add documents to the vector store
        await self.vector_store.aadd_documents(documents=documents, ids=uuids)
