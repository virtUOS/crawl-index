from langchain_ollama import OllamaEmbeddings
from src.config.core_config import settings


def get_ollama_embeddings():

    embeddings = OllamaEmbeddings(
        model=settings.embedding.connection_settings.model_name,
        base_url=settings.embedding.connection_settings.base_url,
        client_kwargs=settings.embedding.connection_settings.headers,
    )

    return embeddings
