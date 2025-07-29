# run_all_test.py (Definitive, Final Version)

import requests
import json
import os
import time
import uuid
from PIL import Image

# --- Configuration ---
BASE_API_URL = os.getenv("API_URL", "http://localhost:8000")
HEALTH_URL = f"{BASE_API_URL}/health"
SYNC_API_URL = f"{BASE_API_URL}/v1/submit_action"
ASYNC_POST_URL = f"{BASE_API_URL}/v1/submit_post"

# IMPORTANT: Replace with your personal webhook URL to see async results
WEBHOOK_URL = "https://webhook.site/a43acabb-4f0c-48d9-b30d-8532e02c1870"  

# --- Helper Functions ---
def get_health_w():
    """Checks the API /health/weaviate endpoint."""
    print_header("2. Weaviate Health Check")
    try:
        response = requests.get(f"{BASE_API_URL}/health/weaviate", timeout=10)
        response.raise_for_status()
        print(f"--> [WEAVIATE HEALTH CHECK] GET {BASE_API_URL}/health/weaviate")
        print(f"<-- [API RESPONSE] Status: {response.status_code}, Body: {response.json()}")
        print("--- WEAVIATE HEALTH CHECK PASSED ---")
    except requests.RequestException as e:
        print(f"--- WEAVIATE HEALTH CHECK FAILED: Cannot connect to Weaviate. Details: {e} ---")
        exit()
def print_header(title):
    """Prints a formatted header to the console."""
    print(f"\n\n{'='*60}\n          {title.upper()}\n{'='*60}")

