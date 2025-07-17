
import requests
import json
import os
from PIL import Image


API_URL = "http://localhost:8000/v1/process_interaction"
# IMAGE_PATH = ""
WEBHOOK_URL = "https://webhook.site/fb737657-2e62-4aac-bff5-bfaffe897fd7" 


json_payload = {
  "creatorAddress": "wallet_0xabc_testuser",
  "Interaction": {
    "interactionType": "like",
    "data": "post_id_12345"
  },
  "webhookUrl": WEBHOOK_URL
}

def send_test_post():
    """Constructs and sends a correct multipart/form-data request."""

    # if not os.path.exists(IMAGE_PATH):
    #     Image.new('RGB', (100, 80), color='purple').save(IMAGE_PATH)

    files = {
        'request': (None, json.dumps(json_payload), 'application/json'),
        # 'image': (os.path.basename(IMAGE_PATH), open(IMAGE_PATH, 'rb'), 'image/png')
    }

    try:
        print("Sending correctly formatted request to API...")
        response = requests.post(API_URL, files=files, timeout=10)
        
        print(f"\n--- API Response ---")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.json()}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    print(f"--> Please go to your webhook catcher at {WEBHOOK_URL} to see the final AIResponse.")
    send_test_post()