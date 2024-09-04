# to run the spider use the following command: scrapy crawl genericspider -a start_url=https://teaching-toolbox.uni-osnabrueck.de/


# mycrawler/spiders/genericspider.py
import scrapy
from urllib.parse import urlparse, urljoin
import re
from ..items import WebsiteIndexItem


class GenericSpider(scrapy.Spider):
    name = "genericspider"

    def __init__(self, start_url=None, max_links=5, *args, **kwargs):
        super(GenericSpider, self).__init__(*args, **kwargs)
        if not start_url:
            start_url = self.settings.get("START_URL", [])
            if not start_url:
                raise ValueError("You must provide a start_url argument.")

        self.start_urls = [start_url]
        self.allowed_domains = [urlparse(start_url).netloc]
        self.max_links = int(max_links)
        self.link_count = 0

    def parse(self, response):
        if self.link_count >= self.max_links:
            self.crawler.engine.close_spider(self, "Reached max_links limit")
            return

        # Extract all text content while maintaining the order
        text_elements = response.xpath("//body//text()").getall()
        text_elements = [
            element.strip() for element in text_elements if element.strip()
        ]
        text = " ".join(text_elements)

        # Extract the Last-Modified header
        last_modified = response.headers.get("Last-Modified", None)
        if last_modified:
            last_modified = last_modified.decode("utf-8")

        item = WebsiteIndexItem()

        item["url"] = response.url
        item["title"] = response.css("title::text").get().strip()
        item["last_updated"] = last_modified
        item["meta_keywords"] = response.css(
            'meta[name="keywords"]::attr(content)'
        ).get()
        item["meta_description"] = response.css(
            'meta[name="description"]::attr(content)'
        ).get()
        item["page_content"] = text

        item["h1_tag"] = response.css("h1::text").getall()

        item["h2_tags"] = response.css("h2::text").getall()

        item["links"] = response.css("a::attr(href)").getall()

        yield item

        self.link_count += 1

        # Recursively follow all the links on the page
        links = response.css("a::attr(href)").getall()
        for link in links:
            absolute_url = urljoin(response.url, link)
            if urlparse(absolute_url).netloc in self.allowed_domains:
                yield response.follow(absolute_url, self.parse)
