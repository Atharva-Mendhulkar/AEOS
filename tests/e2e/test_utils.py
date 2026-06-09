import os
import time
from urllib.parse import urljoin

import httpx
import pytest
from jose import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "test-jwt-secret-key-for-aeos-123456789")
API_BASE = os.environ.get("AEOS_E2E_API_BASE", "http://localhost:8000/api/v1").rstrip("/")
GATEWAY_BASE = API_BASE.removesuffix("/api/v1")
E2E_TIMEOUT = float(os.environ.get("AEOS_E2E_TIMEOUT_SECONDS", "60"))

def get_test_token(role="admin"):
    payload = {
        "sub": "e2e-test-user",
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def get_auth_headers(role="admin"):
    return {"Authorization": f"Bearer {get_test_token(role)}"}

async def require_aeos_gateway():
    """Skip E2E tests unless an AEOS API Gateway is reachable."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(urljoin(f"{GATEWAY_BASE}/", "health"))
    except httpx.HTTPError as exc:
        pytest.skip(f"AEOS gateway is not reachable at {GATEWAY_BASE}: {exc}")

    if response.status_code != 200:
        pytest.skip(f"AEOS gateway health endpoint returned HTTP {response.status_code}")

    data = response.json()
    if data.get("service") != "api-gateway":
        pytest.skip(f"{GATEWAY_BASE} is not the AEOS API Gateway: {data}")

async def get_json(client: httpx.AsyncClient, url: str, **kwargs):
    response = await client.get(url, **kwargs)
    assert response.status_code == 200, f"GET {url} failed: {response.status_code} {response.text}"
    return response.json()

async def wait_for_condition(description: str, probe, timeout: float = E2E_TIMEOUT, interval: float = 1.0):
    deadline = time.monotonic() + timeout
    last_value = None
    while time.monotonic() < deadline:
        last_value = await probe()
        if last_value:
            return last_value
        await asyncio_sleep(interval)
    raise AssertionError(f"Timed out waiting for {description}; last observed value: {last_value!r}")

async def asyncio_sleep(seconds: float):
    import asyncio
    await asyncio.sleep(seconds)
