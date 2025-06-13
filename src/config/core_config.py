from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from typing import Type, Tuple, Literal, ClassVar, Optional
import threading
import colorama
import types
from langchain_milvus import Milvus
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.async_database import async_db_manager

from .models import (
    CrawlSettings,
    MilvusSettings,
    EmbeddingSettings,
)
from src.logger.crawl_logger import logger

# Import custom crawl methods
from src.crawl_ai.custom_crawl import (
    _check_content_changed,
    arun,
    custom_acache_url,
    custom_aget_cached_url,
    custom_ainit_db,
    delete_cached_result,
)

colorama.init(strip=True)

# Apply custom crawl methods
AsyncWebCrawler.arun = arun
AsyncWebCrawler.delete_cached_result = delete_cached_result
AsyncWebCrawler._check_content_changed = _check_content_changed

async_db_manager.ainit_db = types.MethodType(custom_ainit_db, async_db_manager)
async_db_manager.acache_url = types.MethodType(custom_acache_url, async_db_manager)
async_db_manager.aget_cached_url = types.MethodType(
    custom_aget_cached_url, async_db_manager
)

CrawlerRunConfig.check_content_changed = True
CrawlerRunConfig.head_request_timeout = 3.0
CrawlerRunConfig.default_cache_ttl_seconds = 60 * 60 * 72  # 72 hours


class Settings(BaseSettings):
    """
    Unified settings and client management class.

    This singleton class handles both configuration and client lifecycle management,
    eliminating the need for a separate ClientManager.
    """

    _instance: ClassVar[Optional["Settings"]] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    # Configuration fields
    crawl_settings: Optional[CrawlSettings] = None
    milvus: Optional[MilvusSettings] = None
    embedding: Optional[EmbeddingSettings] = None

    # Private client instances (not serialized)
    _milvus_client: Optional[Milvus] = None
    _embedding_client = None
    _crawler: Optional[AsyncWebCrawler] = None
    _crawl_config: Optional[CrawlerRunConfig] = None
    _session_id: str = "session1"

    # Configuration snapshots for change detection
    _milvus_snapshot: Optional[MilvusSettings] = None
    _embedding_snapshot: Optional[EmbeddingSettings] = None
    _crawl_snapshot: Optional[CrawlSettings] = None

    model_config = SettingsConfigDict(yaml_file="config.yaml", env_file=".env")

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Settings, cls).__new__(cls)
        return cls._instance

    def __init__(self, **data):
        if not hasattr(self, "_initialized"):
            super().__init__(**data)
            self._initialized = True
            logger.debug(f"Settings initialized: {self.model_dump_json()}")

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
            logger.info(
                f"Initializing/reinitializing {self.embedding.type} embedding client"
            )
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

    def get_crawler(self) -> tuple[AsyncWebCrawler, CrawlerRunConfig, str]:
        """Get or create crawler instance with lazy initialization"""
        if not self.crawl_settings:
            raise ValueError("Crawl configuration not set")

        if self._config_changed(self.crawl_settings, self._crawl_snapshot):
            logger.info("Initializing/reinitializing crawler")

            self._session_id = "session1"

            browser_config = BrowserConfig(
                headless=True,
                verbose=True,
            )

            self._crawl_config = CrawlerRunConfig(
                cache_mode=CacheMode.ENABLED,
                target_elements=self.crawl_settings.target_elements or None,
                scan_full_page=True,
                verbose=self.crawl_settings.debug,
                exclude_domains=self.crawl_settings.exclude_domains or [],
                stream=False,
            )

            self._crawler = AsyncWebCrawler(config=browser_config)
            self._crawl_snapshot = self.crawl_settings.model_copy()

        return self._crawler, self._crawl_config, self._session_id

    def update_milvus_config(self, new_config: MilvusSettings) -> str:
        """Update Milvus configuration and test connection"""
        old_config = self.milvus
        self.milvus = new_config

        try:
            from src.db.clients import test_milvus_connection

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

    def update_crawl_config(self, new_config: CrawlSettings):
        """Update crawl configuration"""
        self.crawl_settings = new_config

        with self._lock:
            self._crawler = None
            self._crawl_snapshot = None

    def reset_clients(self):
        """Reset all clients (useful for testing)"""
        with self._lock:
            self._milvus_client = None
            self._embedding_client = None
            self._crawler = None
            self._milvus_snapshot = None
            self._embedding_snapshot = None
            self._crawl_snapshot = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (YamlConfigSettingsSource(settings_cls), dotenv_settings)


settings = Settings()
