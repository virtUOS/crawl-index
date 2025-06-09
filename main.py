import argparse
import zipfile
import io
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, File, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.db.process_files import create_db_from_documents
from src.logger.crawl_logger import logger
from src.config.core_config import settings
from src.config.models import MilvusSettings, EmbeddingSettings
from src.db.clients import test_milvus_connection


app = FastAPI(
    title="Document Processing API",
    description="API for processing and embedding PDF documents into Milvus",
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


@app.get("/config")
async def get_current_config():
    """Get current configuration for both Milvus and embeddings"""
    return ConfigurationResponse(
        status="success",
        message="Current configuration retrieved successfully",
        current_config={
            "milvus": settings.milvus.model_dump(),
            "embedding": settings.embedding.model_dump(),
        },
    )


@app.post("/config/milvus", response_model=ConfigurationResponse)
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
        # Update settings
        settings.milvus = config

        test = test_milvus_connection()
        if not test:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to connect to Milvus with the provided configuration",
            )

        return ConfigurationResponse(
            status="success",
            message=f"Milvus configuration updated successfully. Server version: {test}",
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


@app.post("/config/embedding", response_model=ConfigurationResponse)
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
        # Update settings
        settings.embedding = config

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


@app.post("/documents/process", response_model=ProcessingResponse)
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

    try:
        for file in files:
            if not file.filename:
                continue

            content = await file.read()

            if file.filename.endswith(".zip"):
                # Process ZIP archive containing PDFs
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as zip_ref:
                        for file_info in zip_ref.infolist():
                            if (
                                file_info.filename.endswith(".pdf")
                                and not file_info.is_dir()
                            ):
                                # TODO Strip the directories name from the file_info.filename
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

                except zipfile.BadZipFile:
                    errors.append(f"Invalid ZIP file: {file.filename}")
                    logger.error(f"Invalid ZIP file: {file.filename}")

            elif file.filename.endswith(".pdf"):
                # Process single PDF file
                docs, fail = create_db_from_documents(
                    content=content, filename=file.filename
                )
                if docs or fail:
                    if fail:
                        errors.append(fail)
                    if docs:
                        processed_docs.append(docs)

            else:
                errors.append(f"Unsupported file type: {file.filename}")
                logger.warning(f"Unsupported file type: {file.filename}")

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the FastAPI application.")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
