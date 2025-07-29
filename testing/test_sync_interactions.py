import requests
import json
import os
from PIL import Image
import time


BASE_API_URL = os.getenv("API_URL", "http://localhost:8000")
SYNC_API_URL = f"{BASE_API_URL}/v1/submit_action"
ASYNC_POST_URL = f"{BASE_API_URL}/v1/submit_post"

WEBHOOK_URL = "https://webhook.site/fb737657-2e62-4aac-bff5-bfaffe897fd7" 


def print_header(title):
    """Prints a formatted header to the console."""
    print(f"\n{'='*25}")
    print(f"  {title.upper()}")
    print(f"{'='*25}")

def test_synchronous_action(payload: dict):
    """A helper to send a simple JSON interaction to the /submit_action endpoint."""
    interaction_type = payload.get("Interaction", {}).get("interactionType", "unknown")
    user = payload.get("creatorAddress", "unknown")
    print(f"\n--> [SYNC TEST] Sending '{interaction_type}' for {user}")
    
    try:
        response = requests.post(SYNC_API_URL, json=payload, timeout=15)
        print(f"<-- [API RESPONSE] Status Code: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(f"Error: Response was not valid JSON. Body: {response.text}")
            
    except requests.RequestException as e:
        print(f"An error occurred: {e}")

def test_asynchronous_post(json_payload: dict, image_path: str = None):
    """A helper to send a multipart/form-data post to the /submit_post endpoint."""
    user = json_payload.get("creatorAddress", "unknown")
    print(f"\n--> [ASYNC TEST] Sending 'post' for {user}")
    
    files = {'request': (None, json.dumps(json_payload), 'application/json')}
    
    if image_path and os.path.exists(image_path):
        files['image'] = (os.path.basename(image_path), open(image_path, 'rb'), 'image/png')
        print(f"    Attaching image: {image_path}")
    else:
        print("    Sending post without an image.")

    try:
        response = requests.post(ASYNC_POST_URL, files=files, timeout=15)
        print(f"<-- [API RESPONSE] Status Code: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(f"Error: Response was not valid JSON. Body: {response.text}")

    except requests.RequestException as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    print(f"API tests starting.")
    print(f"IMPORTANT: Final 'post' results will be sent to your webhook URL.")
    print(f"Go to {WEBHOOK_URL} to see them arrive.")
    
    print_header("Testing Synchronous Actions")
    sync_user = "wallet_sync_tester_005"
    

    test_synchronous_action({
      "creatorAddress": sync_user,
      "Interaction": {"interactionType": "like", "data": "post_id_abc"},
      "webhookUrl": "N/A" 
    })
    
    test_synchronous_action({
      "creatorAddress": sync_user,
      "Interaction": {"interactionType": "comment", "data": "This is a great comment!"},
      "webhookUrl": "N/A"
    })
    
    test_synchronous_action({
      "creatorAddress": sync_user,
      "Interaction": {"interactionType": "tipping", "data": "Tipped 5 tokens"},
      "webhookUrl": "N/A"
    })

    print_header("Testing Asynchronous Posts")
    
    # A high-quality post with an image
    post_user_1 = "wallet_post_tester_001"
    test_image_path = "test_post_image.png"
    if not os.path.exists(test_image_path):
        Image.new('RGB', (100, 80), color='teal').save(test_image_path)
    
    test_asynchronous_post({
      "creatorAddress": post_user_1,
      "interactorAddress": "wallet_interactor_tester_001",
      "Interaction": {
        "interactionType": "post",
        "data": "This is a thoughtful and well-written post about the future of decentralized social media, accompanied by a relevant image."
      },
      "webhookUrl": WEBHOOK_URL
    }, image_path=test_image_path)
    
    time.sleep(1) # Small delay between requests to not overload the server

    # A text-only post
    post_user_2 = "wallet_post_tester_002"
    test_asynchronous_post({
      "creatorAddress": post_user_2,
      "interactorAddress": "wallet_interactor_tester_002",
      "Interaction": {
        "interactionType": "post",
        "data": "Just wanted to say hello to this amazing community!"
      },
      "webhookUrl": WEBHOOK_URL
    }, image_path=None)
    
    time.sleep(1)

    # --- Test Case 3: Duplicate Post Submission ---
    print_header("Testing Duplicate Detection")
    # We submit the first post again. It should be rejected.
    test_asynchronous_post({
      "creatorAddress": "another_user_trying_to_copy",
      "Interaction": {
        "interactionType": "post",
        "data": "This is a thoughtful and well-written post about the future of decentralized social media, accompanied by a relevant image."
      },
      "webhookUrl": WEBHOOK_URL
    }, image_path=test_image_path)

    print("\n--- All tests sent. Check your webhook and Celery logs for results. ---")