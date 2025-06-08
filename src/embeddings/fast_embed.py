# Configurations
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
DEFAULT_DATA_DIR = "./data/documents/"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 0
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

# Initialize embeddings
embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)
