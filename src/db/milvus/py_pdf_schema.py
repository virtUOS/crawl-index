from pymilvus import DataType

# if another pdf parser is used, the schema may need to be updated accordingly
pdf_metadata_schema = {
    "title": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "PDF title",
    },
    "subject": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "PDF subject",
    },
    "keywords": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "PDF keywords",
    },
    "producer": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "PDF producer",
    },
    "language": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "PDF language",
    },
    "creator": {
        "dtype": DataType.VARCHAR,
        "max_length": 1000,
        "nullable": True,
        "description": "PDF creator",
    },
    "creationdate": {
        "dtype": DataType.VARCHAR,
        "max_length": 32,
        "nullable": True,
        "description": "Creation date",
    },
    "author": {
        "dtype": DataType.VARCHAR,
        "max_length": 128,
        "nullable": True,
        "description": "Author",
    },
    "company": {
        "dtype": DataType.VARCHAR,
        "max_length": 128,
        "nullable": True,
        "description": "Company",
    },
    "moddate": {
        "dtype": DataType.VARCHAR,
        "max_length": 32,
        "nullable": True,
        "description": "Modification date",
    },
    "sourcemodified": {
        "dtype": DataType.VARCHAR,
        "max_length": 32,
        "nullable": True,
        "description": "Source modified",
    },
    "source": {
        "dtype": DataType.VARCHAR,
        "max_length": 256,
        "nullable": True,
        "description": "Source file path",
    },
    "total_pages": {
        "dtype": DataType.INT64,
        "nullable": True,
        "description": "Total pages",
    },
    "page": {
        "dtype": DataType.INT64,
        "nullable": True,
        "description": "Page number",
    },
    "page_label": {
        "dtype": DataType.VARCHAR,
        "max_length": 32,
        "nullable": True,
        "description": "Page label",
    },
}
