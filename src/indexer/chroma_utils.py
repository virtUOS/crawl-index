# chroma_utils.py

import chromadb
from chromadb import Client
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_community.vectorstores import Chroma
from chromadb.config import Settings
from scrapy.settings import Settings as ScrapySettings
import logging
from scrapy.utils.log import configure_logging

configure_logging()
logger = logging.getLogger("scrapy")


class ChromaDbUtil:
    _instance = None

    def __init__(self):
        if ChromaDbUtil._instance is None:
            self.collection_name = ScrapySettings.get(
                "CHROMA_COLLECTION_NAME", "scrapy_index"
            )
            try:
                # if running in a container
                self.client = chromadb.HttpClient(
                    host="chromadb", settings=Settings(allow_reset=True)
                )
            except Exception as e:
                self.client = chromadb.HttpClient(settings=Settings(allow_reset=True))
                logger.error(f"Error initializing ChromaDB client: {e}")

            self.embeddings = FastEmbedEmbeddings(
                model_name="intfloat/multilingual-e5-large"
            )
            # self.collection = client.get_or_create_collection(self.collection_name)

            self.vector_store_from_client = Chroma(
                client=self.client,
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
            )

            ChromaDbUtil._instance = self

    @staticmethod
    def get_instance():
        if ChromaDbUtil._instance is None:
            ChromaDbUtil()
        return ChromaDbUtil._instance
