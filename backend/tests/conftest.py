"""Test configuration: in-memory SQLite, test environment, demo providers, no network."""

import os

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests-0123456789",
        "SERPAPI_API_KEY": "",
        "OPENAI_API_KEY": "",
        "REDIS_URL": "",
        "RAZORPAY_KEY_ID": "rzp_test_dummykey",
        "RAZORPAY_KEY_SECRET": "test_razorpay_secret",
        "RAZORPAY_WEBHOOK_SECRET": "test_webhook_secret",
        "ADMIN_EMAILS": "admin@buywisetest.com",
        "LOG_LEVEL": "WARNING",
    }
)

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.database import Base, async_session_factory, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db():
    async with async_session_factory() as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def user_tokens(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "user@buywisetest.com", "username": "user1", "password": "Passw0rd!x"},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest_asyncio.fixture
async def auth_headers(user_tokens):
    return {"Authorization": f"Bearer {user_tokens['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "admin@buywisetest.com", "username": "admin1", "password": "Passw0rd!x"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def demo_product(client):
    """Run a demo search so a product with offers exists; return its id."""
    r = await client.post("/api/v1/search", json={"query": "Sony WH-1000XM5", "page_size": 3})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["results"], data
    return data["results"][0]["id"]


@pytest.fixture
def anyio_backend():
    return "asyncio"
