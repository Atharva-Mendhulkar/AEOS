from aeos_shared import get, post, put, delete
import httpx
import asyncio
import os
import json
import datetime
import jwt

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

async def ingest_payload(name, format_type, content, filename):
    api_base = "http://localhost:8000/api/v1"
    headers = get_auth_headers()
    
    print(f"\n🚀 Ingesting Test Case: {name} (Format: {format_type})")
    
    if True:
        payload = {"format": format_type, "metadata": json.dumps({"source": "orchestration-test-suite"})}
        mime = "text/plain"
        files = {"file": (filename, content.encode('utf-8') if isinstance(content, str) else content, mime)}
        
        try:
            response = await post(f"{api_base}/incidents/ingest", data=payload, files=files)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Successfully ingested! Incident ID: {data['incident_id']}")
                return data['incident_id']
            else:
                print(f"❌ Failed to ingest: {response.status_code} - {response.text}")
        except Exception as e:
            import traceback
            print(f"❌ Error connecting to API:")
            traceback.print_exc()
        return None

async def main():
    print("=========================================================")
    print("   TEST 1: Specialist Agents & Policy Manager Trigger    ")
    print("=========================================================")
    # Content must include 'critical' to yield a 0.95 confidence score.
    # It must describe a complex scenario needing policy checks and operations.
    critical_content = """
    CRITICAL: Major database breach detected. Root passwords leaked on public repository.
    Immediate emergency rotation required by operations-agent.
    Compliance-agent must verify policy strict-rotation-policy-2028.
    """
    await ingest_payload("Critical DB Breach (Policy & Ops)", "text", critical_content.strip(), "breach.txt")

    # Give the system a second to process
    await asyncio.sleep(2)

    print("\n=========================================================")
    print("   TEST 2: Escalations Queue Trigger (Low Confidence)    ")
    print("=========================================================")
    # Content must include 'low confidence' or 'ambiguous' to yield a 0.50 confidence score.
    # This automatically marks requires_escalation = true and sends it to the Escalations Queue.
    ambiguous_content = """
    We received a user report about a glitch, but the logs are ambiguous. 
    I have low confidence in determining the actual root cause of this anomaly.
    Please investigate manually.
    """
    await ingest_payload("Ambiguous Anomaly (Escalation Queue)", "text", ambiguous_content.strip(), "glitch.txt")

if __name__ == "__main__":
    asyncio.run(main())

