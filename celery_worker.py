# from celery import Celery
# import os

# from core.ai_validator import ContentValidator
# from core.scoring_engine import ScoringEngine

# celery_app = Celery(
#     'tasks',
#     broker='redis://localhost:6379/0',
#     backend='redis://localhost:6379/0'
# )


# validator = ContentValidator()
# engine = ScoringEngine()

# @celery_app.task(name="process_and_score_post_task")
# def process_and_score_post_task(user_id: str, text_content: str, image_path: str):
#     """
#     This is the background task that performs all the heavy AI work.
#     """
#     print(f"WORKER: Received job for user {user_id}")
#     try:
#         validation_result = validator.process_new_post(
#             user_id=user_id,
#             text_content=text_content,
#             image_path=image_path
#         )

#         if not validation_result:
#             print(f"WORKER: Post by {user_id} failed validation. Job complete.")
#             return {"status": "rejected", "reason": "Content failed validation."}

#         post_id, originality_distance = validation_result
#         print(f"WORKER: Post {post_id} is valid. Awarding points...")

#         engine.add_qualitative_post_points(
#             user_id=user_id,
#             text_content=text_content,
#             image_path=image_path,
#             originality_distance=originality_distance
#         )
#         print(f"WORKER: Job for user {user_id} complete.")
#         return {"status": "success", "post_id": post_id}
    
#     finally:
#         # Clean up the image file passed to the worker
#         if os.path.exists(image_path):
#             os.remove(image_path)


from celery import Celery
import os
import traceback

from core.ai_validator import ContentValidator
from core.scoring_engine import ScoringEngine

celery_app = Celery(
    'tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# Initialize these inside the task function to avoid sharing state between workers
# validator = ContentValidator()
# engine = ScoringEngine()

@celery_app.task(name="process_and_score_post_task")
def process_and_score_post_task(user_id: str, text_content: str, image_path: str):
    """
    This is the background task that performs all the heavy AI work.
    """
    print(f"WORKER: Received job for user {user_id}")
    
    # Initialize validator and engine inside the task to avoid shared state issues
    validator = None
    engine = None
    
    try:
        # Initialize components
        validator = ContentValidator()
        engine = ScoringEngine()
        
        # Validate inputs
        if not user_id or not text_content:
            print(f"WORKER: Invalid inputs for user {user_id}")
            return {"status": "rejected", "reason": "Invalid input data."}
        
        # Check if image file exists (if provided)
        if image_path and not os.path.exists(image_path):
            print(f"WORKER: Image file not found: {image_path}")
            image_path = None  # Continue without image
        
        print(f"WORKER: Processing post validation for user {user_id}")
        validation_result = validator.process_new_post(
            user_id=user_id,
            text_content=text_content,
            image_path=image_path
        )

        if not validation_result:
            print(f"WORKER: Post by {user_id} failed validation. Job complete.")
            return {"status": "rejected", "reason": "Content failed validation."}

        # Handle different types of validation results
        if isinstance(validation_result, tuple) and len(validation_result) >= 2:
            post_id, originality_distance = validation_result[0], validation_result[1]
        else:
            print(f"WORKER: Unexpected validation result format: {validation_result}")
            return {"status": "rejected", "reason": "Validation result format error."}

        print(f"WORKER: Post {post_id} is valid. Awarding points...")

        # Add qualitative points
        engine.add_qualitative_post_points(
            user_id=user_id,
            text_content=text_content,
            image_path=image_path,
            originality_distance=originality_distance
        )
        
        print(f"WORKER: Job for user {user_id} complete.")
        return {"status": "success", "post_id": post_id}
    
    except Exception as e:
        error_msg = f"WORKER ERROR for user {user_id}: {str(e)}"
        print(error_msg)
        print(f"WORKER: Full traceback: {traceback.format_exc()}")
        return {"status": "error", "reason": error_msg}
    
    finally:
        # Clean up the image file passed to the worker
        try:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
                print(f"WORKER: Cleaned up image file: {image_path}")
        except Exception as cleanup_error:
            print(f"WORKER: Error during cleanup: {cleanup_error}")
        
        # Close database connections if they exist
        try:
            if engine:
                engine.close()
        except Exception as close_error:
            print(f"WORKER: Error closing engine: {close_error}")