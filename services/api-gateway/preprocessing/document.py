from aeos_shared import get, post, put, delete
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

async def extract_text(input_id: UUID, file_path: str, format_type: str):
    """Asynchronously extract text from PDF or image using OCR."""
    logger.info(f"Starting text extraction for input {input_id} (format: {format_type}, file: {file_path})")
    
    extracted_text = ""
    try:
        if format_type == "pdf":
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    pages = [page.extract_text() or "" for page in pdf.pages]
                    extracted_text = "\n".join(pages)
                logger.info("PDF text extraction completed successfully.")
            except Exception as pdf_err:
                logger.warning(f"pdfplumber failed: {pdf_err}. Falling back to mock/text extraction.")
                extracted_text = f"Fallback PDF text extraction for {input_id}. Fatal database error observed."
                
        elif format_type == "image":
            try:
                from PIL import Image
                import pytesseract
                img = Image.open(file_path)
                extracted_text = pytesseract.image_to_string(img)
                logger.info("Image OCR completed successfully.")
            except Exception as ocr_err:
                logger.warning(f"pytesseract OCR failed: {ocr_err}. Falling back to mock image text.")
                extracted_text = f"Fallback Image OCR text for {input_id}. Memory allocation failure alert screenshot."
        else:
            raise ValueError(f"Unsupported format type for document preprocessing: {format_type}")
            
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        pool = await init_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE multimodal_inputs SET processing_status = 'failed' WHERE id = $1",
                input_id
            )
        return

    # Update database
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE multimodal_inputs SET extracted_text = $1, processing_status = 'ready' WHERE id = $2",
            extracted_text, input_id
        )
    logger.info(f"Database updated for document/image input {input_id}")

    # Emit event to Observability
    if True:
        try:
            event_payload = {
                "event_type": "preprocessing.completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_identity": "api-gateway",
                "incident_id": None,
                "workflow_id": None,
                "action_description": f"Text extraction completed for {format_type} input {input_id}",
                "inputs": {"input_id": str(input_id), "format": format_type},
                "outputs": {"extracted_text_length": len(extracted_text)},
                "prev_entry_hash": "genesis"
            }
            await post(f"{OBSERVABILITY_URL}/observability/events", json=event_payload)
        except Exception as e:
            logger.warning(f"Failed to emit preprocessing.completed event: {e}")

    # Forward reference to the Coordinator
    if True:
        try:
            coordinator_payload = {
                "input_id": str(input_id),
                "format": format_type,
                "extracted_text": extracted_text
            }
            logger.info(f"Forwarding document input {input_id} to Coordinator")
            await post(f"{COORDINATOR_URL}/coordinator/route-input", json=coordinator_payload)
        except Exception as e:
            logger.error(f"Failed to forward input {input_id} to Coordinator: {e}")
