# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


import json
import os
import pickle
from uuid import uuid4

import chromadb
from chromadb import Client
from chromadb.config import Settings
from itemadapter import ItemAdapter
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from scrapy.settings import Settings as ScrapySettings
from .gen_doc import generate_documents
from indexer.chroma_utils import ChromaDbUtil


class ChromaDbPipeline:
    collection_name = ScrapySettings.get("CHROMA_COLLECTION_NAME", "scrapy_index")

    def __init__(self, batch_size=ScrapySettings.BATCH_SIZE):
        self.batch_size = batch_size
        self.items = []

    def close_spider(self, spider):
        if self.items:
            self.save_items()

    def process_item(self, item, spider):
        self.items.append(item)
        if len(self.items) >= self.batch_size:
            self.save_items()
            self.items = []  # Reset items after saving

        return item

    def save_items(self):
        # Generate documents from items
        docs = []
        # metadata needs to be of type bool, str, int or float
        for item in self.items:
            docs.append(
                Document(page_content=item["page_content"], metadata=dict(item))
            )

        # Assign unique IDs to documents
        uuids = [str(uuid4()) for _ in range(len(docs))]

        # TODO enfore unique urls (add a unique field)
        # Add documents to ChromaDB

        chroma_db = ChromaDbUtil.get_instance()
        chroma_db.vector_store_from_client.add_documents(documents=docs, ids=uuids)
        # collection = self.client.get_collection(name=self.collection_name)
        ##  get the first embedding
        # collection.peek()['embeddings'][0]
        # collection.add(documents=docs, ids=uuids)
