# celery_worker.py (New Production Version)

from celery import Celery
import os
import requests
from typing import Optional

# These are imported here but will be instantiated inside the task
from core.ai_validator import ContentValidator
from core.scoring_engine import ScoringEngine

# --- Celery App Configuration ---
# celery_app = Celery(
#     'tasks',
#     broker='redis://redis:6379/0',     # Use Docker service name
#     backend='redis://redis:6379/0'     # Use Docker service name
# )
celery_app = Celery(
    'tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)


# --- The Main Background Task ---
@celery_app.task(name="process_and_score_post_task")
def process_and_score_post_task(
    user_id: str,
    text_content: str,
    image_path: Optional[str],
    webhook_url: str,
    interactor_address: Optional[str] # **THE FIX:** Parameter name changed to snake_case
):
    """
    Background task that validates, scores, and sends the final result to a webhook.
    """
    print(f"WORKER: Received job for user {user_id}")
    
    # **THE FIX:** Use the passed-in 'interactor_address' when building the response.
    ai_response = {
        "creatorAddress": user_id,
        "interactorAddress": interactor_address, # Use the value from the function argument
        "post_id": None,
        "Interaction": {"interactionType": "post", "data": text_content},
        "validation": {
            "aiAgentResponseApproved": False,
            "significanceScore": 0.0,
            "reason": "Processing started"
        }
    }
    validator = None
    engine = None
    try:
        # Instantiate services here to ensure they are fresh for each task
        validator = ContentValidator()
        engine = ScoringEngine()

        # Perform validation
        validation_result = validator.process_new_post(user_id, text_content, image_path)

        if validation_result:
            post_id, originality_distance = validation_result
            
            # If validation passes, score the post
            points_awarded = engine.add_qualitative_post_points(
                user_id=user_id,
                text_content=text_content,
                image_path=image_path,
                originality_distance=originality_distance
            )
            
            # Populate the success response
            ai_response["post_id"] = post_id
            ai_response["validation"]["aiAgentResponseApproved"] = True
            ai_response["validation"]["significanceScore"] = round(points_awarded, 4)
            ai_response["validation"]["reason"] = "Content approved and scored."
            print(f"WORKER: Job for user {user_id} succeeded.")

        else:
            # If validation fails, populate the rejection reason
            ai_response["validation"]["reason"] = "Content failed validation (gibberish or duplicate)."
            print(f"WORKER: Job for user {user_id} failed validation.")

    except Exception as e:
        print(f"WORKER: An unexpected error occurred for user {user_id}. Details: {e}")
        ai_response["validation"]["reason"] = f"An internal error occurred: {e}"

    finally:
        # Ensure connections are closed
        if validator: validator.close()
        if engine: engine.close()

        # Clean up the temporary image file
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            print(f"WORKER: Cleaned up temp file: {image_path}")

        # Send the final response to the webhook
        try:
            print(f"WORKER: Sending final response to webhook: {webhook_url}")
            requests.post(webhook_url, json=ai_response, timeout=15)
        except requests.RequestException as e:
            print(f"WORKER CRITICAL ERROR: Failed to send webhook to {webhook_url}. Details: {e}")
            # In a real system, you would re-queue this or log it to an error monitoring service.

    return ai_response # Return the response for Celery's own logging


# In celery_worker.py

# ... (imports and existing celery_app setup) ...

# --- NEW Task for Validating Comments ---
@celery_app.task(name="validate_and_score_comment_task")
def validate_and_score_comment_task(user_id: str, text_content: str, webhook_url: Optional[str]):
    """
    Background task that validates a comment for gibberish and then scores it.
    """
    print(f"WORKER: Received comment validation job for user {user_id}")
    
    # Prepare the structure of the final JSON response
    ai_response = {
        "creatorAddress": user_id,
        "Interaction": {"interactionType": "comment", "data": text_content},
        "validation": {
            "aiAgentResponseApproved": False,
            "significanceScore": 0.0,
            "reason": "Processing started"
        }
    }

    validator = None
    engine = None
    try:
        # Instantiate services fresh for this task
        validator = ContentValidator()
        engine = ScoringEngine()

        # Perform the gibberish check
        if not text_content or validator.is_gibberish(text_content):
            ai_response["validation"]["reason"] = "Content failed validation (gibberish)."
            print(f"WORKER: Comment from {user_id} failed gibberish check.")
        else:
            # If the comment is valid, award points
            points_awarded = engine.add_comment_points(user_id)
            
            # Populate the success response
            ai_response["validation"]["aiAgentResponseApproved"] = True
            ai_response["validation"]["significanceScore"] = round(points_awarded, 4)
            ai_response["validation"]["reason"] = "Comment approved and scored."
            print(f"WORKER: Comment job for user {user_id} succeeded.")

    except Exception as e:
        print(f"WORKER: An unexpected error occurred for comment job {user_id}. Details: {e}")
        ai_response["validation"]["reason"] = f"An internal error occurred: {e}"

    finally:
        # Ensure connections are closed
        if validator: validator.close()
        if engine: engine.close()

        # Send the final response to the webhook if a URL was provided
        if webhook_url:
            try:
                print(f"WORKER: Sending comment response to webhook: {webhook_url}")
                requests.post(webhook_url, json=ai_response, timeout=15)
            except requests.RequestException as e:
                print(f"WORKER CRITICAL ERROR: Failed to send comment webhook to {webhook_url}. Details: {e}")

    return ai_response