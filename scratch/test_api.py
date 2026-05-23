import asyncio
import httpx
from jose import jwt
import os

token = jwt.encode(
    {"sub": "admin-user", "role": "admin", "iat": 1779546611, "exp": 1779633011},
    "test-jwt-secret-key-for-aeos-123456789",
    algorithm="HS256"
)
print("Generated Token:", token)

async def test():
    async with httpx.AsyncClient() as client:
        r = await client.get("http://localhost:8000/api/v1/observability/audit/validate-chain", headers={"Authorization": f"Bearer {token}"})
        print(r.status_code)
        print(r.text)

asyncio.run(test())
