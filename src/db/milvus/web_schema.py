from pymilvus import DataType


metadata_schema = {
    "url": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "description": "URL of the webpage",
    },
    "num_chunks": {
        "dtype": DataType.INT64,
        "description": "Number of chunks the webpage was split into",
    },
    "response_headers_date": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "Date of the response headers",
    },
    "response_headers_content_language": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "Content language of the response headers",
    },
    "response_headers_etag": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "Etag of the response headers",
    },
    "response_headers_last_modified": {
        "dtype": DataType.VARCHAR,
        "nullable": True,
        "max_length": 1000,
        "description": "Last modified date of the response headers",
    },
    "internal_links": {
        "dtype": DataType.ARRAY,
        "element_type": DataType.VARCHAR,
        "max_length": 65535,
        "max_capacity": 1000,
        "description": "Internal links found on the webpage",
    },
    "external_links": {
        "dtype": DataType.ARRAY,
        "element_type": DataType.VARCHAR,
        "max_length": 65535,
        "max_capacity": 1000,
        "description": "External links found on the webpage",
    },
    "title": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "Title of the webpage",
    },
    "meta_keywords": {
        "dtype": DataType.VARCHAR,
        "nullable": True,
        "max_length": 1000,
        "description": "Keywords of the webpage",
    },
}
