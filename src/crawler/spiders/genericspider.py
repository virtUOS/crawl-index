# to run the spider use the following command: scrapy crawl genericspider -a start_url=https://teaching-toolbox.uni-osnabrueck.de/


# mycrawler/spiders/genericspider.py
import scrapy
from urllib.parse import urlparse
from bs4 import BeautifulSoup


class GenericSpider(scrapy.Spider):
    name = "genericspider"

    def __init__(self, start_url=None, max_links=10, *args, **kwargs):
        super(GenericSpider, self).__init__(*args, **kwargs)
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

        # Extract metadata
        last_updated = response.headers.get("Last-Modified", b"").decode("utf-8")
        title = response.xpath("//title/text()").get()

        # Extract text without HTML tags using BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
        text_content = soup.get_text(separator=" ", strip=True)

        # Yield the text content and metadata
        yield {
            "url": response.url,
            "html": response.text,
            "text": text_content,
            "last_updated": last_updated,
            "title": title,
        }

        self.link_count += 1

        # Recursively follow all the links on the page
        links = response.css("a::attr(href)").getall()
        for link in links:
            yield response.follow(link, self.parse)
