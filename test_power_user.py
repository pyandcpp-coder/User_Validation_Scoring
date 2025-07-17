import requests
import json
import time

SYNC_API_URL = "http://localhost:8000/v1/submit_action"

def print_header(title):
    print(f"\n{'='*25}\n  {title.upper()}\n{'='*25}")

def send_interaction(payload: dict):
    interaction_type = payload.get("Interaction", {}).get("interactionType", "unknown")
    try:
        response = requests.post(SYNC_API_URL, json=payload, timeout=15)
        print(f"-> Sent '{interaction_type}'. Status: {response.status_code}. Response: {response.json().get('validation', {}).get('reason')}")
    except Exception as e:
        print(f"-> Sent '{interaction_type}'. FAILED: {e}")

if __name__ == "__main__":
    user = "power_user_001"
    
    print_header(f"Simulating Power User: {user}")

    # --- Build Payloads ---
    like_payload = {
      "creatorAddress": user,
      "Interaction": {"interactionType": "like", "data": "post_id_xyz"},
      "webhookUrl": "N/A" 
    }
    comment_payload = {
      "creatorAddress": user,
      "Interaction": {"interactionType": "comment", "data": "This is a power user comment!"},
      "webhookUrl": "N/A"
    }

    # --- Simulate Hitting Daily Limits ---
    
    print("\n--- Testing LIKE limit (Daily Max = 5) ---")
    for i in range(7): # Try to send 7 likes
        print(f"Attempting like #{i + 1}...")
        send_interaction(like_payload)
        time.sleep(0.1) # Small delay

    print("\n--- Testing COMMENT limit (Daily Max = 5) ---")
    for i in range(7): # Try to send 7 comments
        print(f"Attempting comment #{i + 1}...")
        send_interaction(comment_payload)
        time.sleep(0.1)

    print("\n--- Simulation Complete ---")
    print("Check the server logs to see the 'Cooldown active' messages and timestamps.")