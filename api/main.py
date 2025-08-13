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
from core.historical_analyzer import HistoricalAnalyzer
from datetime import datetime, timezone, timedelta
from fastapi.middleware.cors import CORSMiddleware



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

# Key changes to add to your main.py in the handle_synchronous_action functi

@app.post("/v1/submit_action", tags=["Synchronous Actions"])
async def handle_synchronous_action(request: BlockchainRequestModel):
    """
    Handles simple, fast, JSON-only interactions like 'like', 'comment', 'referral', 'tipping', and 'crypto'.
    
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
        
        # Handle synchronous actions - UPDATED TO INCLUDE CRYPTO
        elif interaction_type in ["like", "tipping", "referral", "crypto"]:
            print(f"API: Processing synchronous '{interaction_type}' for user {user_id}.")
            
            # Award points - ALL go to interactorAddress
            points_awarded = 0.0
            if interaction_type == "like":
                points_awarded = engine.add_like_points(user_id)
            elif interaction_type == "referral":
                points_awarded = engine.add_referral_points(user_id)
            elif interaction_type == "tipping":
                points_awarded = engine.add_tipping_points(user_id)
            elif interaction_type == "crypto":  # NEW CRYPTO HANDLING
                points_awarded = engine.add_crypto_points(user_id)
            
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
# Updated admin endpoints in main.py for category-wise analysis

@app.post("/admin/run-daily-analysis", tags=["Admin"])
def run_daily_analysis():
    """
    Manually trigger the category-wise daily user analysis and reward distribution.
    This will:
    1. Analyze each category (posts, likes, comments, crypto, tipping, referrals) independently
    2. Award qualified users for each category they meet requirements for
    3. Calculate category-specific empathy scores for non-qualified users
    4. Award top 10% of non-qualified users per category (empathy rewards)
    5. Make API calls to distribute category-wise rewards
    """
    try:
        analyzer = HistoricalAnalyzer()
        print(f"Starting category-wise daily analysis at {datetime.now(timezone.utc)}")
        
        category_results = analyzer.analyze_and_reward_users()
        analyzer.close()
        
        return {
            "status": "success",
            "message": "Category-wise daily analysis completed and API calls made for reward distribution",
            "analysis_type": "category_based",
            "results": category_results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR in category-wise daily analysis: {e}")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        )

@app.get("/admin/daily-summary", tags=["Admin"])
def get_daily_summary():
    """
    Get a category-wise summary of today's user activity and potential rewards without making API calls.
    Shows qualification status and empathy candidates for each category independently.
    """
    try:
        analyzer = HistoricalAnalyzer()
        summary = analyzer.get_daily_summary()
        analyzer.close()
        
        return {
            "status": "success",
            "data": summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR getting category-wise daily summary: {e}")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        )

@app.get("/admin/user-activity/{user_id}", tags=["Admin"])
def get_user_activity(user_id: str):
    """
    Get detailed category-wise activity information for a specific user.
    Shows their qualification status and potential empathy eligibility for each category.
    """
    try:
        if not engine:
            return JSONResponse(
                status_code=500,
                content={"error": "Scoring engine not initialized"}
            )
        
        # Import config here to avoid circular imports
        from core import scoring_config as config
        # Fix datetime import issue
        from datetime import datetime, timezone, timedelta
        
        conn = engine._get_conn()
        try:
            with conn.cursor() as cur:
                # First check if user exists
                cur.execute("SELECT user_id FROM user_scores WHERE user_id = %s;", (user_id,))
                if not cur.fetchone():
                    return JSONResponse(
                        status_code=404,
                        content={"error": f"User {user_id} not found"}
                    )
                
                # Get user data with proper column handling
                cur.execute("""
                    SELECT 
                        user_id, last_active_date, consecutive_activity_days, historical_engagement_score,
                        points_from_posts, points_from_likes, points_from_comments, 
                        points_from_referrals, points_from_tipping, 
                        COALESCE(points_from_crypto, 0) as points_from_crypto,
                        daily_posts_timestamps, daily_likes_timestamps, daily_comments_timestamps,
                        daily_referrals_timestamps, daily_tipping_timestamps,
                        COALESCE(daily_crypto_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_crypto_timestamps
                    FROM user_scores 
                    WHERE user_id = %s;
                """, (user_id,))
                
                user_data = cur.fetchone()
                if not user_data:
                    return JSONResponse(
                        status_code=404,
                        content={"error": f"User {user_id} not found"}
                    )
                
                (user_id, last_active_date, streak, hist_score, p_posts, p_likes, p_comments, 
                 p_referrals, p_tipping, p_crypto, post_ts, like_ts, comment_ts, 
                 referral_ts, tipping_ts, crypto_ts) = user_data
                
                # Calculate today's activity for each category - FIXED DATETIME USAGE
                now = datetime.now(timezone.utc)
                twenty_four_hours_ago = now - timedelta(hours=24)
                
                posts_today = len([ts for ts in (post_ts or []) if ts > twenty_four_hours_ago])
                likes_today = len([ts for ts in (like_ts or []) if ts > twenty_four_hours_ago])
                comments_today = len([ts for ts in (comment_ts or []) if ts > twenty_four_hours_ago])
                crypto_today = len([ts for ts in (crypto_ts or []) if ts > twenty_four_hours_ago])
                tipping_today = len([ts for ts in (tipping_ts or []) if ts > twenty_four_hours_ago])
                referrals_today = len([ts for ts in (referral_ts or []) if ts > twenty_four_hours_ago])
                
                # Check qualification for each category with safe config access
                category_status = {
                    "posts": {
                        "activity_today": posts_today,
                        "required_for_qualification": getattr(config, 'POST_LIMIT_DAY', 2),
                        "qualified": posts_today >= getattr(config, 'POST_LIMIT_DAY', 2),
                        "monthly_points": p_posts or 0,
                        "monthly_limit": getattr(config, 'MAX_MONTHLY_POST_POINTS', 30)
                    },
                    "likes": {
                        "activity_today": likes_today,
                        "required_for_qualification": getattr(config, 'LIKE_LIMIT_DAY', 5),
                        "qualified": likes_today >= getattr(config, 'LIKE_LIMIT_DAY', 5),
                        "monthly_points": p_likes or 0,
                        "monthly_limit": getattr(config, 'MAX_MONTHLY_LIKE_POINTS', 15)
                    },
                    "comments": {
                        "activity_today": comments_today,
                        "required_for_qualification": getattr(config, 'COMMENT_LIMIT_DAY', 5),
                        "qualified": comments_today >= getattr(config, 'COMMENT_LIMIT_DAY', 5),
                        "monthly_points": p_comments or 0,
                        "monthly_limit": getattr(config, 'MAX_MONTHLY_COMMENT_POINTS', 15)
                    },
                    "crypto": {
                        "activity_today": crypto_today,
                        "required_for_qualification": getattr(config, 'CRYPTO_LIMIT_DAY', 3),
                        "qualified": crypto_today >= getattr(config, 'CRYPTO_LIMIT_DAY', 3),
                        "monthly_points": p_crypto or 0,
                        "monthly_limit": getattr(config, 'MAX_MONTHLY_CRYPTO_POINTS', 20)
                    },
                    "tipping": {
                        "activity_today": tipping_today,
                        "required_for_qualification": getattr(config, 'TIPPING_LIMIT_DAY', 1),
                        "qualified": tipping_today >= getattr(config, 'TIPPING_LIMIT_DAY', 1),
                        "monthly_points": p_tipping or 0,
                        "monthly_limit": getattr(config, 'MAX_MONTHLY_TIPPING_POINTS', 20)
                    },
                    "referrals": {
                        "activity_today": referrals_today,
                        "required_for_qualification": getattr(config, 'REFERRAL_LIMIT_DAY', 1),
                        "qualified": referrals_today >= getattr(config, 'REFERRAL_LIMIT_DAY', 1),
                        "monthly_points": p_referrals or 0,
                        "monthly_limit": getattr(config, 'MAX_MONTHLY_REFERRAL_POINTS', 10)
                    }
                }
                
                # Calculate final score
                final_score = engine.get_final_score(user_id)
                
                # Count qualified categories
                qualified_categories = [cat for cat, status in category_status.items() if status["qualified"]]
                
                return {
                    "status": "success",
                    "user_id": user_id,
                    "analysis_type": "category_based",
                    "category_breakdown": category_status,
                    "summary": {
                        "qualified_categories": qualified_categories,
                        "qualified_count": len(qualified_categories),
                        "total_categories": len(category_status),
                        "final_score": round(final_score, 4)
                    },
                    "engagement_data": {
                        "consecutive_activity_days": streak or 0,
                        "historical_engagement_score": hist_score or 0,
                        "last_active_date": last_active_date.isoformat() if last_active_date else None
                    },
                    "reward_eligibility": {
                        "qualified_for_regular_rewards": qualified_categories,
                        "eligible_for_empathy_rewards": [
                            cat for cat, status in category_status.items() 
                            if not status["qualified"] and status["monthly_points"] > 0
                        ]
                    }
                }
                
        finally:
            engine._put_conn(conn)
            
    except Exception as e:
        print(f"ERROR getting user activity for {user_id}: {e}")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        )
@app.get("/admin/category-summary", tags=["Admin"])
def get_category_summary():
    """
    Get a summary of all categories and their requirements.
    Useful for understanding the qualification criteria for each category.
    """
    try:
        # Import config here to avoid circular imports
        from core import scoring_config as config
        categories = {
            'posts': {
                'name': 'Content Creation Rewards',
                'description': 'Rewards for users who create quality posts',
                'daily_requirement': getattr(config, 'POST_LIMIT_DAY', 2),
                'point_value': getattr(config, 'POINTS_PER_POST', 0.5)
            },
            'likes': {
                'name': 'Engagement Rewards', 
                'description': 'Rewards for users who actively like content',
                'daily_requirement': getattr(config, 'LIKE_LIMIT_DAY', 5),
                'point_value': getattr(config, 'POINTS_PER_LIKE', 0.1)
            },
            'comments': {
                'name': 'Discussion Rewards',
                'description': 'Rewards for users who participate in discussions',
                'daily_requirement': getattr(config, 'COMMENT_LIMIT_DAY', 5),
                'point_value': getattr(config, 'POINTS_PER_COMMENT', 0.1)
            },
            'crypto': {
                'name': 'Crypto Activity Rewards',
                'description': 'Rewards for users who perform crypto transactions',
                'daily_requirement': getattr(config, 'CRYPTO_LIMIT_DAY', 3),
                'point_value': getattr(config, 'POINTS_FOR_CRYPTO', 0.5)
            },
            'tipping': {
                'name': 'Community Support Rewards',
                'description': 'Rewards for users who tip other community members',
                'daily_requirement': getattr(config, 'TIPPING_LIMIT_DAY', 1),
                'point_value': getattr(config, 'POINTS_FOR_TIPPING', 0.5)
            },
            'referrals': {
                'name': 'Growth Rewards',
                'description': 'Rewards for users who bring new members to the community',
                'daily_requirement': getattr(config, 'REFERRAL_LIMIT_DAY', 1),
                'point_value': getattr(config, 'POINTS_PER_REFERRAL', 10)
            }
        }
        
        return {
            "status": "success",
            "analysis_type": "category_based",
            "categories": categories,
            "empathy_config": {
                "percentage_selected": getattr(config, 'REWARD_PERCENTAGE_OF_INACTIVE', 0.10),
                "description": "Top 10% of non-qualified users per category receive empathy rewards"
            },
            "monthly_limits": {
                "posts": getattr(config, 'MAX_MONTHLY_POST_POINTS', 30),
                "likes": getattr(config, 'MAX_MONTHLY_LIKE_POINTS', 15),
                "comments": getattr(config, 'MAX_MONTHLY_COMMENT_POINTS', 15),
                "crypto": getattr(config, 'MAX_MONTHLY_CRYPTO_POINTS', 20),
                "tipping": getattr(config, 'MAX_MONTHLY_TIPPING_POINTS', 20),
                "referrals": getattr(config, 'MAX_MONTHLY_REFERRAL_POINTS', 10),
                "total_possible": getattr(config, 'TOTAL_POSSIBLE_MONTHLY_POINTS', 110)
            }
        }
        
    except Exception as e:
        print(f"ERROR getting category summary: {e}")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        )
    
# PART 1: Add the missing close() method to your HistoricalAnalyzer class

def close(self):
    """Closes all connections in the database pool."""
    if hasattr(self, 'db_pool') and self.db_pool:
        self.db_pool.closeall()
        print("HistoricalAnalyzer: DB connection pool closed.")

# PART 2: Updated and fixed API endpoints for main.py

from core.historical_analyzer import HistoricalAnalyzer
from datetime import datetime, timezone, timedelta
import math

# Individual category endpoints
@app.get("/api/rewards/posts", tags=["Category Rewards"])
def get_post_rewards():
    """Get qualified and empathy users for POST category."""
    try:
        analyzer = HistoricalAnalyzer()
        category_result = analyzer._get_category_results("posts")
        analyzer.close()
        
        return {
            "status": "success",
            "category": "posts",
            "daily_requirement": 2,
            "qualified_users": category_result["qualified"],
            "empathy_users": category_result["empathy"],
            "stats": {
                "qualified_count": len(category_result["qualified"]),
                "empathy_count": len(category_result["empathy"]),
                "total_users_analyzed": category_result["total_analyzed"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR in get_post_rewards: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "category": "posts", "error": str(e)}
        )

@app.get("/api/rewards/likes", tags=["Category Rewards"])
def get_like_rewards():
    """Get qualified and empathy users for LIKE category."""
    try:
        analyzer = HistoricalAnalyzer()
        category_result = analyzer._get_category_results("likes")
        analyzer.close()
        
        return {
            "status": "success",
            "category": "likes",
            "daily_requirement": 5,
            "qualified_users": category_result["qualified"],
            "empathy_users": category_result["empathy"],
            "stats": {
                "qualified_count": len(category_result["qualified"]),
                "empathy_count": len(category_result["empathy"]),
                "total_users_analyzed": category_result["total_analyzed"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR in get_like_rewards: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "category": "likes", "error": str(e)}
        )

@app.get("/api/rewards/comments", tags=["Category Rewards"])
def get_comment_rewards():
    """Get qualified and empathy users for COMMENT category."""
    try:
        analyzer = HistoricalAnalyzer()
        category_result = analyzer._get_category_results("comments")
        analyzer.close()
        
        return {
            "status": "success",
            "category": "comments",
            "daily_requirement": 5,
            "qualified_users": category_result["qualified"],
            "empathy_users": category_result["empathy"],
            "stats": {
                "qualified_count": len(category_result["qualified"]),
                "empathy_count": len(category_result["empathy"]),
                "total_users_analyzed": category_result["total_analyzed"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR in get_comment_rewards: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "category": "comments", "error": str(e)}
        )

@app.get("/api/rewards/crypto", tags=["Category Rewards"])
def get_crypto_rewards():
    """Get qualified and empathy users for CRYPTO category."""
    try:
        analyzer = HistoricalAnalyzer()
        category_result = analyzer._get_category_results("crypto")
        analyzer.close()
        
        return {
            "status": "success",
            "category": "crypto",
            "daily_requirement": 3,
            "qualified_users": category_result["qualified"],
            "empathy_users": category_result["empathy"],
            "stats": {
                "qualified_count": len(category_result["qualified"]),
                "empathy_count": len(category_result["empathy"]),
                "total_users_analyzed": category_result["total_analyzed"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR in get_crypto_rewards: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "category": "crypto", "error": str(e)}
        )

@app.get("/api/rewards/tipping", tags=["Category Rewards"])
def get_tipping_rewards():
    """Get qualified and empathy users for TIPPING category."""
    try:
        analyzer = HistoricalAnalyzer()
        category_result = analyzer._get_category_results("tipping")
        analyzer.close()
        
        return {
            "status": "success",
            "category": "tipping",
            "daily_requirement": 1,
            "qualified_users": category_result["qualified"],
            "empathy_users": category_result["empathy"],
            "stats": {
                "qualified_count": len(category_result["qualified"]),
                "empathy_count": len(category_result["empathy"]),
                "total_users_analyzed": category_result["total_analyzed"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR in get_tipping_rewards: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "category": "tipping", "error": str(e)}
        )

@app.get("/api/rewards/referrals", tags=["Category Rewards"])
def get_referral_rewards():
    """Get qualified and empathy users for REFERRAL category."""
    try:
        analyzer = HistoricalAnalyzer()
        category_result = analyzer._get_category_results("referrals")
        analyzer.close()
        
        return {
            "status": "success",
            "category": "referrals",
            "daily_requirement": 1,
            "qualified_users": category_result["qualified"],
            "empathy_users": category_result["empathy"],
            "stats": {
                "qualified_count": len(category_result["qualified"]),
                "empathy_count": len(category_result["empathy"]),
                "total_users_analyzed": category_result["total_analyzed"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR in get_referral_rewards: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "category": "referrals", "error": str(e)}
        )

# Special endpoint for ALL categories
@app.get("/api/rewards/all", tags=["Category Rewards"])
def get_all_category_rewards():
    """Get qualified and empathy users for ALL categories at once."""
    try:
        analyzer = HistoricalAnalyzer()
        
        categories = ["posts", "likes", "comments", "crypto", "tipping", "referrals"]
        all_results = {}
        
        for category in categories:
            try:
                category_result = analyzer._get_category_results(category)
                all_results[category] = {
                    "qualified_users": category_result["qualified"],
                    "empathy_users": category_result["empathy"],
                    "qualified_count": len(category_result["qualified"]),
                    "empathy_count": len(category_result["empathy"])
                }
            except Exception as cat_error:
                print(f"ERROR processing category {category}: {cat_error}")
                all_results[category] = {
                    "qualified_users": [],
                    "empathy_users": [],
                    "qualified_count": 0,
                    "empathy_count": 0,
                    "error": str(cat_error)
                }
        
        analyzer.close()
        
        # Calculate totals
        total_qualified = sum(result["qualified_count"] for result in all_results.values())
        total_empathy = sum(result["empathy_count"] for result in all_results.values())
        
        return {
            "status": "success",
            "categories": all_results,
            "summary": {
                "total_qualified_across_categories": total_qualified,
                "total_empathy_across_categories": total_empathy,
                "categories_analyzed": len(categories)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR in get_all_category_rewards: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(e)}
        )

# UPDATED generic endpoint that handles 'all' specially
@app.get("/api/rewards/{category}", tags=["Category Rewards"])
def get_category_rewards(category: str):
    """Generic endpoint to get qualified and empathy users for any category."""
    # Special handling for 'all'
    if category.lower() == "all":
        return get_all_category_rewards()
    
    valid_categories = ["posts", "likes", "comments", "crypto", "tipping", "referrals"]
    
    if category.lower() not in valid_categories:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "error": f"Invalid category '{category}'",
                "valid_categories": valid_categories + ["all"]
            }
        )
    
    try:
        analyzer = HistoricalAnalyzer()
        category_result = analyzer._get_category_results(category.lower())
        analyzer.close()
        
        # Get daily requirement for the category
        daily_requirements = {
            "posts": 2,
            "likes": 5,
            "comments": 5,
            "crypto": 3,
            "tipping": 1,
            "referrals": 1
        }
        
        return {
            "status": "success",
            "category": category.lower(),
            "daily_requirement": daily_requirements.get(category.lower(), 1),
            "qualified_users": category_result["qualified"],
            "empathy_users": category_result["empathy"],
            "stats": {
                "qualified_count": len(category_result["qualified"]),
                "empathy_count": len(category_result["empathy"]),
                "total_users_analyzed": category_result["total_analyzed"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"ERROR in get_category_rewards for {category}: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "category": category, "error": str(e)}
        )