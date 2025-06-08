import os

import dotenv

dotenv.load_dotenv()
import os
from typing import List, Optional

from langchain_milvus import Milvus
from src.embeddings.fast_embed import embeddings


URI = os.getenv("MILVUS_URL")
MILVUS_USER = os.getenv("MILVUS_USER")
MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD")


def get_milvus_client(collection_name: str) -> Milvus:

    vector_store = Milvus(
        embedding_function=embeddings,
        connection_args={"uri": URI, "token": f"{MILVUS_USER}:{MILVUS_PASSWORD}"},
        collection_name=collection_name,
    )

    return vector_store
