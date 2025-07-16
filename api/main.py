from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
import uuid
from core.ai_validator import ContentValidator
from core.scoring_engine import ScoringEngine
from core.ollama_scorer import OllamaQualityScorer
from celery_worker import process_and_score_post_task
app = FastAPI(
    title="Intelligent Scoring Service",
    description="An AI-powered service to validate and score user-generated content.",
    version="1.0.0"
)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Initialize the ContentValidator and ScoringEngine
validator = ContentValidator()
engine = ScoringEngine()

# --- API Endpoint Definition ---
@app.post("/v1/post/submit")
async def handle_post_submission(
    user_id: str = Form(...),
    text_content: str = Form(...),
    image: UploadFile = File(...)
):
    """
    This endpoint instantly accepts a post and queues it for background
    AI validation and scoring.
    """
    # Save the file to a location accessible by the worker
    temp_filename = f"{uuid.uuid4()}{os.path.splitext(image.filename)[1]}"
    image_path = os.path.join(UPLOAD_FOLDER, temp_filename)
    
    with open(image_path, "wb") as buffer:
        buffer.write(await image.read())

    # Create the background job by calling .delay()
    process_and_score_post_task.delay(
        user_id=user_id,
        text_content=text_content,
        image_path=image_path
    )
    
    print(f"API: Queued scoring job for user {user_id}.")

    # Respond to the user immediately
    return JSONResponse(
        status_code=202, # 202 Accepted
        content={"status": "processing", "message": "Post accepted for validation and scoring."}
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}

