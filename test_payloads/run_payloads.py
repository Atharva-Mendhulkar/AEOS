import httpx
import asyncio
import os
import json
import datetime
import jwt
from pathlib import Path

# Fetch the secret to sign the JWT
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

def get_format_and_mime(ext):
    mapping = {
        ".txt": ("text", "text/plain"),
        ".log": ("text", "text/plain"),
        ".json": ("json", "application/json"),
        ".png": ("image", "image/png"),
        ".pdf": ("pdf", "application/pdf"),
        ".m4a": ("audio", "audio/mp4")
    }
    return mapping.get(ext, ("unknown", "application/octet-stream"))

async def ingest_payload(filepath):
    api_base = "http://localhost:80/api/v1"
    headers = get_auth_headers()
    
    path = Path(filepath)
    ext = path.suffix.lower()
    format_type, mime = get_format_and_mime(ext)
    
    if format_type == "unknown":
        return
        
    print(f"\n🚀 Ingesting Test Case: {path.name} (Format: {format_type})")
    
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        payload = {"format": format_type, "metadata": json.dumps({"source": "test_payloads", "filename": path.name})}
        
        try:
            with open(path, "rb") as f:
                content = f.read()
                
            files = {"file": (path.name, content, mime)}
            response = await client.post(f"{api_base}/incidents/ingest", data=payload, files=files)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Successfully ingested! Incident ID: {data['incident_id']}")
            else:
                print(f"❌ Failed to ingest: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Error connecting to API: {e}")

async def main():
    print("=========================================================")
    print("   INGESTING ALL TEST PAYLOADS IN DIRECTORY              ")
    print("=========================================================")
    
    payloads_dir = Path("/Users/atharvamendhulkar/Desktop/AEOS/test_payloads")
    for filepath in payloads_dir.iterdir():
        if filepath.is_file() and filepath.name not in ["test.py", "run_payloads.py"]:
            await ingest_payload(filepath)
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
