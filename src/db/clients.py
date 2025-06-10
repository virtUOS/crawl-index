import os

import dotenv
from typing import Union

dotenv.load_dotenv()
from typing import Optional
from langchain_milvus import Milvus
from src.embeddings.main import get_embeddings
from src.config.core_config import settings
from pymilvus import connections, utility
from src.logger.crawl_logger import logger

# connections.connect(host="standalone", port="19530", token="root:Milvus")


def test_milvus_connection() -> Union[str, None]:
    """
    Test the connection to the Milvus server.

    Returns:
        str: Server version if connection is successful, None otherwise.
    """
    try:
        if settings.milvus.host:
            connections.connect(
                alias="default",
                host=settings.milvus.host,
                port=settings.milvus.port,
                token=settings.milvus.token,
            )
        else:
            # Use URL if host is not specified

            connections.connect(
                alias="default",
                uri=settings.milvus.uri,
                token=settings.milvus.token,
            )
        server_version = utility.get_server_version()
        if server_version:
            logger.debug(f"Connected to Milvus server version: {server_version}")
            return server_version
        else:
            logger.debug("Failed to retrieve server version.")
            return None

    except Exception as e:
        logger.debug(f"Connection failed: {e}")
        return None


# Updated function to use the singleton
def get_milvus_client(collection_name: Optional[str] = None) -> Milvus:
    """
    Get a configured Milvus client instance from the singleton manager.

    Args:
        collection_name: Optional name for the collection. If not provided,
                        uses the default from settings.

    Returns:
        Configured Milvus client instance
    """
    from src.config.client_manager import client_manager

    return client_manager.get_milvus_client(collection_name)
