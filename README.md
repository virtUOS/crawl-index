# Crawl & Index - FastAPI Service

This repository provides a simple FastAPI service to crawl a (large) website and automatically process its content with [RAGFlow](https://ragflow.io). The goal is to make it easy to:

- **Crawl a website** with a single API call
- **Send crawled content to RAGFlow** for processing and indexing
- **Recrawl** a website at any time to update content in RAGFlow

> **Best suited for large-scale sites:**  
> This API is built to handle large websites with thousands of pages. After crawling, the collected content can be processed, indexed, and stored in a vector database—enabling  Retrieval-Augmented Generation (RAG) systems and AI-driven search engines.

> **Note:** Milvus vector database integration is still under development and not yet available in this version.

> **Content tracking:**  
> The service maintains a database of all crawled content, making it possible to detect changes and trigger targeted recrawls as needed. 

## Quick Start

### 1. Clone and Configure

```sh
git clone <repository-url>
cd <repository-directory>
cp config_example.yaml config.yaml
# Edit config.yaml with your website and RAGFlow settings
```

### 2. Run with Docker (Recommended)

```sh
docker-compose up --build
```

Or run locally for development:

```sh
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py --host 0.0.0.0 --port 8000
```

The API will be available at [http://localhost:8000](http://localhost:8000)


## Requirements

- This service depends on a running instance of [crawl4ai](https://docs.crawl4ai.com). You can add crawl4ai as a service in your `docker-compose.yml` or connect to any accessible crawl4ai instance.
- The `crawl_payload` in your API requests can be any configuration accepted by the crawl4ai API, allowing you to fully customize the crawling process to your needs. For details, see the [Crawl4AI API documentation](https://www.postman.com/pixelao/pixel-public-workspace/documentation/c26yn3l/crawl4ai-api?entity=request-24060341-db21f4c1-3760-4a21-abad-3c07a90e08da).

## How It Works

1. **Start a crawl**: Send a POST request to `/api/v1/crawl_embed` with your website and RAGFlow settings.
2. **Automatic RAGFlow integration**: The service crawls your site and sends the content to RAGFlow for processing and indexing.
3. **Recrawl anytime**: Use `/api/v1/recrawl_embed` to update RAGFlow with new or changed content from your site.

## Example: Start a Crawl

```bash
curl -X POST http://localhost:8000/api/v1/crawl_embed \
    -H "Content-Type: application/json" \
    -d '{
        "crawl_settings": {
            "start_url": ["https://www.example.com"],
            "max_urls_to_visit": 100,
            "allowed_domains": ["https://www.example.com"],
            "crawl_payload": { /* see crawl4ai API docs */ }
        },
        "ragflow_settings": {
            "base_url": "https://ragflow-instance.com",
            "collection_name": "my_collection",
            "api_key": "ragflow-api-key"
        }
    }'
```

## Example: Recrawl for Updates

```bash
curl -X POST http://localhost:8000/api/v1/recrawl_embed \
    -H "Content-Type: application/json" \
    -d '{
        "crawl_payload": { /* updated crawl4ai config */ },
        "ragflow_settings": {
            "base_url": "https://ragflow-instance.com",
            "collection_name": "my_collection",
            "api_key": "ragflow-api-key"
        }
    }'
```

## Configuration

Edit `config.yaml` to set your website and RAGFlow connection details. All settings can also be updated at runtime via the API.

## API Documentation

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---



