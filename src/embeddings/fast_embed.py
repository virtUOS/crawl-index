# Configurations
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from src.config.core_config import settings


# Initialize embeddings with configuration
def get_fast_embed_model():
    return FastEmbedEmbeddings(
        model_name=settings.embedding.connection_settings.model_name,
    )
