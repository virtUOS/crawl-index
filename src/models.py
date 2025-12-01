from pydantic import BaseModel
from typing import Optional, List, Dict


class CrawlReusltsCustom(BaseModel):

    url: str
    html: Optional[str] = None
    cleaned_html: Optional[str] = None
    media: Dict[str, List[Dict]] = {}
    links: Optional[dict] = None
    downloaded_files: Optional[List[str]] = None
    markdown: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[str] = None
    author: Optional[str] = None
    status_code: Optional[int] = None
    response_headers: Optional[dict] = None
