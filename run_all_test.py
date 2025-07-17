

import requests
import json
import os
import time
import uuid
from PIL import Image

BASE_API_URL = os.getenv("API_URL", "http://localhost:8000")
HEALTH_URL = f"{BASE_API_URL}/health"
SYNC_API_URL = f"{BASE_API_URL}/v1/submit_action"
ASYNC_POST_URL = f"{BASE_API_URL}/v1/submit_post"

WEBHOOK_URL = "https://webhook.site/fb737657-2e62-4aac-bff5-bfaffe897fd7"  


def print_header(title):
    """Prints a formatted header to the console."""
    print(f"\n\n{'='*60}\n          {title.upper()}\n{'='*60}")

def get_health_check():
    """Checks the API /health endpoint."""
    print_header("1. System Health Check")
    try:
        response = requests.get(HEALTH_URL, timeout=10)
        response.raise_for_status()
        print(f"--> [HEALTH CHECK] GET {HEALTH_URL}")
        print(f"<-- [API RESPONSE] Status: {response.status_code}, Body: {response.json()}")
        print("--- HEALTH CHECK PASSED ---")
    except requests.RequestException as e:
        print(f"--- HEALTH CHECK FAILED: Cannot connect to API. Details: {e} ---")
        exit()

def test_synchronous_action(payload: dict, test_name: str):
    """Sends a raw JSON payload to the synchronous action endpoint."""
    interaction_type = payload.get("Interaction", {}).get("interactionType", "unknown")
    user = payload.get("creatorAddress", "unknown")
    print(f"\n--> [SYNC TEST: {test_name}] Sending '{interaction_type}' for user '{user}'")
    
    try:
        response = requests.post(SYNC_API_URL, json=payload, timeout=15)
        print(f"<-- [API RESPONSE] Status: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(f"Response Body: {response.text}")
    except requests.RequestException as e:
        print(f"An error occurred: {e}")

def test_asynchronous_action(payload: dict, image_path: str = None, test_name: str = "Async Action"):
    """Sends a request that will be processed asynchronously (comment or post)."""
    interaction_type = payload.get("Interaction", {}).get("interactionType", "unknown")
    user = payload.get("creatorAddress", "unknown")
    
    if interaction_type == "comment":
        print(f"\n--> [ASYNC TEST: {test_name}] Sending '{interaction_type}' for user '{user}' to be queued")
        target_url = SYNC_API_URL # Comments go to the action endpoint
        files = None
        data = None
        json_payload = payload
    elif interaction_type == "post":
        print(f"\n--> [ASYNC TEST: {test_name}] Sending '{interaction_type}' for user '{user}' to be queued")
        target_url = ASYNC_POST_URL # Posts go to the post endpoint
        files = {'request': (None, json.dumps(payload), 'application/json')}
        if image_path and os.path.exists(image_path):
            files['image'] = (os.path.basename(image_path), open(image_path, 'rb'), 'image/png')
            print(f"    Attaching image: {image_path}")
        else:
            print("    Sending post without an image.")
        json_payload = None # Using files, not json
    else:
        print(f"Unknown async action type: {interaction_type}")
        return

    try:
        response = requests.post(target_url, json=json_payload, files=files, timeout=15)
        print(f"<-- [API RESPONSE] Status: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(f"Response Body: {response.text}")
    except requests.RequestException as e:
        print(f"An error occurred: {e}")

# --- Main Execution Block ---

if __name__ == "__main__":
    print(f"API tests starting. Asynchronous results will appear at: {WEBHOOK_URL}")
    
    # Generate a unique ID for this test run to ensure content is unique
    test_run_id = str(uuid.uuid4())[:8]

    # --- 1. Health Check ---
    get_health_check()

    # --- 2. Synchronous Actions (Immediate Response) ---
    print_header("2. Testing Synchronous Actions (Likes, Tipping, Referrals)")
    sync_user = f"wallet_sync_{test_run_id}"
    test_synchronous_action({"creatorAddress": sync_user, "Interaction": {"interactionType": "like", "data": "post_id_abc"}}, "Single Like")
    test_synchronous_action({"creatorAddress": sync_user, "Interaction": {"interactionType": "tipping", "data": "Tipped 5 tokens"}}, "Single Tip")
    test_synchronous_action({"creatorAddress": sync_user, "Interaction": {"interactionType": "referral", "data": "referred_user_xyz"}}, "Single Referral")
    
    # --- 3. Daily Limit Tests ---
    print_header("3. Testing Daily Limits (Cooldowns)")
    
    # Test Like Limit (5 per day)
    limit_test_user = f"wallet_limiter_{test_run_id}"
    print("\n--- Testing Daily Like Limit (5 allowed per day) ---")
    for i in range(6):
        test_synchronous_action({"creatorAddress": limit_test_user, "Interaction": {"interactionType": "like", "data": f"post_id_{i}"}}, f"Like #{i+1}")
        time.sleep(0.2)
    print(">>> CHECK: The first 5 'like' calls should have a positive score. The 6th should have a score of 0.0.")
    
    # Test Comment Limit (5 per day)
    print("\n--- Testing Daily Comment Limit (5 allowed per day) ---")
    for i in range(6):
        test_asynchronous_action({"creatorAddress": limit_test_user, "Interaction": {"interactionType": "comment", "data": f"This is valid comment number {i+1}."}, "webhookUrl": WEBHOOK_URL}, test_name=f"Comment #{i+1}")
        time.sleep(0.2)
    print(f">>> CHECK WEBHOOK: The first 5 comments for user '{limit_test_user}' should be approved. The 6th should be rejected for 'Daily Limit Reached'.")

    # Test Post Limit (2 per day)
    print("\n--- Testing Daily Post Limit (2 allowed per day) ---")
    for i in range(3):
         test_asynchronous_action({"creatorAddress": limit_test_user, "Interaction": {"interactionType": "post", "data": f"A unique post #{i+1} about blockchains."}, "webhookUrl": WEBHOOK_URL}, test_name=f"Post #{i+1}")
         time.sleep(1) # Give a small delay between posts
    print(f">>> CHECK WEBHOOK: The first 2 posts for user '{limit_test_user}' should be approved. The 3rd should be rejected for 'Daily Limit Reached'.")

    # --- 4. Content Validation Tests ---
    print_header("4. Testing AI Content Validation")
    validator_user = f"wallet_validator_{test_run_id}"
    test_image_path = "test_post_image.png"
    if not os.path.exists(test_image_path):
        Image.new('RGB', (100, 80), color='magenta').save(test_image_path)
    
    # Gibberish Comment
    test_asynchronous_action({"creatorAddress": validator_user, "Interaction": {"interactionType": "comment", "data": "asdf qwer zxcv 1234 lkjh"}, "webhookUrl": WEBHOOK_URL}, test_name="Gibberish Comment")
    print(f">>> CHECK WEBHOOK: The 'Gibberish Comment' from '{validator_user}' should be REJECTED.")
    time.sleep(1)

    # Gibberish Post
    test_asynchronous_action({"creatorAddress": validator_user, "Interaction": {"interactionType": "post", "data": "qwerty yuiop asdfgh 11111"}, "webhookUrl": WEBHOOK_URL}, test_name="Gibberish Post")
    print(f">>> CHECK WEBHOOK: The 'Gibberish Post' from '{validator_user}' should be REJECTED.")
    time.sleep(1)

    # Duplicate Post Detection
    original_post_text = f"This is a truly original post about AI ethics - {test_run_id}"
    
    # First, submit the original post
    test_asynchronous_action({"creatorAddress": validator_user, "Interaction": {"interactionType": "post", "data": original_post_text}, "webhookUrl": WEBHOOK_URL}, image_path=test_image_path, test_name="Original Post")
    print(f">>> CHECK WEBHOOK: The 'Original Post' from '{validator_user}' should be APPROVED.")
    
    # Wait a bit to ensure the first post is likely processed and in the vector DB
    print("\n...Waiting 5 seconds for original post to be indexed before testing duplicate...")
    time.sleep(5)
    
    # Second, submit the exact same content from a different user
    duplicate_user = f"wallet_copycat_{test_run_id}"
    test_asynchronous_action({"creatorAddress": duplicate_user, "Interaction": {"interactionType": "post", "data": original_post_text}, "webhookUrl": WEBHOOK_URL}, image_path=test_image_path, test_name="Duplicate Post")
    print(f">>> CHECK WEBHOOK: The 'Duplicate Post' from '{duplicate_user}' should be REJECTED.")

    print_header("5. Standard Asynchronous Posts")
    final_user = f"wallet_final_{test_run_id}"
    
    # Test Text-only Post
    test_asynchronous_action({"creatorAddress": final_user, "Interaction": {"interactionType": "post", "data": f"A valid text-only post about decentralized finance {test_run_id}."}, "webhookUrl": WEBHOOK_URL}, test_name="Text-Only Post")
    print(f">>> CHECK WEBHOOK: The 'Text-Only Post' from '{final_user}' should be APPROVED.")

    print("\n\n--- ALL TESTS SENT ---")
    print("Please check your API and Celery worker console logs for processing details.")
    print(f"Final results for all asynchronous actions will appear at: {WEBHOOK_URL}")