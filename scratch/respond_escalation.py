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

def run():
    headers = get_auth_headers()
    r = httpx.get("http://localhost:8000/api/v1/escalations/pending", headers=headers)
    print("Pending Escalations:")
    escalations = r.json()
    print(escalations)
    for esc in escalations:
        esc_id = esc["id"]
        print(f"Responding to escalation {esc_id}...")
        resp = httpx.post(
            f"http://localhost:8000/api/v1/escalations/{esc_id}/respond",
            headers=headers,
            data={"decision": "approve", "notes": "Approved by operator via script"}
        )
        print("Response status:", resp.status_code)
        print("Response JSON:", resp.json())

if __name__ == "__main__":
    run()
