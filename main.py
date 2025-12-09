import argparse
import zipfile
import io

from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, File, UploadFile, status, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.db.process_files import create_db_from_documents
from src.logger.crawl_logger import logger
from src.config.core_config import settings
from src.config.models import (
    MilvusSettings,
    EmbeddingSettings,
    CrawlSettings,
    FirstCrawlSettings,
)
import asyncio
from src.crawl_ai.first_crawl import CrawlApp
from tqdm import tqdm

app = FastAPI(
    title="Document Processing API",
    description="API for processing Documents and Web Crawling with Vector Embeddings (Milvus, RAGFlow)",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Specify your allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create API v1 router
api_v1_router = APIRouter(prefix="/api/v1")


class ProcessingResponse(BaseModel):
    """Response model for file processing endpoints"""

    status: str
    message: str
    details: Dict


class ConfigurationResponse(BaseModel):
    """Response model for configuration endpoints"""

    status: str
    message: str
    current_config: Dict


@app.get("/")
def read_root():
    """Root endpoint returning API information"""
    return {
        "status": "active",
        "message": "Document Processing API",
        "version": "1.0.0",
    }


@api_v1_router.get("/config")
async def get_current_config():
    """Get current configuration for both Milvus and embeddings"""
    current_config = {}

    if settings.milvus:
        current_config["milvus"] = settings.milvus.model_dump()
    if settings.embedding:
        current_config["embedding"] = settings.embedding.model_dump()
    if settings.crawl_settings:
        current_config["crawl_settings"] = settings.crawl_settings.model_dump()

    return ConfigurationResponse(
        status="success",
        message="Current configuration retrieved successfully",
        current_config=current_config,
    )


@api_v1_router.post("/config/milvus", response_model=ConfigurationResponse)
async def configure_milvus(config: MilvusSettings):
    """
    Configure Milvus settings at runtime.
    This will override settings from config.yml until application restart.
    Example (Milvus running on docker standalone service):
    bash ```
        curl -X POST http://localhost:8000/config/milvus \
    -H "Content-Type: application/json" \
    -d '{
        "host": "standalone",
        "port": 19530,
        "token": "root:Milvus",
        "collection_name": "documents",
        "collection_description": "A collection of PDF documents",
        "enable_dynamic_field": false,
        "auto_id": false
    }'```

    """
    try:
        server_version = settings.update_milvus_config(config)

        return ConfigurationResponse(
            status="success",
            message=f"Milvus configuration updated successfully. Server version: {server_version}",
            current_config={"milvus": settings.milvus.model_dump()},
        )
    except Exception as e:
        logger.error(f"Failed to update Milvus configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to update Milvus configuration",
                "error": str(e),
            },
        )


@api_v1_router.post("/config/embedding", response_model=ConfigurationResponse)
async def configure_embedding(config: EmbeddingSettings):
    """
    Configure embedding settings at runtime.
    This will override settings from config.yml until application restart.
    Example (using FastEmbed):
    bash
    ```
    curl -X POST http://localhost:8000/config/embedding \
    -H "Content-Type: application/json" \
    -d '{
        "type": "FastEmbed",
        "connection_settings": {
            "model_name": "intfloat/multilingual-e5-large",
            }
    }'```
    """
    try:
        settings.update_embedding_config(config)

        return ConfigurationResponse(
            status="success",
            message="Embedding configuration updated successfully",
            current_config={"embedding": settings.embedding.model_dump()},
        )
    except Exception as e:
        logger.error(f"Failed to update embedding configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to update embedding configuration",
                "error": str(e),
            },
        )


