from src.embeddings.fast_embed import get_fast_embed_model
from src.embeddings.ollama_embed import get_ollama_embeddings
from src.config.models import EmbeddingType


def get_embeddings(type_embedding: EmbeddingType = "FastEmbed"):
    if type_embedding == "FastEmbed":
        return get_fast_embed_model()
    elif type_embedding == "Ollama":
        return get_ollama_embeddings()
    else:
        raise ValueError(f"Unknown embedding type: {type_embedding}")
