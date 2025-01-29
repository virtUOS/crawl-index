# Crawl & Index

**(Currently being developed)**

This project aims to create an index by crawling web pages, extracting their text content, processing, indexing, and storing it. The text is accompanied by metadata.

## Table of Contents

- Setup and Installation
  - Prerequisites
  - Production Setup
  - Development Setup
- Running the Project
- Configuration


## Setup and Installation

### Prerequisites

Before you begin, ensure you have a running instance of Milvus.

#### Running Milvus with Docker
The easiest way to start [Milvus](https://milvus.io/) is by using Docker. You can do this by modifying the `docker-compose.yml` file to include all necessary services.

To set up Milvus using Docker Compose, follow these instructions:
    [Install Milvus Standalone with Docker Compose](https://milvus.io/docs/v2.0.x/install_standalone-docker.md)

This guide will walk you through the steps to configure and launch a standalone instance of Milvus efficiently.

Note: 


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

5. **Run the application:**

    ```sh
    python src/crawl_ai/main.py
    ```

## Running the Project

### Using Docker 
**(Currently being developed)**


To run the project using Docker, use the following command:

```
docker-compose up
```

This will start the necessary services and run the application.

### Without Docker
To run the project without Docker, ensure you have followed the development setup instructions and then run:

```
python src/crawl_ai/main.py
```

## Configuration
The project uses a combination of YAML and environment variables for configuration. The main configuration file is `config.yaml`. You can find an example configuration in `config_example.yaml`.

### Environment Variables
The `.env` file contains environment-specific variables. An example `.env` file is provided as `.env_example`.

