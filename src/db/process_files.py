# from pymilvus import MilvusClient
import os
from uuid import uuid4

import dotenv

dotenv.load_dotenv()


from typing import List, Optional

from fastapi import HTTPException
from langchain_core.documents import Document
from pydantic import validate_call
from tqdm import tqdm

from src.db.clients import get_milvus_client
from src.config.core_config import settings
from src.loaders.py_pdf_loader import parse_pdf
from src.logger.crawl_logger import logger


@validate_call
def create_db_from_documents(
    content: bytes,
    filename: str,
    collection_name: str = settings.milvus.collection_name,
) -> tuple[
    Optional[str],  # Filename of the processed document or None if failed
    Optional[str],  # Error message if processing failed, None if successful
]:
    """
    Process a document and store it in the vector database.

    Args:
        content: The raw bytes of the document
        filename: Name of the file being processed
        collection_name: Name of the Milvus collection to store embeddings in

    Returns:
        List of Document objects that were processed and stored

    Raises:
        HTTPException: If document processing fails
    """

    try:
        # Parse the PDF into documents
        documents = parse_pdf(
            content=content,
            filename=filename,
        )
    except Exception as e:
        logger.error(f"Error processing file {filename}: {e}")

        return None, f"Error processing file {filename}"

    if not documents:
        logger.warning(f"Failed to parse PDF file: {filename}")
        return None, f"Failed to parse PDF file: {filename}"

    try:
        # Use singleton client manager
        from src.config.client_manager import client_manager

        db = client_manager.get_milvus_client(collection_name)

        # Generate UUIDs for documents
        uuids = [str(uuid4()) for _ in range(len(documents))]

        # Add to vector store
        db.add_documents(documents=documents, ids=uuids)
        logger.info(
            f"Successfully added {len(documents)} pages from {filename} to vector store"
        )
        return filename, None
    except Exception as e:
        logger.error(f"Failed to add documents to vector store: {e}")
        return (
            None,
            f"Failed to add documents to vector store, while processing {filename}",
        )
