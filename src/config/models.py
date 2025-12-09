from pydantic import BaseModel
from typing import Optional, List, Literal, Type, Tuple, ClassVar

EmbeddingType = Literal["FastEmbed", "Ollama"]


class RAGFlowSettings(BaseModel):
    """
    Configuration for RAGFlow settings.
    """

    base_url: str
    chunk_size: int = 10  # Number of chunks to retrieve per request
    collection_name: Optional[str] = None


class FirstCrawlSettings(BaseModel):
    """Settings for the initial web crawl, FastAPI-based crawler."""

    start_url: Optional[List[str]] = None
    max_urls_to_visit: Optional[int] = None
    crawl_payload: Optional[dict] = None


class CrawlSettings(BaseModel):
    """Settings for web crawler behavior"""

    start_url: Optional[List[str]] = None
    max_urls_to_visit: Optional[int] = None
    allowed_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None
    debug: bool = False
    target_elements: Optional[List[str]] = None
    check_content_changed: bool = (
        True  # If True, checks if the content has changed before crawling. Useful for avoiding unnecessary re-crawling of unchanged pages.
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
