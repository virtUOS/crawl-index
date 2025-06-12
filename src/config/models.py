from pydantic import BaseModel
from typing import Optional, List, Literal, Type, Tuple, ClassVar

EmbeddingType = Literal["FastEmbed", "Ollama"]


class CrawlSettings(BaseModel):
    """Settings for web crawler behavior"""

    start_url: str
    max_urls_to_visit: int
    allowed_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None
    debug: bool = False
    target_elements: Optional[List[str]] = None


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
    chunk_size: int = 1000
    chunk_overlap: int = 0
    batch_size: int = 256
