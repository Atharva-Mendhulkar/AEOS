import asyncio
import httpx
import jwt
import datetime

SECRET = "test-jwt-secret-key-for-aeos-123456789"
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
headers = {"Authorization": f"Bearer {token}"}

async def main():
    async with httpx.AsyncClient(headers=headers) as c:
        # Get escalations
        r1 = await c.get("http://localhost:80/api/v1/escalations/pending")
        print("Escalations:", r1.json())
        
        # Get incidents
        r2 = await c.get("http://localhost:80/api/v1/incidents")
        incidents = r2.json()
        print("Incidents:", len(incidents))
        
        if incidents:
            inc = incidents[0]
            wf_id = inc.get("workflow_id")
            if wf_id:
                rwf = await c.get(f"http://localhost:80/api/v1/workflows/{wf_id}")
                print("Workflow:", rwf.json())

asyncio.run(main())