@api_v1_router.post("/crawl_embed", response_model=ProcessingResponse)
async def crawl_embed(config_start: FirstCrawlSettings):
    """
    Configure crawl settings at runtime.
    This will override settings from config.yml until application restart.
    The crawl_payload should be structured as per the Crawl4AI API documentation: # doc https://www.postman.com/pixelao/pixel-public-workspace/documentation/c26yn3l/crawl4ai-api?entity=request-24060341-db21f4c1-3760-4a21-abad-3c07a90e08da
    Leave out the urls key in crawl_payload as it will be set from start_url.
    Example (crawling a website):
    bash
    ```
   curl -X POST http://localhost:8000/api/v1/crawl_embed \
    -H "Content-Type: application/json" \
    -d '{
        "start_url": ["https://example.com"],
        "max_urls_to_visit": 100,
        "crawl_payload": {
            "browser_config": {
                "type": "BrowserConfig",
                "params": {"headless": true}
            },
            "crawler_config": {
                "type": "CrawlerRunConfig",
                "params": {
                    "stream": false,
                    "cache_mode": {"type": "CacheMode", "params": "bypass"},
                    "word_count_threshold": 100,
                    "scan_full_page": true
                }
            }
        } 
    }'
   
   ```
    """
    try:

        # Pass the updated config directly to CrawlApp
        crawl_app = CrawlApp()
        asyncio.create_task(crawl_app.main(config_start))
    except Exception as e:
        logger.error(f"Failed to start crawl: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Crawling Failed", "error": str(e)},
        )

    return ProcessingResponse(
        status="success",
        message="Crawl started successfully. Check logs for progress.",
        details={},
    )


@api_v1_router.post("/documents/process", response_model=ProcessingResponse)
async def process_documents(files: List[UploadFile] = File(...)):
    """
    Process and embed documents into the vector database.
    Supports PDF files directly or within ZIP archives.
    
    Example usage:
    bash
    ```
    curl -X POST http://localhost:8000/documents/process \
    -F "files=@/path/to/document1.pdf" 


    """
    # keep track of processed documents and errors
    processed_docs = []  # list of filenames
    errors = []

    # Count total PDFs to process for progress bar
    total_pdfs = 0
    file_contents = []
    for file in files:
        if not file.filename:
            continue
        content = await file.read()
        file_contents.append((file, content))
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zip_ref:
                    for file_info in zip_ref.infolist():
                        if (
                            file_info.filename.endswith(".pdf")
                            and not file_info.is_dir()
                        ):
                            total_pdfs += 1
            except zipfile.BadZipFile:
                pass
        elif file.filename.endswith(".pdf"):
            total_pdfs += 1

    progress_bar = tqdm(total=total_pdfs, desc="Processing PDFs", unit="pdf")

    try:
        for file, content in file_contents:
            if not file.filename:
                continue

            if file.filename.endswith(".zip"):
                # Process ZIP archive containing PDFs

                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as zip_ref:
                        for file_info in zip_ref.infolist():
                            if (
                                file_info.filename.endswith(".pdf")
                                and not file_info.is_dir()
                            ):
                                logger.info(
                                    f"Processing PDF from ZIP: {file_info.filename}"
                                )
                                with zip_ref.open(file_info) as pdf_file:
                                    pdf_content = pdf_file.read()
                                    docs, fail = create_db_from_documents(
                                        content=pdf_content, filename=file_info.filename
                                    )
                                    if docs or fail:
                                        if fail:
                                            errors.append(fail)
                                        if docs:
                                            processed_docs.append(docs)
                                    progress_bar.update(1)
                except zipfile.BadZipFile:
                    errors.append(f"Invalid ZIP file: {file.filename}")
                    logger.error(f"Invalid ZIP file: {file.filename}")

            elif file.filename.endswith(".pdf"):
                docs, fail = create_db_from_documents(
                    content=content, filename=file.filename
                )
                if docs or fail:
                    if fail:
                        errors.append(fail)
                    if docs:
                        processed_docs.append(docs)
                progress_bar.update(1)

            else:
                errors.append(f"Unsupported file type: {file.filename}")
                logger.warning(f"Unsupported file type: {file.filename}")

        progress_bar.close()

        if not processed_docs and errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "No documents were processed successfully",
                    "errors": errors,
                },
            )

        return ProcessingResponse(
            status="success",
            message=f"Successfully processed {len(processed_docs)} documents",
            details={
                "processed_count": len(processed_docs),
                "errors": errors if errors else None,
                "documents": processed_docs,
            },
        )

    except Exception as e:
        logger.error(f"Error processing documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Error processing documents", "error": str(e)},
        )


# Include the v1 router in the app
app.include_router(api_v1_router)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the FastAPI application.")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
