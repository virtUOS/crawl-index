from pydantic import BaseModel
from typing import Optional, List, Dict
from crawl4ai.models import CrawlResult


class CrawlReusltsCustom(BaseModel):

    url: str
    html: Optional[str] = None
    cleaned_html: Optional[str] = None
    media: Dict[str, List[Dict]] = {}
    links: Optional[dict] = None
    downloaded_files: Optional[List[str]] = None
    markdown: Optional[str] = None
    formatted_markdown: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[str] = None
    author: Optional[str] = None
    status_code: Optional[int] = None
    response_headers: Optional[dict] = None
    is_content_useful: Optional[bool] = None
    is_content_pdf: Optional[bool] = None

    def model_post_init(self, __context):
        if self.markdown:
            self.formatted_markdown = self._formatted_markdown()
            self.is_content_useful = self._is_content_useful()
            self.is_content_pdf = self._is_content_pdf()

    def _is_content_pdf(self) -> bool:

        content_type = self.response_headers.get("content-type", "")
        return "application/pdf" in content_type.lower()

    def _formatted_markdown(self) -> str:
        md_content = f"""
---
title: "{self.title or ''}"
url: "{self.url}"
description: "{self.description or ''}"
keywords: "{self.keywords or ''}"
author: "{self.author or ''}"
---

### Source: {self.url}\n\n{self.markdown}
"""
        return md_content

    def _is_content_useful(
        self,
    ) -> bool:
        """Check if the HTML content is useful (not empty or boilerplate)."""
        # Simple heuristic: check length and presence of meaningful tags

        if len(self.markdown.strip()) < 700:
            print(f"Skipping short document: {self.title}")

            return False

        if (
            "events" in self.title.lower()
            or "event" in self.title.lower()
            or "veranstaltungen" in self.title.lower()
        ):
            if (
                "no events available" in self.title.lower()
                or "keine veranstaltungen verfügbar" in self.markdown.lower()
            ):
                print(f"Skipping document with no content: {self.title}")

                return False

        return True
