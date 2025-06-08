import argparse
import zipfile
import io
import os
from typing import Dict, List, Union, Annotated, Optional
from pydantic import BaseModel
import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_community.document_loaders.parsers.pdf import PyPDFParser
from langchain_community.document_loaders.blob_loaders import Blob
from src.db.process_files import create_db_from_documents

# Add PDF processing
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

app = FastAPI()


class MilvusConfig(BaseModel):
    url: str
    token: Optional[str] = None
    collection_name: str
    collection_description: str = "A collection of text files"


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model_name: str = "nomic-embed-text"
    headers: Dict[str, str] = {}
    timeout: int = 60


class AppConfig(BaseModel):
    milvus: Optional[MilvusConfig] = None
    ollama: Optional[OllamaConfig] = None


# Global configuration storage
app_config = AppConfig()


class EmbedTextFilesModel(BaseModel):
    collection_name: str = "text_files"
    collection_description: str = "A collection of text files"
    batch_size: int = 256


class ConfigResponse(BaseModel):
    message: str
    config: Union[MilvusConfig, OllamaConfig]


@app.get("/")
def read_root():
    print()
    return {"message": "Welcome to the Text Milvus DB Embedding API"}


@app.post("/config/milvus", response_model=ConfigResponse)
async def configure_milvus(config: MilvusConfig):
    """Configure Milvus database connection and collection settings."""
    app_config.milvus = config
    return ConfigResponse(
        message="Milvus configuration updated successfully",
        config=config,
    )


@app.post("/config/ollama", response_model=ConfigResponse)
async def configure_ollama(config: OllamaConfig):
    """Configure Ollama embedding model settings."""
    app_config.ollama = config
    return ConfigResponse(
        message="Ollama configuration updated successfully",
        config=config,
    )


@app.get("/config")
async def get_config():
    """Get current configuration settings."""
    return {"milvus": app_config.milvus, "ollama": app_config.ollama}


"""
# files are uploaded as form data. vector db configuration is passed as Form  data.
Example of how to use this endpoint with curl:
```bash
curl -X POST "http://127.0.0.1:8000/embed-text-files/" \
  -F "files=@/app/data/docs_test/Allgemeine-PO-Bachelor-Master_2020-06.pdf" \
```
"""


@app.post("/embed-text-files/")
async def embed_text_files(
    files: List[UploadFile] = File(...),
):

    for file in files:
        content = await file.read()

        if file.filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content), "r") as zip_ref:
                for file_info in zip_ref.infolist():
                    if not file_info.is_dir() and file_info.filename.endswith(".pdf"):
                        with zip_ref.open(file_info) as extracted_file:
                            pdf_content = extracted_file.read()
                            create_db_from_documents(pdf_content, file_info.filename)

        elif file.filename.endswith(".pdf"):
            documents = create_db_from_documents(content, file.filename)

        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported file type: {file.filename}"
            )

    return {
        "message": f"Processed {len(all_documents)} documents",
        "documents": [
            {
                "page_content": doc.page_content[:100] + "...",
                "metadata": doc.metadata,
            }
            for doc in all_documents
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the FastAPI application.")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=8000)
