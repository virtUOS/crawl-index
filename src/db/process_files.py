# from pymilvus import MilvusClient
import os
from uuid import uuid4

import dotenv

dotenv.load_dotenv()


import argparse
import logging
import os
from typing import List, Optional

from clients import get_milvus_client
from pydantic import DirectoryPath, FilePath, validate_call
from tqdm import tqdm

from src.embeddings.fast_embed import embeddings
from src.loaders.py_pdf_loader import parse_pdf


DEFAULT_COLLECTION_NAME = "my_documents"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


URI = os.getenv("MILVUS_URL")


@validate_call
def create_db_from_documents(
    content: bytes, filename: str, collection_name: str = DEFAULT_COLLECTION_NAME
) -> None:

    # TODO: Needs to be done asynchronously

    db = get_milvus_client(collection_name)
    try:

        logger.info(f"Processing file: {filename}")
        documents = parse_pdf(
            content=content,
            filename=filename,
        )
        if documents:
            uuids = [str(uuid4()) for _ in range(len(documents))]
            db.add_documents(documents, ids=uuids)
    except Exception as e:
        logger.error(
            f"An error ocurrued while processing/embedding this file: {filename}. Error: {e}"
        )

    logger.info("DB creation completed")
