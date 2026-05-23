import os
import logging
import asyncio
import httpx
from uuid import UUID
from datetime import datetime, timezone
from aeos_shared import get_db, init_db_pool

logger = logging.getLogger(__name__)

OBSERVABILITY_URL = os.environ.get("OBSERVABILITY_URL", "http://observability-service:8040")
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8001")

async def transcribe_audio(input_id: UUID, file_path: str):
    """Asynchronously transcribe audio using Speechmatics or mock if key is mock."""
    logger.info(f"Starting audio transcription for input {input_id} (file: {file_path})")
    
    api_key = os.environ.get("SPEECHMATICS_API_KEY", "mock-key")
    api_url = os.environ.get("SPEECHMATICS_API_URL", "https://api.speechmatics.com")
    
    transcript = ""
    try:
        if api_key == "mock-key":
            # Simulate processing delay
            await asyncio.sleep(0.5)
            transcript = f"Mock transcription for audio input {input_id}. System alert detected: service degradation in database node."
            logger.info("Mock Speechmatics transcription completed.")
        else:
            # Call actual Speechmatics API (v2 jobs endpoint)
            # 1. Submit job
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient() as client:
                with open(file_path, "rb") as f:
                    files = {"data_file": f}
                    data = {"config": '{"type": "transcription", "transcription_config": {"language": "en"}}'}
                    response = await client.post(f"{api_url}/v2/jobs", headers=headers, files=files, data=data)
                
                if response.status_code != 201:
                    raise RuntimeError(f"Speechmatics job submission failed: {response.text}")
                
                job_id = response.json()["id"]
                logger.info(f"Speechmatics job submitted. ID: {job_id}")
                
                # 2. Poll for completion
                for _ in range(60): # Poll up to 60 times (60 seconds)
                    await asyncio.sleep(1)
                    job_response = await client.get(f"{api_url}/v2/jobs/{job_id}", headers=headers)
                    if job_response.status_code == 200:
                        job_status = job_response.json()["job"]["status"]
                        if job_status == "done":
                            # 3. Retrieve transcript
                            transcript_response = await client.get(f"{api_url}/v2/jobs/{job_id}/transcript?format=txt", headers=headers)
                            if transcript_response.status_code == 200:
                                transcript = transcript_response.text
                                break
                            else:
                                raise RuntimeError(f"Failed to retrieve transcript: {transcript_response.text}")
                        elif job_status == "rejected":
                            raise RuntimeError("Speechmatics job rejected")
                else:
                    raise TimeoutError("Speechmatics transcription timed out")
    except Exception as e:
        logger.error(f"Audio transcription failed: {e}")
        # Update database with failed status
        pool = await init_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE multimodal_inputs SET processing_status = 'failed' WHERE id = $1",
                input_id
            )
        return

    # Update database with transcript and ready status
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE multimodal_inputs SET transcript = $1, processing_status = 'ready' WHERE id = $2",
            transcript, input_id
        )
    logger.info(f"Database updated for audio input {input_id}")

    # Emit preprocessing.completed event to Observability
    async with httpx.AsyncClient() as client:
        try:
            event_payload = {
                "event_type": "preprocessing.completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_identity": "api-gateway",
                "incident_id": None,
                "workflow_id": None,
                "action_description": f"Audio transcription completed for input {input_id}",
                "inputs": {"input_id": str(input_id)},
                "outputs": {"transcript_length": len(transcript)},
                "prev_entry_hash": "genesis"
            }
            await client.post(f"{OBSERVABILITY_URL}/observability/events", json=event_payload)
        except Exception as e:
            logger.warning(f"Failed to emit preprocessing.completed event: {e}")

    # Forward reference to the Coordinator
    async with httpx.AsyncClient() as client:
        try:
            coordinator_payload = {
                "input_id": str(input_id),
                "format": "audio",
                "transcript": transcript
            }
            logger.info(f"Forwarding audio input {input_id} to Coordinator")
            await client.post(f"{COORDINATOR_URL}/coordinator/route-input", json=coordinator_payload)
        except Exception as e:
            logger.error(f"Failed to forward input {input_id} to Coordinator: {e}")
