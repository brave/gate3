import os

import httpx
import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("INTEGRATION_BASE_URL", "http://localhost:8000")


@pytest_asyncio.fixture
async def client(base_url: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as c:
        yield c
