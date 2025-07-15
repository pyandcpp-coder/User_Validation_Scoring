import requests

# The URL of our running Flask API server
API_URL = "http://localhost:8020/validate_post"

def submit_post(user_id, text, image_path):
    """Sends a post to the validation API and prints the response."""
    print(f"\n--- Submitting post for user: {user_id} ---")
    
    try:
        with open(image_path, 'rb') as img:
            # We send as 'multipart/form-data'
            files = {'image': (image_path, img, 'image/png')}
            data = {'user_id': user_id, 'text_content': text}
            
            response = requests.post(API_URL, files=files, data=data, timeout=20)
            
            # Print the result
            print(f"Status Code: {response.status_code}")
            print(f"Response JSON: {response.json()}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Test 1: A valid, original post
    submit_post(
        user_id="user-api-001",
        text="This is a brand new post about a sunset, submitted via the API.",
        image_path="test_image.png" # Make sure you have this file
    )

    # Test 2: Submitting the exact same post again (should be rejected)
    submit_post(
        user_id="user-api-002",
        text="This is a brand new post about a sunset, submitted via the API.",
        image_path="test_image.png"
    )

    # Test 3: A gibberish post (should be rejected)
    submit_post(
        user_id="user-api-003",
        text="asdfhkj qweorui kjhsdf",
        image_path="test_image.png"
    )
    submit_post(
        user_id="user-api-010",
        text="This is a valid post with an image,, also my name is yash tiwari",
        image_path="ok.png"  
    )