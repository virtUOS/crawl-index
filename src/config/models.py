from pydantic import BaseModel
from typing import Optional, List, Literal, Type, Tuple, ClassVar
import os

EmbeddingType = Literal["FastEmbed", "Ollama"]


class RAGFlowSettings(BaseModel):
    """
    Configuration for RAGFlow settings.
    """

    base_url: Optional[str] = None
    api_key: Optional[str] = None
    collection_name: Optional[str] = None

    def model_post_init(self, context):
        if self.api_key is None:
            self.api_key = os.getenv("RAGFLOW_API_KEY")

    def validate_required_fields(self):
        if not all([self.base_url, self.api_key, self.collection_name]):
            raise ValueError(
                "RAGFlow configuration is incomplete. Required parameters could not be loaded from config.yml or environment file"
            )

    # TODO: test connnection here


class CrawlSettings(BaseModel):
    """Settings for web crawler behavior"""

    start_url: Optional[List[str]] = None
    max_urls_to_visit: Optional[int] = None
    allowed_domains: List[str] = None
    crawl_payload: Optional[dict] = (
        None  # TODO : requires special validation, use the crawl4ai schema
    )

    def validate_required_fields(self):
        # Validate required fields
        if not all(
            [
                self.start_url,
                self.allowed_domains,
                self.max_urls_to_visit,
                self.crawl_payload,
            ]
        ):
            raise ValueError(
                "Crawl configuration is incomplete. Please provide start_url, allowed_domains, "
                "max_urls_to_visit, and crawl_payload. Use the config.yaml file to set these values or e.g., curl."
            )


class CrawlIngestSettings(BaseModel):
    """Settings for crawling and ingesting web content"""

    crawl_settings: CrawlSettings
    ragflow_settings: Optional[RAGFlowSettings]  # default to settings.ragflow if None


class ReCrawlSettings(BaseModel):
    """Settings for re-crawling existing URLs in the database."""

    crawl_payload: Optional[dict] = None  # Custom payload for the crawl API
    ragflow_settings: Optional[RAGFlowSettings] = (
        None  # RAGFlow settings for re-ingestion
    )


class MilvusSettings(BaseModel):
    """Settings for Milvus vector database"""

    uri: Optional[str] = "http://localhost:19530"
    host: Optional[str] = None
    port: int = 19530
    token: Optional[str] = "root:Milvus"
    collection_name: str = "my_documents"
    collection_description: str = "A collection of documents"
    enable_dynamic_field: bool = False
    auto_id: bool = False


class EmbeddingConnectionSettings(BaseModel):
    """Settings for Ollama embeddings"""

    model_name: str = (
        "intfloat/multilingual-e5-large"  # e.g., "llama2", "mistral", "intfloat/multilingual-e5-large"
    )
    base_url: Optional[str] = "http://localhost:11434"
    headers: Optional[dict] = None


class EmbeddingSettings(BaseModel):
    """Settings for text embedding"""

    type: EmbeddingType = "FastEmbed"
    connection_settings: EmbeddingConnectionSettings
    chunk_size: int = (
        1800  # Size of each chunk in characters (Only crawler uses a text splitter)
    )
    chunk_overlap: int = 50
    batch_size: int = 256
