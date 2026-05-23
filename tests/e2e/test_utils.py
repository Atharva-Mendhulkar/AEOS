import time
import os
from jose import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "test-jwt-secret-key-for-aeos-123456789")

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
