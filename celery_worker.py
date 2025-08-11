from celery import Celery
import os
import requests
from typing import Optional
from core.ai_validator import ContentValidator
from core.scoring_engine import ScoringEngine
from core.historical_analyzer import HistoricalAnalyzer

celery_app = Celery(
    'tasks',
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
)
# --- NEW SECTION: CELERY BEAT SCHEDULE ---
celery_app.conf.beat_schedule = {
    'run-daily-user-analysis': {
        'task': 'daily_empathy_analysis_task',
        # 'schedule': 86400.0,  # 86400 seconds = 24 hours
        'schedule': 240.0,  # 240 seconds = 4 minutes for testing
        # For testing, you can set a shorter schedule, e.g., 60.0 for every minute
        # 'schedule': 200.0,n
    }
}
celery_app.conf.timezone = 'UTC'



@celery_app.task(name="process_and_score_post_task")
def process_and_score_post_task(
    user_id: str,
    text_content: str,
    image_path: Optional[str],
    webhook_url: str,
    creator_address: str,
    interactor_address: Optional[str]
):
    """Background task that validates, scores, and sends the final result for a post to a webhook."""
    print(f"WORKER: Received 'post' job for user {user_id}")
    ai_response = {
        "creatorAddress": creator_address,
        "interactorAddress": interactor_address,
        "post_id": None,
        "Interaction": {"interactionType": "post", "data": text_content},
        "validation": {"aiAgentResponseApproved": False, "significanceScore": 0.0, "reason": "Processing started"}
    }
    validator, engine = None, None
    try:
        validator = ContentValidator()
        engine = ScoringEngine()
        
        print(f"WORKER: Starting validation for post from user {user_id}")
        print(f"WORKER: Post content preview: '{text_content[:50]}...'")
        
        validation_result = validator.process_new_post(user_id, text_content, image_path)
        if validation_result:
            post_id, originality_distance = validation_result
            points_awarded = engine.add_qualitative_post_points(user_id, text_content, image_path, originality_distance)
            ai_response["post_id"] = post_id
            ai_response["validation"]["aiAgentResponseApproved"] = True
            ai_response["validation"]["significanceScore"] = round(points_awarded, 4)
            ai_response["validation"]["reason"] = "Content approved and scored."
            print(f"WORKER: Post job for user {user_id} succeeded with {points_awarded} points.")
        else:
            ai_response["validation"]["reason"] = "Content failed validation (gibberish or duplicate)."
            print(f"WORKER: Post job for user {user_id} failed validation.")
    except Exception as e:
        print(f"WORKER ERROR (Post): An unexpected error occurred for user {user_id}. Details: {e}")
        import traceback
        print(f"WORKER ERROR (Post): Traceback: {traceback.format_exc()}")
        ai_response["validation"]["reason"] = f"An internal error occurred: {e}"
    finally:
        if validator: validator.close()
        if engine: engine.close()
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            print(f"WORKER: Cleaned up temp file: {image_path}")
        if webhook_url:
            try:
                print(f"WORKER: Sending 'post' response to webhook: {webhook_url}")
                requests.post(webhook_url, json=ai_response, timeout=15)
            except requests.RequestException as e:
                print(f"WORKER CRITICAL: Failed to send webhook to {webhook_url}. Details: {e}")
    return ai_response

@celery_app.task(name="validate_and_score_comment_task")
def validate_and_score_comment_task(
    user_id: str, 
    text_content: str, 
    webhook_url: Optional[str], 
    creator_address: str,
    interactor_address: str
):
    """Background task that validates a comment for gibberish, scores it."""
    print(f"WORKER: Received 'comment' job for user {user_id}")
    ai_response = {
        "creatorAddress": creator_address,
        "interactorAddress": interactor_address,
        "Interaction": {"interactionType": "comment", "data": text_content},
        "validation": {"aiAgentResponseApproved": False, "significanceScore": 0.0, "reason": "Processing started"}
    }
    validator, engine = None, None
    try:
        validator = ContentValidator()
        engine = ScoringEngine()
        
        print(f"WORKER: Starting validation for comment from user {user_id}")
        print(f"WORKER: Comment content: '{text_content}'")
        
        if not text_content or validator.is_gibberish(text_content):
            ai_response["validation"]["reason"] = "Content failed validation (gibberish)."
            print(f"WORKER: Comment from {user_id} failed gibberish check.")
        else:
            points_awarded = engine.add_comment_points(user_id)
            if points_awarded > 0:
                ai_response["validation"]["aiAgentResponseApproved"] = True
                ai_response["validation"]["significanceScore"] = round(points_awarded, 4)
                ai_response["validation"]["reason"] = "Comment approved and scored."
                print(f"WORKER: Comment job for user {user_id} succeeded with {points_awarded} points.")
            else:
                ai_response["validation"]["reason"] = "Comment rejected due to daily limit."
                print(f"WORKER: Comment from {user_id} hit daily limit.")
    except Exception as e:
        print(f"WORKER ERROR (Comment): An unexpected error occurred for user {user_id}. Details: {e}")
        import traceback
        print(f"WORKER ERROR (Comment): Traceback: {traceback.format_exc()}")
        ai_response["validation"]["reason"] = f"An internal error occurred: {e}"
    finally:
        if validator: validator.close()
        if engine: engine.close()
        if webhook_url:
            try:
                print(f"WORKER: Sending 'comment' response to webhook: {webhook_url}")
                requests.post(webhook_url, json=ai_response, timeout=15)
            except requests.RequestException as e:
                print(f"WORKER CRITICAL: Failed to send comment webhook to {webhook_url}. Details: {e}")
    return ai_response


@celery_app.task(name="daily_empathy_analysis_task")
def daily_empathy_analysis_task():
    """
    A scheduled daily task that initiates the historical user analysis
    to provide "empathy" rewards for loyal but recently inactive users.
    """
    print("SCHEDULER: Kicking off the daily user empathy analysis.")
    analyzer = None
    try:
        analyzer = HistoricalAnalyzer()
        analyzer.analyze_and_reward_users()
        print("SCHEDULER: Daily analysis completed successfully.")
    except Exception as e:
        import traceback
        print(f"SCHEDULER CRITICAL: The daily empathy analysis task failed. Error: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    finally:
        if analyzer:
            analyzer.close()