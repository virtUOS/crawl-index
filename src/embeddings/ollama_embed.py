from langchain_ollama import OllamaEmbeddings
from src.config.core_config import settings


def get_ollama_embeddings() -> OllamaEmbeddings:
    """
    Get Ollama embeddings configured with the settings from the application.
    Returns:
        OllamaEmbeddings: Configured Ollama embeddings instance.
    """

    embeddings = OllamaEmbeddings(
        model=settings.embedding.connection_settings.model_name,
        base_url=settings.embedding.connection_settings.base_url,
        client_kwargs={
            "headers": {
                "Authorization": settings.embedding.connection_settings.headers[
                    "Authorization"
                ]
            }
        },
    )

    return embeddings
