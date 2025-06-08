from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders.parsers.pdf import PyPDFParser
from langchain_community.document_loaders.blob_loaders import Blob
from langchain.schema import Document
from typing import List


# TODO consider using a text splitter to handle large pages or documents e.g., RecursiveCharacterTextSplitter


def parse_pdf(content: bytes, filename: str) -> List[Document]:
    """Parse a single PDF document from bytes content."""
    parser = PyPDFParser()
    blob = Blob(data=content, path=filename, mime_type="application/pdf")
    return parser.parse(blob)
