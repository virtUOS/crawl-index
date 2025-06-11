import threading
from typing import Optional
from langchain_milvus import Milvus
from src.db.clients import test_milvus_connection
from src.embeddings.main import get_embeddings
from src.config.core_config import settings
from src.config.models import MilvusSettings, EmbeddingSettings
from src.logger.crawl_logger import logger


class ClientManager:
    """Singleton class to manage Milvus and embedding clients"""

    _instance: Optional["ClientManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ClientManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._milvus_client: Optional[Milvus] = None
            self._embedding_client = None
            self._current_milvus_config: Optional[MilvusSettings] = None
            self._current_embedding_config: Optional[EmbeddingSettings] = None
            self._initialized = True

    def _should_reinitialize_milvus(self, new_config: MilvusSettings) -> bool:
        """Check if Milvus client needs reinitialization"""
        if self._current_milvus_config is None:
            return True

        # Compare critical connection parameters
        return (
            self._current_milvus_config.uri != new_config.uri
            or self._current_milvus_config.host != new_config.host
            or self._current_milvus_config.port != new_config.port
            or self._current_milvus_config.token != new_config.token
            or self._current_milvus_config.collection_name != new_config.collection_name
        )

    def _should_reinitialize_embedding(self, new_config: EmbeddingSettings) -> bool:
        """Check if embedding client needs reinitialization"""
        if self._current_embedding_config is None:
            return True

        return (
            self._current_embedding_config.type != new_config.type
            or self._current_embedding_config.connection_settings
            != new_config.connection_settings
        )

    def _initialize_milvus_client(self, config: MilvusSettings, schema: dict) -> Milvus:
        """Initialize Milvus client with given configuration"""
        # Ensure embedding client is initialized first
        embedding_client = self.get_embedding_client()

        if config.host:
            connection_args = {
                "uri": f"http://{config.host}",
                "port": config.port,
                "token": config.token,
            }
        else:
            connection_args = {
                "uri": config.uri,
                "token": config.token,
            }

        return Milvus(
            embedding_function=embedding_client,
            connection_args=connection_args,
            collection_name=config.collection_name,
            metadata_schema=schema,
            enable_dynamic_field=config.enable_dynamic_field,
            auto_id=config.auto_id,
        )

    def get_milvus_client(
        self, schema: dict, collection_name: Optional[str] = None
    ) -> Milvus:
        """Get or create Milvus client instance"""
        with self._lock:
            current_config = settings.milvus

            # Use custom collection name if provided
            if collection_name and collection_name != current_config.collection_name:
                config_copy = current_config.model_copy()
                config_copy.collection_name = collection_name
                embedding_client = self.get_embedding_client()
                return self._create_milvus_with_embedding(
                    config_copy, embedding_client, schema
                )

            # Check if we need to reinitialize
            if self._should_reinitialize_milvus(current_config):
                logger.info("Initializing/reinitializing Milvus client")
                self._milvus_client = self._initialize_milvus_client(
                    current_config, schema
                )
                self._current_milvus_config = current_config.model_copy()

            return self._milvus_client

    def _create_milvus_with_embedding(
        self, config: MilvusSettings, embedding_client, schema: dict
    ) -> Milvus:
        """Helper method to create Milvus client with pre-initialized embedding client"""
        if config.host:
            connection_args = {
                "uri": f"http://{config.host}",
                "port": config.port,
                "token": config.token,
            }
        else:
            connection_args = {
                "uri": config.uri,
                "token": config.token,
            }

        return Milvus(
            embedding_function=embedding_client,
            connection_args=connection_args,
            collection_name=config.collection_name,
            metadata_schema=schema,
            enable_dynamic_field=config.enable_dynamic_field,
            auto_id=config.auto_id,
        )

    def get_embedding_client(self):
        """Get or create embedding client instance"""

        current_config = settings.embedding

        if self._should_reinitialize_embedding(current_config):
            logger.info(
                f"Initializing/reinitializing {current_config.type} embedding client"
            )
            self._embedding_client = get_embeddings(current_config.type)
            self._current_embedding_config = current_config.model_copy()

        return self._embedding_client

    def update_milvus_config(self, new_config: MilvusSettings) -> str:
        """Update Milvus configuration and test connection"""
        # Test connection with new config
        old_config = settings.milvus
        settings.milvus = new_config

        try:
            server_version = test_milvus_connection()
            if not server_version:
                # Rollback on failure
                settings.milvus = old_config
                raise Exception("Failed to connect to Milvus with new configuration")

            # Force reinitialization on next access
            with self._lock:
                self._milvus_client = None
                self._current_milvus_config = None

            return server_version

        except Exception as e:
            # Rollback on failure
            settings.milvus = old_config
            raise e

    def update_embedding_config(self, new_config: EmbeddingSettings):
        """Update embedding configuration"""
        settings.embedding = new_config

        # Force reinitialization on next access
        with self._lock:
            self._embedding_client = None
            self._current_embedding_config = None
            # if the embedding configuration changes, we might also need to reinitialize Milvus
            self._milvus_client = None
            self._current_milvus_config = None

    def reset(self):
        """Reset all clients (useful for testing)"""
        with self._lock:
            self._milvus_client = None
            self._embedding_client = None
            self._current_milvus_config = None
            self._current_embedding_config = None


# Global instance
client_manager = ClientManager()
