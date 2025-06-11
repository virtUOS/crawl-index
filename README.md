# Crawl & Index - FastAPI Embedding Service

**(Currently being developed)**

This FastAPI application provides an API service for embedding content from multiple sources. It can extract and embed text content from PDF files as well as crawl web pages to extract, process, and index their content using vector embeddings. All processed content is stored with metadata in Milvus vector database.

## Table of Contents

- Setup and Installation
  - Prerequisites
  - Production Setup
  - Development Setup
- Running the Project
- API Endpoints
- Configuration

## Setup and Installation

### Prerequisites

Before you begin, ensure you have the following:

- Python 3.8+
- A running instance of Milvus vector database
- FastAPI and related dependencies

#### Running Milvus with Docker
The easiest way to start [Milvus](https://milvus.io/) is by using Docker. You can do this by modifying the `docker-compose.yml` file to include all necessary services.

To set up Milvus using Docker Compose, follow these instructions:
    [Install Milvus Standalone with Docker Compose](https://milvus.io/docs/v2.0.x/install_standalone-docker.md)

This guide will walk you through the steps to configure and launch a standalone instance of Milvus efficiently.

### Production Setup

1. **Clone the repository:**

    ```sh
    git clone <repository-url>
    cd <repository-directory>
    ```

2. **Create a [`.env`](.env ) file:**

    Copy the contents of [`.env_example`](.env_example ) to a new file named [`.env`](.env ) and update the values as needed.

    ```sh
    cp .env_example .env
    ```

3. **Build and run the Docker containers:**

    ```sh
    docker-compose up --build
    ```

### Development Setup

1. **Clone the repository:**

    ```sh
    git clone <repository-url>
    cd <repository-directory>
    ```

2. **Create a virtual environment:**

    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. **Install dependencies:**

    ```sh
    pip install -r requirements.txt
    ```

4. **Create a [`.env`](.env ) file:**

    Copy the contents of [`.env_example`](.env_example ) to a new file named [`.env`](.env ) and update the values as needed.

    ```sh
    cp .env_example .env
    ```

5. **Run the FastAPI application:**

    ```sh
    uvicorn src.crawl_ai.main:app --reload --host 0.0.0.0 --port 8000
    ```

## Running the Project

### Using Docker 
**(Currently being developed)**

To run the project using Docker, use the following command:

```sh
docker-compose up
```

This will start the necessary services and run the FastAPI application.

### Without Docker
To run the FastAPI server without Docker, ensure you have followed the development setup instructions and then run:

```sh
uvicorn src.crawl_ai.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## API Endpoints

Once the FastAPI server is running, you can:

- **View API Documentation**: Visit `http://localhost:8000/docs` for interactive Swagger UI documentation
- **Alternative Documentation**: Visit `http://localhost:8000/redoc` for ReDoc documentation

### PDF Embedding Endpoints

The application provides endpoints for:
- Uploading and embedding PDF files
- Crawling and embedding web page content
- Querying embedded content from any source
- Managing indexed documents

Detailed endpoint documentation is available in the interactive API docs.

## Configuration
The project uses a combination of YAML and environment variables for configuration. The main configuration file is `config.yaml`. You can find an example configuration in `config_example.yaml`.

### Environment Variables
The `.env` file contains environment-specific variables. An example `.env` file is provided as `.env_example`.

