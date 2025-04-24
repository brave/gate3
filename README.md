# Gate3

[![Build Status](https://github.com/brave-experiments/gate3/actions/workflows/ci.yml/badge.svg)](https://github.com/brave-experiments/gate3/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/Made%20with-Python%203.13-1f425f.svg)](https://www.python.org/)


A FastAPI-based gateway service for web3 applications at Brave.

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