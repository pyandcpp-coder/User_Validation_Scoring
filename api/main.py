# api/main.py (Definitive Production Version)
import uvicorn
import os
import uuid
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from typing import Optional

# Import the Celery task
from celery_worker import process_and_score_post_task

# --- Pydantic Models for Input Validation ---
class InteractionModel(BaseModel):
    interactionType: str
    data: Optional[str] = None

class BlockchainRequestModel(BaseModel):
    creatorAddress: str
    interactorAddress: Optional[str] = None
    Interaction: InteractionModel
    webhookUrl: str

# --- App Initialization ---
app = FastAPI(
    title="Intelligent Scoring Service - Production",
    version="1.2.0" # Version bump for new API structure
)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Custom Dependency to Parse JSON from a Form ---
# This is the key to solving the 422 error.
def parse_blockchain_request(request_str: str = Form(..., alias="request")) -> BlockchainRequestModel:
    """
    This function is a 'dependency' that FastAPI will run. It takes the
    'request' field from the multipart form, which is a string, and parses
    it into our validated Pydantic model.
    """
    try:
        # Use Pydantic's validator to parse the JSON string
        return BlockchainRequestModel.model_validate_json(request_str)
    except ValidationError as e:
        # If the JSON is malformed or missing fields, raise a 422 error
        raise HTTPException(
            status_code=422,
            detail=f"Invalid JSON format in 'request' form field: {e}"
        )

# --- API Endpoint Definition ---
@app.post("/v1/process_interaction")
async def handle_blockchain_interaction(
    # Use Depends to tell FastAPI to run our custom parser for the 'request' form field
    request_data: BlockchainRequestModel = Depends(parse_blockchain_request),
    # The 'image' part is still handled as a standard optional file
    image: Optional[UploadFile] = File(None)
):
    """
    Accepts a multipart/form-data request with a 'request' (JSON string) field
    and an optional 'image' file field.
    """
    interaction_type = request_data.Interaction.interactionType.lower()
    user_id = request_data.creatorAddress
    
    if interaction_type == "post":
        image_path = None
        if image:
            temp_filename = f"{uuid.uuid4()}{os.path.splitext(image.filename)[1]}"
            image_path = os.path.join(UPLOAD_FOLDER, temp_filename)
            with open(image_path, "wb") as buffer:
                buffer.write(await image.read())

        process_and_score_post_task.delay(
            user_id=user_id,
            text_content=request_data.Interaction.data or "",
            image_path=image_path,
            webhook_url=request_data.webhookUrl
        )
        
        print(f"API: Queued 'post' job for user {user_id}. Webhook: {request_data.webhookUrl}")
        return JSONResponse(
            status_code=202,
            content={"status": "processing", "message": "Post accepted. Result will be sent to webhook."}
        )
    
    else:
        # Handle other interaction types
        raise HTTPException(status_code=400, detail=f"interactionType '{interaction_type}' not supported.")

@app.get("/health")
def health_check():
    return {"status": "ok"}