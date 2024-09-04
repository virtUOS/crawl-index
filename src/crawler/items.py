# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy
from typing import Dict, Union, List, Optional
from pydantic import validate_call
import re
import hashlib


# TODO collect when the page was last updated
class WebsiteIndexItem(scrapy.Item):
    url = scrapy.Field()
    title = scrapy.Field()
    meta_keywords = scrapy.Field()  # The meta keywords tag content
    meta_description = scrapy.Field()  # The meta description tag content
    page_content = scrapy.Field()
    h1_tag = scrapy.Field()
    h2_tags = scrapy.Field()
    word_count = scrapy.Field()
    last_updated = scrapy.Field()  # The last modified date of the page
    hash_content = scrapy.Field()  # A hash value of the main content to detect changes.
    links = scrapy.Field()

    @staticmethod
    @validate_call
    def get_field_content(content: Optional[Union[List, str, int, float]]) -> str:

        if content is None:
            return ""
        if isinstance(content, list):
            if not content:
                return ""
            content = ", ".join(content)
        elif isinstance(content, (int, float)):
            return content

        # for the items to be saved in the database, we need to ensure the types are the ones supported by the database
        content = re.sub(r"\s+", " ", content).strip()  # remove extra whitespace
        return content

    @staticmethod
    def get_content_hash(content):
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def __setitem__(self, key, value):
        if key in self.fields:
            self._values[key] = WebsiteIndexItem.get_field_content(value)
            if key == "page_content":
                self._values["word_count"] = len(self._values[key].split())
                self._values["hash_content"] = WebsiteIndexItem.get_content_hash(
                    self._values[key]
                )

        else:
            raise KeyError(f"{self.__class__.__name__} does not support field: {key}")


# for m in meta:
#     for key, value in m.items():
#         if not isinstance(key, str):
#             print(f'key found: {key}')
#         # isinstance(True, int) evaluates to True, so we need to check for bools separately
#         if not isinstance(value, bool) and not isinstance(value, (str, int, float)):
#             print(f'value found: {value}')
