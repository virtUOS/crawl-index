# Crawl & Index - FastAPI Embedding Service

**(Currently being developed)**

This FastAPI application provides an API service for embedding content from multiple sources. It can extract and embed text content from PDF files as well as crawl web pages to extract, process, and index their content using vector embeddings. All processed content is stored with metadata in Milvus vector database.

## Setup and Installation

### Prerequisites

- Python 3.8+
- A running instance of Milvus vector database
- FastAPI and related dependencies

#### Running Milvus with Docker
The easiest way to start [Milvus](https://milvus.io/) is by using Docker. Follow the [Install Milvus Standalone with Docker Compose](https://milvus.io/docs/v2.0.x/install_standalone-docker.md) guide.

### Running the Project (Recommended)

#### Using Docker

```sh
# Clone the repository
git clone <repository-url>
cd <repository-directory>

# Create configuration
cp config_example.yaml config.yaml
# Edit config.yaml with your settings

# Build and run with Docker
docker-compose up --build
```

This will start all necessary services including the FastAPI application.

### Alternative: Development Setup

If you prefer running without Docker:

1. **Clone and setup:**
    ```sh
    git clone <repository-url>
    cd <repository-directory>
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

2. **Configure:**
    ```sh
    cp config_example.yaml config.yaml
    # Edit config.yaml with your settings
    ```

3. **Run:**
    ```sh
    python main.py --host 0.0.0.0 --port 8000
    ```

The API will be available at `http://localhost:8000`

## API Endpoints

Access the API documentation at `http://localhost:8000/docs`

### Configuration Endpoints

The application uses a YAML-based configuration system that can be overridden at runtime through API endpoints:

#### Configure Milvus
```bash
curl -X POST http://localhost:8000/config/milvus \
-H "Content-Type: application/json" \
-d '{
    "uri": "http://my-milvus-instance.de:19530",
    "token": "root:Milvus",
    "collection_name": "documents",
    "collection_description": "A collection of PDF documents",
    "enable_dynamic_field": false,
    "auto_id": false
}'
```

#### Configure Embedding
The application supports two embedding providers: **FastEmbed** and **Ollama**:

```bash
# FastEmbed configuration
curl -X POST http://localhost:8000/config/embedding \
-H "Content-Type: application/json" \
-d '{
    "type": "FastEmbed",
    "connection_settings": {
        "model_name": "intfloat/multilingual-e5-large"
    }
}'

# Ollama configuration
curl -X POST http://localhost:8000/config/embedding \
-H "Content-Type: application/json" \
-d '{
    "type": "Ollama",
    "connection_settings": {
        "base_url": "http://my-ollama-instance.de",
        "model": "nomic-embed-text"
        headers: {
        "Authorization": "API-KEY"
        }
    }
}'
```

#### Start Crawling
```bash
curl -X POST http://localhost:8000/crawl/process \
-H "Content-Type: application/json" \
-d '{
    "start_url": "https://example.com",
    "max_urls_to_visit": 100,
    "allowed_domains": ["example.com"],
    "check_content_changed": false
}'
```

### Document Processing

- Process single documents or `.zip` files containing PDFs. 
 
```bash
curl -X POST http://localhost:8000/documents/process \
-F "files=@/path/to/document.pdf"
```

## Configuration

The application uses `config.yaml` for initial configuration. All settings can be updated at runtime through API endpoints.

### Example Configuration File
```yaml
milvus:
  # Use uri for direct connection
  uri: "http://my-milvus-instance.de:19530"
  token: "root:Milvus"
  collection_name: "documents"
  collection_description: "A collection of PDF documents"
  enable_dynamic_field: false
  auto_id: false
  
  # Alternative: Use host/port when connecting via Docker network
  # host: "standalone"
  # port: 19530

embedding:
  # Choose one of the supported providers: "FastEmbed" or "Ollama"
  type: "FastEmbed"
  connection_settings:
    # For FastEmbed:
    model_name: "intfloat/multilingual-e5-large"
    
    # For Ollama (uncomment if using Ollama):
    # base_url: "http://my-ollama-instance.de"
    # model: "nomic-embed-text"

crawl_settings:
  start_url: "https://example.com"
  max_urls_to_visit: 100
  allowed_domains: ["example.com"]
  exclude_domains: []
  debug: true
  target_elements: ["a[href]", "p"]
  check_content_changed: false # If true, first check if the content of the website has changed since last visited. If content changed crawl again. (overrides crawl4ai)
```

### Features

- **Configuration Management**: Settings loaded from `config.yaml` with runtime updates via API
- **Multiple Embedding Providers**: Support for FastEmbed and Ollama embedding engines
- **PDF Processing**: Process documents individually or in ZIP archives
- **Web Crawling**: Configure and crawl websites with customizable parameters
- **Content Change Detection**: Option to only process changed content during re-crawling