def get_random_interactor():
    """Generates a random wallet address for interaction targets."""
    return f"wallet_interactor_{uuid.uuid4().hex[:12]}"

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
    creator = payload.get("creatorAddress", "unknown")
    interactor = payload.get("interactorAddress", "unknown")
    print(f"\n--> [SYNC TEST: {test_name}] Sending '{interaction_type}' - Creator: '{creator}', Interactor: '{interactor}'")
    
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
    creator = payload.get("creatorAddress", "unknown")
    interactor = payload.get("interactorAddress", "unknown")
    
    # Determine the target URL based on the interaction type
    if interaction_type == "comment":
        print(f"\n--> [ASYNC TEST: {test_name}] Sending '{interaction_type}' - Creator: '{creator}', Interactor: '{interactor}'")
        target_url = SYNC_API_URL
        files = None
        json_data = payload
    elif interaction_type == "post":
        print(f"\n--> [ASYNC TEST: {test_name}] Sending '{interaction_type}' - Creator: '{creator}'")
        target_url = ASYNC_POST_URL
        files = {'request': (None, json.dumps(payload), 'application/json')}
        if image_path and os.path.exists(image_path):
            files['image'] = (os.path.basename(image_path), open(image_path, 'rb'), 'image/png')
            print(f"    Attaching image: {image_path}")
        else:
            print("    Sending post without an image.")
        json_data = None
    else:
        print(f"ERROR: Unknown asynchronous action type '{interaction_type}'")
        return

    try:
        response = requests.post(target_url, json=json_data, files=files, timeout=15)
        print(f"<-- [API RESPONSE] Status: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(f"Response Body: {response.text}")
    except requests.RequestException as e:
        print(f"An error occurred: {e}")
# --- Main Execution Block ---


# Updated test script with interactorAddress for ALL actions

if __name__ == "__main__":
    print(f"API tests starting. Asynchronous results will appear at: {WEBHOOK_URL}")
    
    # Generate a unique ID for this entire test run
    test_run_id = str(uuid.uuid4())[:8]

    # 1. Health Check
    get_health_check()

    # 2. Synchronous Actions - ALL need interactorAddress
    print_header("2. Testing Synchronous Actions (Likes, Tipping, Referrals)")
    sync_creator = f"creator_sync_{test_run_id}"
    sync_interactor = f"interactor_sync_{test_run_id}"  # This is the wallet getting rewards
    
    # For ALL actions, interactor gets the rewards
    test_synchronous_action({
        "creatorAddress": sync_creator, 
        "interactorAddress": sync_interactor, 
        "Interaction": {"interactionType": "like", "data": "post_id_abc"}
    }, "Single Like")
    
    test_synchronous_action({
        "creatorAddress": sync_creator, 
        "interactorAddress": sync_interactor, 
        "Interaction": {"interactionType": "tipping", "data": "Tipped 5 tokens"}
    }, "Single Tip")
    
    # For referrals, interactor is the one who made the referral and gets the bonus
    test_synchronous_action({
        "creatorAddress": sync_creator, 
        "interactorAddress": sync_interactor,  # FIX: Add interactorAddress for referrals
        "Interaction": {"interactionType": "referral", "data": "referred_user_xyz"}
    }, "Single Referral")
    
    # 3. Daily Limit Tests - Use consistent interactor for limits
    print_header("3. Testing Daily Limits (Cooldowns)")
    limit_creator = f"creator_limiter_{test_run_id}"
    limit_interactor = f"interactor_limiter_{test_run_id}"  # Same wallet for all limits
    
    print("\n--- Testing Daily Like Limit (5 allowed per day) ---")
    for i in range(6):
        test_synchronous_action({
            "creatorAddress": limit_creator, 
            "interactorAddress": limit_interactor, 
            "Interaction": {"interactionType": "like", "data": f"post_id_{i}"}
        }, f"Like #{i+1}")
        time.sleep(0.2)
    
    print("\n--- Testing Daily Comment Limit (5 allowed per day) ---")
    for i in range(6):
        test_asynchronous_action({
            "creatorAddress": limit_creator, 
            "interactorAddress": limit_interactor, 
            "Interaction": {"interactionType": "comment", "data": f"Valid comment number {i+1} for test run {test_run_id}."}, 
            "webhookUrl": WEBHOOK_URL
        }, test_name=f"Comment #{i+1}")
        time.sleep(0.2)

    print("\n--- Testing Daily Post Limit (2 allowed per day) ---")
    for i in range(3):
        post_text = f"Unique post #{i+1} about blockchain technology for test run {test_run_id}."
        test_asynchronous_action({
            "creatorAddress": limit_creator, 
            "interactorAddress": limit_interactor,  # FIX: Add interactorAddress for posts
            "Interaction": {"interactionType": "post", "data": post_text}, 
            "webhookUrl": WEBHOOK_URL
        }, test_name=f"Post #{i+1}")
        time.sleep(1)

    # 4. Content Validation Tests - ALL need interactorAddress
    print_header("4. Testing AI Content Validation")
    validator_creator = f"creator_validator_{test_run_id}"
    validator_interactor = f"interactor_validator_{test_run_id}"
    
    test_image_path = "test_post_image.png"
    if not os.path.exists(test_image_path):
        Image.new('RGB', (100, 80), color='magenta').save(test_image_path)
    
    test_asynchronous_action({
        "creatorAddress": validator_creator, 
        "interactorAddress": validator_interactor, 
        "Interaction": {"interactionType": "comment", "data": "asdf qwer zxcv 1234 lkjh"}, 
        "webhookUrl": WEBHOOK_URL
    }, test_name="Gibberish Comment")
    time.sleep(1)

    test_asynchronous_action({
        "creatorAddress": validator_creator, 
        "interactorAddress": validator_interactor, 
        "Interaction": {"interactionType": "post", "data": "qwerty yuiop asdfgh 11111"}, 
        "webhookUrl": WEBHOOK_URL
    }, test_name="Gibberish Post")
    time.sleep(1)

    # Use the unique run ID to ensure this content is never a duplicate
    original_post_text = f"This is a truly original post about AI ethics for test run {test_run_id}"
    
    test_asynchronous_action({
        "creatorAddress": validator_creator, 
        "interactorAddress": validator_interactor, 
        "Interaction": {"interactionType": "post", "data": original_post_text}, 
        "webhookUrl": WEBHOOK_URL
    }, image_path=test_image_path, test_name="Original Post")
    
    print("\n...Waiting 5 seconds for original post to be indexed before testing duplicate...")
    time.sleep(5)
    
    duplicate_creator = f"creator_copycat_{test_run_id}"
    duplicate_interactor = f"interactor_copycat_{test_run_id}"  # Different interactor
    test_asynchronous_action({
        "creatorAddress": duplicate_creator, 
        "interactorAddress": duplicate_interactor, 
        "Interaction": {"interactionType": "post", "data": original_post_text}, 
        "webhookUrl": WEBHOOK_URL
    }, image_path=test_image_path, test_name="Duplicate Post")

    # 5. Standard Asynchronous Posts - ALL need interactorAddress
    print_header("5. Standard Asynchronous Posts")
    final_creator = f"creator_final_{test_run_id}"
    final_interactor = f"interactor_final_{test_run_id}"
    
    # Test a unique text-only post
    text_post_content = f"A valid text-only post about decentralized finance for test run {test_run_id}."
    test_asynchronous_action({
        "creatorAddress": final_creator, 
        "interactorAddress": final_interactor, 
        "Interaction": {"interactionType": "post", "data": text_post_content}, 
        "webhookUrl": WEBHOOK_URL
    }, test_name="Text-Only Post")
    
    # Test a unique post with an image
    image_post_content = f"A valid post with a new image about layer-2 solutions for test run {test_run_id}."
    test_asynchronous_action({
        "creatorAddress": final_creator, 
        "interactorAddress": final_interactor, 
        "Interaction": {"interactionType": "post", "data": image_post_content}, 
        "webhookUrl": WEBHOOK_URL
    }, image_path=test_image_path, test_name="Image Post")

    print("\n\n--- ALL TESTS SENT ---")
    print("Please check your API and Celery worker console logs for processing details.")
    print(f"Final results for all asynchronous actions will appear at: {WEBHOOK_URL}")