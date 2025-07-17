import uvicorn
import os
import uuid
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from typing import Optional

# Import the Celery task and Scoring Engine
from celery_worker import process_and_score_post_task
from core.scoring_engine import ScoringEngine

# --- Pydantic Models for Input Validation ---
class InteractionModel(BaseModel):
    interactionType: str = Field(..., description="The type of interaction, e.g., 'post', 'like', 'comment'.")
    data: Optional[str] = Field(None, description="The text content for a post or comment, or an ID for a like.")

class BlockchainRequestModel(BaseModel):
    creatorAddress: str = Field(..., description="The wallet address of the user performing the action.")
    interactorAddress: Optional[str] = Field(None, description="The wallet address of the receiver (for likes, etc.).")
    Interaction: InteractionModel
    webhookUrl: Optional[str] = Field(None, description="The URL to send the final AIResponse to (required for posts).")

# --- App Initialization ---
app = FastAPI(
    title="Intelligent Scoring Service - Production",
    version="2.0.0", # Version bump for new API structure
    description="""
    An AI-powered service to validate and score user-generated content.
    - Use `/v1/submit_action` for simple JSON-based interactions (like, comment, etc.).
    - Use `/v1/submit_post` for `multipart/form-data` interactions that may include an image.
    """
)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Singleton Instance for Scoring Engine ---
# This is created once when the API starts up and reused.
engine = ScoringEngine()

# --- Custom Dependency to Parse JSON from a Form for Posts ---
def parse_post_request(request_str: str = Form(..., alias="request")) -> BlockchainRequestModel:
    """Parses the 'request' JSON string from a multipart form."""
    try:
        model = BlockchainRequestModel.model_validate_json(request_str)
        if not model.webhookUrl:
            raise HTTPException(status_code=422, detail="A 'webhookUrl' is required for post submissions.")
        return model
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON in 'request' field: {e}")

# ===================================================================
#                      API ENDPOINT DEFINITIONS
# ===================================================================

@app.get("/health", tags=["System"])
def health_check():
    """Check if the API service is running."""
    return {"status": "ok"}

@app.post("/v1/submit_action", tags=["Synchronous Actions"])
async def handle_synchronous_action(request: BlockchainRequestModel):
    """
    Handles simple, fast, JSON-only interactions like 'like', 'comment', 'referral', and 'tipping'.
    This endpoint processes the request immediately and returns the final result.
    """
    interaction_type = request.Interaction.interactionType.lower()
    user_id = request.creatorAddress
    
    # --- Router for simple, synchronous tasks ---
    if interaction_type not in ["like", "comment", "referral", "tipping"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid interactionType for this endpoint. Use /v1/submit_post for posts."
        )
        
    print(f"API: Received synchronous '{interaction_type}' job for user {user_id}.")
    
    points_awarded = 0.0
    if interaction_type == "like":
        points_awarded = engine.add_like_points(user_id)
    elif interaction_type == "comment":
        points_awarded = engine.add_comment_points(user_id)
    elif interaction_type == "referral":
        points_awarded = engine.add_referral_points(user_id)
    elif interaction_type == "tipping":
        points_awarded = engine.add_tipping_points(user_id)
        
    final_score = engine.get_final_score(user_id)
    
    # Build and return the final AIResponse immediately
    ai_response = {
        "creatorAddress": user_id,
        "interactorAddress": request.interactorAddress,
        "Interaction": request.Interaction.model_dump(),
        "validation": {
            "aiAgentResponseApproved": True,
            "significanceScore": round(points_awarded, 4),
            "reason": "Interaction processed successfully.",
            "finalUserScore": round(final_score, 4)
        }
    }
    return JSONResponse(status_code=200, content=ai_response)


@app.post("/v1/submit_post", tags=["Asynchronous Actions (Posts)"])
async def handle_post_submission(
    request_data: BlockchainRequestModel = Depends(parse_post_request),
    image: Optional[UploadFile] = File(None)
):
    """
    Handles 'post' submissions, which may include an image file.
    This is an asynchronous endpoint that accepts the post and queues it for
    heavy AI processing. The final result is sent to the provided `webhookUrl`.
    """
    image_path = None
    if image:
        temp_filename = f"{uuid.uuid4()}{os.path.splitext(image.filename)[1]}"
        image_path = os.path.join(UPLOAD_FOLDER, temp_filename)
        with open(image_path, "wb") as buffer:
            buffer.write(await image.read())

    # Queue the background job
    process_and_score_post_task.delay(
        user_id=request_data.creatorAddress,
        text_content=request_data.Interaction.data or "",
        image_path=image_path,
        webhook_url=request_data.webhookUrl
    )
    
    print(f"API: Queued 'post' job for user {request_data.creatorAddress}. Webhook: {request_data.webhookUrl}")
    
    # Respond immediately to the caller
    return JSONResponse(
        status_code=202, # 202 Accepted
        content={"status": "processing", "message": "Post accepted for validation and scoring. Result will be sent to webhook."}
    )