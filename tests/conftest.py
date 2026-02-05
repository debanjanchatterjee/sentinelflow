import os
import asyncio
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

os.environ["TESTING"] = "1"

from app.main import app as fastapi_app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(app=fastapi_app, base_url="http://testserver") as ac:
        yield ac
