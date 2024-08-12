# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


import json
import chromadb
from chromadb import Client
from itemadapter import ItemAdapter
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings


# https://python.langchain.com/docs/integrations/text_embedding/fastembed
embeddings = FastEmbedEmbeddings(model_name="intfloat/multilingual-e5-large")
# load or create db
# db = Chroma(persist_directory="./chromadb/chroma_index", embedding_function=embeddings)
# db = Chroma(client=client, embedding_function=embeddings)


class ChromaDbPipeline:
    collection_name = "scrapy_index"

    def __init__(self, chromadb_uri, model_path):
        self.chromadb_uri = chromadb_uri
        self.model_path = model_path

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(
            chromadb_uri=settings.get("CHROMADB_URI"),
        )

    def open_spider(self, spider):
        self.client = Client(self.chromadb_uri)
        self.collection = self.client[self.collection_name]

        # Load your local AI model
        self.model = FastEmbedEmbeddings(model_name="intfloat/multilingual-e5-large")

    def close_spider(self, spider):
        self.client.close()

    def process_item(self, item, spider):
        html_content = item["html"]
        url = item["url"]
        last_updated = item.get("last_updated", "")
        title = item.get("title", "")

        # Use AI model to extract and summarize text from HTML
        prompt = f"Extract and summarize the text from this HTML content. The final result should not contain any HTML tags.\n\n{html_content}"
        summary = self.model.summarize(prompt)

        # Construct metadata
        metadata = {
            "url": url,
            "title": title,
            "summary": summary,
            "last_updated": last_updated,
        }

        # Save summary and metadata to ChromaDB
        self.collection.add_document(text=summary, metadata=metadata)

        return item  # Must return the item for Scrapy
