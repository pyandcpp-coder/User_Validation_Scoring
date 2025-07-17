# run_all_tests.py (Definitive, Corrected Version)

import requests
import json
import os
from PIL import Image
import time

# --- Configuration ---
BASE_API_URL = os.getenv("API_URL", "http://localhost:8000")
SYNC_API_URL = f"{BASE_API_URL}/v1/submit_action"
ASYNC_POST_URL = f"{BASE_API_URL}/v1/submit_post"

WEBHOOK_URL = "https://webhook.site/fb737657-2e62-4aac-bff5-bfaffe897fd7"  

# --- Helper Functions ---

def print_header(title):
    print(f"\n{'='*25}\n  {title.upper()}\n{'='*25}")

def test_synchronous_action(payload: dict):
    """Sends a raw JSON payload to the synchronous action endpoint."""
    interaction_type = payload.get("Interaction", {}).get("interactionType", "unknown")
    user = payload.get("creatorAddress", "unknown")
    print(f"\n--> [SYNC TEST] Sending '{interaction_type}' for {user}")
    
    try:
        response = requests.post(SYNC_API_URL, json=payload, timeout=15)
        print(f"<-- [API RESPONSE] Status: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(f"Response Body: {response.text}")
    except requests.RequestException as e:
        print(f"An error occurred: {e}")

def test_asynchronous_post(json_payload: dict, image_path: str = None):
    """Sends a multipart/form-data payload to the asynchronous post endpoint."""
    user = json_payload.get("creatorAddress", "unknown")
    print(f"\n--> [ASYNC POST TEST] Sending 'post' for {user}")
    
    files = {'request': (None, json.dumps(json_payload), 'application/json')}
    if image_path and os.path.exists(image_path):
        files['image'] = (os.path.basename(image_path), open(image_path, 'rb'), 'image/png')
        print(f"    Attaching image: {image_path}")
    else:
        print("    Sending post without an image.")

    try:
        response = requests.post(ASYNC_POST_URL, files=files, timeout=15)
        print(f"<-- [API RESPONSE] Status: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(f"Response Body: {response.text}")
    except requests.RequestException as e:
        print(f"An error occurred: {e}")

# --- Main Execution Block ---

if __name__ == "__main__":
    print(f"API tests starting. Async results will appear at {WEBHOOK_URL}")
    
    # --- Test 1: Synchronous Actions (Likes, Tipping) ---
    print_header("Testing Synchronous Actions")
    sync_user = "wallet_sync_tester_010"
    test_synchronous_action({
      "creatorAddress": sync_user,
      "Interaction": {"interactionType": "like", "data": "post_id_abc"},
      "webhookUrl": "N/A"
    })
    test_synchronous_action({
      "creatorAddress": sync_user,
      "Interaction": {"interactionType": "tipping", "data": "Tipped 5 tokens"},
      "webhookUrl": "N/A"
    })

    # --- Test 2: Asynchronous Comment Validation ---
    # **FIXED:** Comments are sent to /v1/submit_action to be queued asynchronously.
    print_header("Testing Asynchronous Comment Validation")
    comment_user = "wallet_comment_tester_005"
    
    # A valid comment - CORRECTED to use test_synchronous_action
    test_synchronous_action({
        "creatorAddress": comment_user,
        "Interaction": {"interactionType": "comment", "data": "This is a thoughtful and valid comment."},
        "webhookUrl": WEBHOOK_URL
    })

    time.sleep(1)
    
    # A gibberish comment - CORRECTED to use test_synchronous_action
    test_synchronous_action({
        "creatorAddress": comment_user,
        "Interaction": {"interactionType": "comment", "data": "asdf qwer zxcv 1234"},
        "webhookUrl": WEBHOOK_URL
    })
    
    # --- Test 3: Asynchronous Post Submissions ---
    print_header("Testing Asynchronous Posts")
    post_user_1 = "wallet_post_tester_011"
    test_image_path = "test_post_image.png"
    if not os.path.exists(test_image_path):
        Image.new('RGB', (100, 80), color='cyan').save(test_image_path)
    
    test_asynchronous_post({
        "creatorAddress": post_user_1,
        "Interaction": {"interactionType": "post", "data": "A new perspective on layer-2 scaling solutions."},
        "webhookUrl": WEBHOOK_URL
    }, image_path=test_image_path)
    
    # --- Test 4: Duplicate Post Submission ---
    print_header("Testing Duplicate Detection")
    test_asynchronous_post({
        "creatorAddress": "copycat_user_012",
        "Interaction": {"interactionType": "post", "data": "A new perspective on layer-2 scaling solutions."},
        "webhookUrl": WEBHOOK_URL
    }, image_path=test_image_path)

    print("\n--- All tests sent. Check API, Celery, and webhook for results. ---")