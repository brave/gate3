# Gate3

[![Build Status](https://github.com/brave/gate3/actions/workflows/ci.yml/badge.svg)](https://github.com/brave/gate3/actions/workflows/ci.yml)

A FastAPI-based gateway service for web3 applications at Brave.

## Features

- FastAPI-based REST API
- Redis integration for caching and data storage
- Web3 functionality integration
- Async HTTP client support via httpx
- Fast JSON serialization with orjson
- Configuration management with pydantic-settings

## Prerequisites

- Python 3.13 or higher
- Poetry for dependency management
- Redis server (optional)

## Development

1. Clone the repository:
    ```bash
    git clone https://github.com/brave/gate3.git
    cd gate3
    ```

2. Install dependencies using Poetry:
    ```bash
    poetry install
    ```

3. Run the development server using FastAPI:
    ```bash
    poetry run fastapi dev
    ```

4. Run the production server using Uvicorn:
    ```bash
    poetry run fastapi run
    ```