import httpx
import os
import jwt
import datetime

SECRET = os.environ.get("AEOS_JWT_SECRET") or os.environ.get("JWT_SECRET", "test-jwt-secret-key-for-aeos-123456789")

def get_auth_headers():
    token = jwt.encode(
        {
            "sub": "operator-user",
            "role": "operator",
            "iat": datetime.datetime.now(datetime.timezone.utc),
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
        },
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}

def verify():
    headers = get_auth_headers()
    r = httpx.get("http://localhost:8000/api/v1/observability/agents", headers=headers)
    print("Status code:", r.status_code)
    print("Response JSON:")
    print(r.json())

if __name__ == "__main__":
    verify()
