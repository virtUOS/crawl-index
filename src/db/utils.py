import hashlib
from typing import List


def generate_unique_id(doc_name: str, index: int) -> str:
    """
    Generate a unique ID for a document based on its name and index.

    Args:
        doc_name (str): The name of the document.
        index (int): The index of the document in the list.

    Returns:
        str: A SHA-256 hash representing the unique ID.
    """
    unique_string = f"[{index}]{doc_name}"
    return hashlib.sha256(unique_string.encode()).hexdigest()


def generate_unique_ids(doc_name: str, num_documents: int) -> List[str]:
    """
    Generate a list of unique IDs for a document based on its name and index.

    Args:
        doc_name (str): The name of the document.
        num_documents (int): The total number of documents.

    Returns:
        List[str]: A list of SHA-256 hashes representing the unique IDs.
    """
    return [generate_unique_id(doc_name, index) for index in range(num_documents)]
