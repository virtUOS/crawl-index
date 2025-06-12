# from pymilvus import MilvusClient

from typing import List, Tuple
from dotenv import load_dotenv
from logger.crawl_logger import logger

from config.core_config import settings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents.base import Document
from crawl4ai import CrawlResult
from src.db.utils import generate_unique_ids
from src.config.client_manager import client_manager
from src.db.web_schema import metadata_schema

load_dotenv()
CHUNK_SIZE = 500
CHUNK_OVERLAP = 70


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


async def split_embed_to_db(result: CrawlResult) -> None:
    # TODO it is possible to get result.markdown_v2.markdown_with_citations and then result.markdown_v2.references_markdown
    # TODO concatenate them and save to db as page_content (downside context is to long, and single langchain documents
    # wouldnt have the references)
    # result.json(); then save to db as metadata (used for seach with filters)
    page_content = result[0].markdown
    # TODO every langchain Document will have all of these metadata fields (think of some relational strategy
    # where there is like a parent object that contains all metadata and then the subdocuments i.e. Langchain Document)

    db = client_manager.get_milvus_client(
        metadata_schema,
        collection_name=settings.milvus.collection_name,
    )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

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
        "internal_links": get_internal_external_links(result)[0],
        "external_links": get_internal_external_links(result)[1],
        "title": result.metadata.get("title", ""),
        "meta_keywords": result.metadata.get("keywords", ""),
    }

    # TODO use langachain markdown parser to parse the markdown and extract metadata
    documents = None
    # TODO: Instead of passing just one page_content, pass a list of page_contents (Documents)
    data = [
        Document(
            page_content=page_content,
            metadata=metadata,
        )
    ]
    documents = text_splitter.split_documents(data)

    # Assign unique IDs to documents
    # url_id ex. [0]https://www.example.com

    url_id = generate_unique_ids(result.url, len(documents))

    try:
        # Add documents to the vector store
        await db.aadd_documents(documents=documents, ids=url_id)
    except Exception as e:
        logger.error(
            f"Failed to add documents to the vector store: {e}. Url: {result.url}"
        )
