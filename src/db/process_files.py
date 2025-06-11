# from pymilvus import MilvusClient
import os
from uuid import uuid4
import os
import dotenv

dotenv.load_dotenv()


from typing import List, Optional

from fastapi import HTTPException
from langchain_core.documents import Document
from pydantic import validate_call
from tqdm import tqdm

from src.db.utils import generate_unique_ids
from src.config.core_config import settings
from src.loaders.py_pdf_loader import parse_pdf
from src.logger.crawl_logger import logger
from src.db.py_pdf_schema import pdf_metadata_schema


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

    # Langchain creates db schema based on the first document's metadata,
    # make sure that the docs metadata matches the collection schema
    metadata_keys = documents[0].metadata.keys()

    for key in metadata_keys:
        if key not in pdf_metadata_schema.keys():
            logger.warning(f"Metadata key '{key}' not found in schema")
    try:
        # Use singleton client manager
        from src.config.client_manager import client_manager

        db = client_manager.get_milvus_client(
            pdf_metadata_schema,
            collection_name,
        )

        # To find a document by its name, we generate unique IDs based on the filename.
        # one can find a document by encoding (hashing) for example [0]filename. [0] indicates chunk 0 from document
        ids = generate_unique_ids(
            doc_name=os.path.basename(filename), num_documents=len(documents)
        )

        # Add to vector store
        db.add_documents(documents=documents, ids=ids)
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
