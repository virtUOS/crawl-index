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


class IndexingStorageSettings(BaseModel):
    """
    IndexingStorageSettings is a model for configuring storage settings related to indexing.

    Attributes:
        collection_name (str): The name of the collection where the data will be stored.
        save_to_pickle (Optional[bool]): A flag indicating whether to save the data to a pickle file. Defaults to False.
        save_to_pickle_interval (Optional[int]): The interval at which data should be saved to a pickle file, in terms of visited links. Defaults to 1000.
    """

    collection_name: str
    save_to_pickle: Optional[bool] = False
    save_to_pickle_interval: Optional[int] = 1000


# class MilvusConnection(BaseModel):
#     milvus_url: str
