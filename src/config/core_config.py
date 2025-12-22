import threading
import colorama
import types
import yaml

from typing import Optional, ClassVar, Dict, Any
from pathlib import Path
from langchain_milvus import Milvus


from .models import (
    CrawlSettings,
    MilvusSettings,
    EmbeddingSettings,
    RAGFlowSettings,
    ReCrawlSettings,
)

from src.logger.crawl_logger import logger
from ragflow_sdk import RAGFlow


colorama.init(strip=True)


class Settings:
    """
    Unified settings and client management class.

    This singleton class handles both configuration and client lifecycle management,
    eliminating the need for a separate ClientManager.
    """

    _instance: ClassVar[Optional["Settings"]] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_initialized"):
            # Configuration fields
            self.crawl_settings: Optional[CrawlSettings] = None
            self.milvus: Optional[MilvusSettings] = None
            self.embedding: Optional[EmbeddingSettings] = None

            # Private client instances (not serialized)
            self._milvus_client: Optional[Milvus] = None
            self._embedding_client = None

            # Configuration snapshots for change detection
            self._milvus_snapshot: Optional[MilvusSettings] = None
            self._embedding_snapshot: Optional[EmbeddingSettings] = None
            self._crawl_snapshot: Optional[CrawlSettings] = None

            # First Load configuration from YAML file (They can be overridden through respective endpoints)
            self._load_config()
            self._initialized = True
            logger.debug(f"Settings initialized: {self._dump_config()}")

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Settings, cls).__new__(cls)
        return cls._instance

    def _load_config(self):
        """Load configuration from config.yaml"""
        # Load from config.yaml
        config_path = Path("config.yaml")
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config_data = yaml.safe_load(f) or {}

                # Parse configuration sections
                if "crawl_settings" in config_data:
                    self.crawl_settings = CrawlSettings(**config_data["crawl_settings"])

                if "milvus" in config_data:
                    self.milvus = MilvusSettings(**config_data["milvus"])

                if "embedding" in config_data:
                    self.embedding = EmbeddingSettings(**config_data["embedding"])

                if "ragflow" in config_data:
                    self.ragflow = RAGFlowSettings(**config_data["ragflow"])

                if "re_crawl_settings" in config_data:
                    self.re_crawl_settings = ReCrawlSettings(
                        **config_data["re_crawl_settings"]
                    )

                if self.ragflow and self.milvus:
                    raise ValueError(
                        "Cannot have both RAGFlow and Milvus configurations set at the same time."
                    )

                logger.info("Configuration loaded from config.yaml")
            except Exception as e:
                logger.warning(f"Failed to load config.yaml: {e}")
        else:
            logger.info("config.yaml not found, using defaults")

    def _dump_config(self) -> str:
        """Dump current configuration as JSON string for logging"""
        config = {}
        if self.crawl_settings:
            config["crawl_settings"] = self.crawl_settings.model_dump()
        if self.milvus:
            config["milvus"] = self.milvus.model_dump()
        if self.embedding:
            config["embedding"] = self.embedding.model_dump()
        if self.ragflow:
            config["ragflow"] = self.ragflow.model_dump()

        import json

        return json.dumps(config, indent=2)

    def model_dump_json(self) -> str:
        """Compatibility method for existing logging code"""
        return self._dump_config()

    def _config_changed(self, current_config, snapshot) -> bool:
        """Check if configuration has changed"""
        if snapshot is None:
            return True
        return current_config != snapshot

    def get_embedding_client(self):
        """Get or create embedding client instance with lazy initialization"""
        if not self.embedding:
            raise ValueError("Embedding configuration not set")

        if self._config_changed(self.embedding, self._embedding_snapshot):
            logger.info(f"Initializing/reinitializing embedding client")
            from src.embeddings.main import get_embeddings

            self._embedding_client = get_embeddings(self.embedding.type)
            self._embedding_snapshot = self.embedding.model_copy()
            # Invalidate Milvus client when embedding changes
            self._milvus_client = None
            self._milvus_snapshot = None

        return self._embedding_client

    def get_milvus_client(
        self, schema: dict, collection_name: Optional[str] = None
    ) -> Milvus:
        """Get or create Milvus client instance with lazy initialization"""
        if not self.milvus:
            raise ValueError("Milvus configuration not set")

        effective_config = self.milvus
        if collection_name and collection_name != self.milvus.collection_name:
            effective_config = self.milvus.model_copy()
            effective_config.collection_name = collection_name
            # For custom collection names, create a new instance without caching
            return self._create_milvus_client(effective_config, schema)

        if self._config_changed(self.milvus, self._milvus_snapshot):
            logger.info("Initializing/reinitializing Milvus client")
            self._milvus_client = self._create_milvus_client(effective_config, schema)
            self._milvus_snapshot = self.milvus.model_copy()

        return self._milvus_client

    def _create_milvus_client(self, config: MilvusSettings, schema: dict) -> Milvus:
        """Create Milvus client with given configuration"""
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

    def update_milvus_config(self, new_config: MilvusSettings) -> str:
        """Update Milvus configuration and test connection"""
        old_config = self.milvus
        self.milvus = new_config

        try:
            from src.db.milvus.client import test_milvus_connection

            server_version = test_milvus_connection()
            if not server_version:
                self.milvus = old_config
                raise Exception("Failed to connect to Milvus with new configuration")

            # Invalidate cached client
            with self._lock:
                self._milvus_client = None
                self._milvus_snapshot = None

            return server_version

        except Exception as e:
            self.milvus = old_config
            raise e

    def update_embedding_config(self, new_config: EmbeddingSettings):
        """Update embedding configuration"""
        self.embedding = new_config

        with self._lock:
            self._embedding_client = None
            self._embedding_snapshot = None
            # Invalidate Milvus client since it depends on embedding
            self._milvus_client = None
            self._milvus_snapshot = None

    def reset_clients(self):
        """Reset all clients (useful for testing)"""
        with self._lock:
            self._milvus_client = None
            self._embedding_client = None
            self._milvus_snapshot = None
            self._embedding_snapshot = None


settings = Settings()
