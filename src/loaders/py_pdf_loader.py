from typing import List
from langchain_community.document_loaders.parsers.pdf import PyPDFParser
from langchain_community.document_loaders.blob_loaders import Blob
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from src.config.core_config import settings


def parse_pdf(content: bytes, filename: str) -> List[Document]:
    """
    Parse a PDF document and split it into chunks.

    Args:
        content: Raw bytes of the PDF file
        filename: Name of the file being processed

    Returns:
        List of Document objects after splitting
    """
    # Parse PDF into documents
    parser = PyPDFParser()
    blob = Blob(data=content, path=filename, mimetype="application/pdf")
    documents = parser.parse(blob)

    # # TODO Create text splitter with configured chunk size
    # text_splitter = RecursiveCharacterTextSplitter(
    #     chunk_size=settings.embedding.chunk_size,
    #     chunk_overlap=settings.embedding.chunk_overlap,
    # )

    # # Split documents into chunks
    # split_docs = text_splitter.split_documents(documents)

    # return split_docs
    return documents
