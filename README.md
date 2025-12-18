# Gate3

[![Build Status](https://github.com/brave-experiments/gate3/actions/workflows/ci.yml/badge.svg)](https://github.com/brave-experiments/gate3/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/Made%20with-Python%203.14-1f425f.svg)](https://www.python.org/)


A FastAPI-based gateway service for web3 applications at Brave.

**Documentation:** [`gate3.bsg.brave.com/docs`](https://gate3.bsg.brave.com/docs) (requires Brave VPN)


## Prerequisites

- Python 3.14 or higher
- Poetry for dependency management
- Redis server

## Development

### Setup

1. Clone the repository:
    ```bash
    git clone https://github.com/brave/gate3.git
    cd gate3
    ```

2. Install dependencies using Poetry:
    ```bash
    poetry install
    ```

3. Run unit tests
    ```bash
    poetry run pytest
    ```

4. Run Redis server

    ```bash
    redis-server
    ```

5. Run the development server using FastAPI:
    ```bash
    poetry run fastapi dev
    ```

### Deployments

Deployments are managed using the [generalized docker build pipeline](https://github.com/brave-intl/general-docker-build-pipeline-action). To create a new deployment, simply publish a new release on GitHub.

gate3 is currently deployed to the following environments:

| Environment | Access Control | URL |
|-------------|----------------|------------------|
| Production (internal) | Internal Brave VPN | `gate3.bsg.brave.com` |
| Production | Brave Services Key | `gate3.wallet.brave.com` |
| Staging | Brave Services Key | `gate3.wallet.brave.software` |
