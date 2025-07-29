import uvicorn
import os
import uuid
import json
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, Annotated
from celery_worker import validate_and_score_comment_task
from celery_worker import process_and_score_post_task
from core.scoring_engine import ScoringEngine


class InteractionModel(BaseModel):
    interactionType: str = Field(..., description="The type of interaction, e.g., 'post', 'like', 'comment'.")
    data: Optional[str] = Field(None, description="The text content for a post or comment, or an ID for a like.")

class BlockchainRequestModel(BaseModel):
    creatorAddress: str = Field(..., description="The wallet address of the user performing the action.")
    interactorAddress: Optional[str] = Field(None, description="The wallet address of the receiver (for likes, etc.).")
    Interaction: InteractionModel
    webhookUrl: Optional[str] = Field(None, description="The URL to send the final AIResponse to (required for posts).")

engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    print("Application startup: Initializing scoring engine and database...")
    try:
        engine = ScoringEngine()
        engine._initialize_database()
        print("Database initialization complete. Application is ready.")
    except Exception as e:
        print(f"CRITICAL ERROR during startup: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        raise
    
    yield
    
    # Shutdown
    print("Application shutdown: Closing database connections.")
    if engine:
        engine.close()

# --- App Initialization ---
app = FastAPI(
    title="Intelligent Scoring Service - Production",
    version="2.0.0",
    description="""
    An AI-powered service to validate and score user-generated content.
    - Use `/v1/submit_action` for simple JSON-based interactions (like, comment, etc.).
    - Use `/v1/submit_post` for `multipart/form-data` interactions that may include an image.
    """,
    lifespan=lifespan
)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.get("/debug/db", tags=["Debug"])
def debug_database():
    """Test database connection directly."""
    try:
        if not engine:
            return {"status": "error", "error": "Engine not initialized"}
            
        conn = engine._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()
            
            # Test if user_scores table exists
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'user_scores';
            """)
            table_exists = cur.fetchone() is not None
            
        engine._put_conn(conn)
        
        return {
            "status": "ok",
            "postgres_version": version[0] if version else "unknown",
            "user_scores_table_exists": table_exists
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/engine", tags=["Debug"])
def debug_engine():
    """Test the scoring engine directly."""
    try:
        if not engine:
            return {"status": "error", "error": "Engine not initialized"}
            
        test_user = "debug_user_123"
        initial_score = engine.get_final_score(test_user)
        like_points = engine.add_like_points(test_user)
        
        final_score = engine.get_final_score(test_user)
        
        return {
            "status": "ok",
            "test_user": test_user,
            "initial_score": initial_score,
            "like_points_awarded": like_points,
            "final_score": final_score
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.post("/debug/simple-like", tags=["Debug"])
def debug_simple_like(user_id: str = Query(default="test_user")):
    """Test a simple like operation."""
    try:
        if not engine:
            return {"status": "error", "error": "Engine not initialized"}
            
        print(f"DEBUG: Testing like for user {user_id}")
        points = engine.add_like_points(user_id)
        score = engine.get_final_score(user_id)
        
        return {
            "status": "ok",
            "user_id": user_id,
            "points_awarded": points,
            "final_score": score
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@app.get("/health", tags=["System"])
def health_check():
    """Check if the API service is running."""
    return {"status": "ok", "engine_initialized": engine is not None}

@app.get("/health/weaviate", tags=["System"])
def weaviate_health_check():
    """Check if Weaviate is connected and working."""
    try:
        from core.ai_validator import ContentValidator
        validator = ContentValidator()
        posts_collection = validator.client.collections.get("Post")
        info = posts_collection.aggregate.over_all(total_count=True)
        validator.close()
        return {"status": "ok", "total_posts": info.total_count}
    except Exception as e:
        return {"status": "error", "details": str(e)}

@app.post("/v1/submit_action", tags=["Synchronous Actions"])
async def handle_synchronous_action(request: BlockchainRequestModel):
    """
    Handles simple, fast, JSON-only interactions like 'like', 'comment', 'referral', and 'tipping'.
    
    UNIVERSAL PRIMARY KEY LOGIC:
    - interactorAddress is ALWAYS the wallet that receives rewards
    - ALL scoring and limits are tracked by interactorAddress
    - creatorAddress is just for context/attribution
    """
    if not engine:
        return JSONResponse(
            status_code=500,
            content={"error": "Scoring engine not initialized"}
        )
    
    interaction_type = request.Interaction.interactionType.lower()
    creator_address = request.creatorAddress
    interactor_address = request.interactorAddress
    
    print(f"API: Processing '{interaction_type}' - Creator: {creator_address}, Interactor: {interactor_address}")
    
    # CRITICAL: interactorAddress is REQUIRED for ALL interactions
    if not interactor_address:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"interactorAddress is required for {interaction_type} actions",
                "reason": "interactorAddress is the universal wallet address for receiving rewards"
            }
        )
    
    # The user_id is ALWAYS the interactorAddress
    user_id = interactor_address
    
    try:
        # Handle comments asynchronously
        if interaction_type == "comment":
            print(f"API: Queued 'comment' validation job for user {user_id}.")
            
            validate_and_score_comment_task.delay(
                user_id=user_id,
                text_content=request.Interaction.data or "",
                webhook_url=request.webhookUrl,
                creator_address=creator_address,
                interactor_address=interactor_address
            )
            
            return JSONResponse(
                status_code=202,
                content={"status": "processing", "message": "Comment accepted for validation and scoring."}
            )
        
        # Handle synchronous actions
        elif interaction_type in ["like", "tipping", "referral"]:
            print(f"API: Processing synchronous '{interaction_type}' for user {user_id}.")
            
            # Award points - ALL go to interactorAddress
            points_awarded = 0.0
            if interaction_type == "like":
                points_awarded = engine.add_like_points(user_id)
            elif interaction_type == "referral":
                points_awarded = engine.add_referral_points(user_id)
            elif interaction_type == "tipping":
                points_awarded = engine.add_tipping_points(user_id)
            
            final_score = engine.get_final_score(user_id)
            
            ai_response = {
                "creatorAddress": creator_address,
                "interactorAddress": interactor_address,
                "rewardedUserId": user_id,  # Show which user got the rewards
                "Interaction": request.Interaction.model_dump(),
                "validation": {
                    "aiAgentResponseApproved": True,
                    "significanceScore": round(points_awarded, 4),
                    "reason": "Interaction processed successfully.",
                    "finalUserScore": round(final_score, 4)
                }
            }
            
            print(f"API: Successfully processed {interaction_type} - awarded {points_awarded} points to {user_id}")
            return JSONResponse(status_code=200, content=ai_response)
        
        else:
            return JSONResponse(
                status_code=400,
                content={"error": f"Unknown interaction type: {interaction_type}"}
            )
            
    except Exception as e:
        print(f"ERROR in handle_synchronous_action: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Internal server error: {str(e)}",
                "interaction_type": interaction_type,
                "user_addresses": {
                    "creator": creator_address,
                    "interactor": interactor_address
                }
            }
        )

@app.post("/v1/submit_post", 
    tags=["Asynchronous Actions (Posts)"],
    summary="Submit a post with optional image",
    description="""
    Submit a post that may include an image file.
    
    For posts, the creatorAddress is typically the same as interactorAddress (the post creator gets the rewards).
    """,
    responses={
        202: {
            "description": "Post accepted for processing",
            "content": {
                "application/json": {
                    "example": {"status": "processing", "message": "Post accepted for validation and scoring. Result will be sent to webhook."}
                }
            }
        },
        400: {
            "description": "Bad request",
            "content": {
                "application/json": {
                    "example": {"error": "interactorAddress is required for post submissions", "reason": "interactorAddress is the wallet address that will receive post rewards"}
                }
            }
        }
    }
)
async def handle_post_submission(
    creatorAddress: str = Form(..., description="The wallet address of the user creating the post"),
    interactorAddress: str = Form(..., description="The wallet address that will receive rewards (usually same as creatorAddress)"),
    interactionType: str = Form(default="post", description="The type of interaction (should be 'post')"),
    data: str = Form(..., description="The text content of the post"),
    webhookUrl: str = Form(..., description="URL where the validation result will be sent"),
    image: Optional[UploadFile] = File(None, description="Optional image file to attach to the post")
):
    """
    Handles 'post' submissions, which may include an image file.
    For posts, interactorAddress is the user who gets the rewards (since they created the content).
    """
    request_data = BlockchainRequestModel(
        creatorAddress=creatorAddress,
        interactorAddress=interactorAddress,
        Interaction=InteractionModel(
            interactionType=interactionType,
            data=data
        ),
        webhookUrl=webhookUrl
    )

    if not request_data.interactorAddress:
        return JSONResponse(
            status_code=400,
            content={
                "error": "interactorAddress is required for post submissions",
                "reason": "interactorAddress is the wallet address that will receive post rewards"
            }
        )
    
    image_path = None
    if image:
        temp_filename = f"{uuid.uuid4()}{os.path.splitext(image.filename)[1]}"
        image_path = os.path.join(UPLOAD_FOLDER, temp_filename)
        with open(image_path, "wb") as buffer:
            buffer.write(await image.read())
    user_id = request_data.interactorAddress

    process_and_score_post_task.delay(
        user_id=user_id,
        text_content=request_data.Interaction.data or "",
        image_path=image_path,
        webhook_url=request_data.webhookUrl,
        creator_address=request_data.creatorAddress,
        interactor_address=request_data.interactorAddress
    )
    
    print(f"API: Queued 'post' job for user {user_id}. Webhook: {request_data.webhookUrl}")
    
    return JSONResponse(
        status_code=202,
        content={"status": "processing", "message": "Post accepted for validation and scoring. Result will be sent to webhook."}
    )