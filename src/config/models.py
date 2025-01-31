from pydantic import BaseModel
from typing import Optional


class CrawlSettings(BaseModel):
    """
    CrawlSettings is a model that defines the configuration settings for a web crawler.

    Attributes:
        start_url (str): The initial URL from which the crawler will start.
        max_urls_to_visit (int): The maximum number of URLs the crawler is allowed to visit.
        allowed_domains (list[str]): A list of domains that the crawler is allowed to visit.
    """

    start_url: str
    max_urls_to_visit: int
    allowed_domains: list[str]
    exclude_domains: Optional[list[str]] = []


class IndexingStorageSettings(BaseModel):
    """
    IndexingStorageSettings is a model for configuring storage settings related to indexing.

    Attributes:
        collection_name (str): The name of the collection where the data will be stored.
    """

    collection_name: str


# class MilvusConnection(BaseModel):
#     milvus_url: str
