# import requests
# import base64
# import json

# class OllamaQualityScorer:
#     def __init__(self, host: str = "http://localhost:11434"):
#         """
#         Initializes the scorer with the Ollama server URL.
#         """
#         self.api_url = f"{host}/api/generate"
#         self.model_name = "qwen2.5vl" 
#         print(f"Ollama Quality Scorer initialized for model '{self.model_name}' at {host}")

#     def _image_to_base64(self, image_path: str) -> str:
#         """Helper function to convert an image file to a base64 string."""
#         with open(image_path, "rb") as img_file:
#             return base64.b64encode(img_file.read()).decode('utf-8')

#     def get_quality_score(self, text_content: str, image_path: str) -> int:
#         """
#         Gets a quality score from the local Ollama multimodal LLM using an improved prompt.
#         """
#         print("--- Querying Ollama for content quality score ---")
#         image_b64 = self._image_to_base64(image_path)
        
#         # IMPROVED PROMPT (One-Shot Prompting)
#         prompt = f"""
#         You are a meticulous Content Quality Analyst. Your task is to rate a user's post on a scale of 0 to 10 based on effort, creativity, and text-image relevance. You MUST respond with only a single number and nothing else.

#         Here is an example:
#         Post Text: "my vacation"
#         Image: [An image of a beach]
#         Your Response: 2

#         Now, analyze the following post:
#         Post Text: "{text_content}"
#         Image: [An image is provided]
#         Your Response:
#         """

#         payload = {
#             "model": self.model_name,
#             "prompt": prompt,
#             "stream": False,
#             "images": [image_b64]
#         }

#         try:
#             response = requests.post(self.api_url, json=payload, timeout=60) # Increased timeout for LLMs
#             response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

#             response_json = response.json()
#             score_text = response_json.get('response', '0').strip()
#             import re
#             match = re.search(r'\d+', score_text)
#             if match:
#                 score = int(match.group(0))
#                 print(f"Ollama response: '{score_text}', Extracted score: {score}")
#                 return min(10, max(0, score)) 
#             else:
#                 print(f"Warning: Could not parse a number from Ollama response: '{score_text}'")
#                 return 0

#         except requests.exceptions.RequestException as e:
#             print(f"ERROR: Could not connect to Ollama server at {self.api_url}. Is it running?")
#             print(e)
#             return 0
#         except json.JSONDecodeError:
#             print(f"ERROR: Failed to decode JSON response from Ollama.")
#             return 0

import requests
import base64
import json
import time
from typing import Optional

class OllamaQualityScorer:
    def __init__(self, host: str = "http://localhost:11434"):
        """
        Initializes the scorer with the Ollama server URL.
        """
        self.api_url = f"{host}/api/generate"
        self.model_name = "qwen2.5vl" 
        self.host = host
        print(f"Ollama Quality Scorer initialized for model '{self.model_name}' at {host}")

    def _image_to_base64(self, image_path: str) -> str:
        """Helper function to convert an image file to a base64 string."""
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')

    def _check_ollama_health(self) -> bool:
        """Check if Ollama server is running and accessible."""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=10)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def _ensure_model_loaded(self) -> bool:
        """Ensure the model is loaded by making a simple request."""
        try:
            payload = {
                "model": self.model_name,
                "prompt": "test",
                "stream": False
            }
            response = requests.post(self.api_url, json=payload, timeout=30)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def get_quality_score(self, text_content: str, image_path: str, max_retries: int = 3) -> int:
        """
        Gets a quality score from the local Ollama multimodal LLM with improved error handling.
        """
        print("--- Querying Ollama for content quality score ---")
        
        # Health check
        if not self._check_ollama_health():
            print("ERROR: Ollama server is not accessible. Please check if it's running.")
            return 0

        # Ensure model is loaded
        print("Ensuring model is loaded...")
        if not self._ensure_model_loaded():
            print("WARNING: Model may not be loaded properly")

        try:
            image_b64 = self._image_to_base64(image_path)
        except Exception as e:
            print(f"ERROR: Failed to encode image: {e}")
            return 0
        
        # IMPROVED PROMPT (One-Shot Prompting)
        prompt = f"""
        You are a meticulous Content Quality Analyst. Your task is to rate a user's post on a scale of 0 to 10 based on effort, creativity, and text-image relevance. You MUST respond with only a single number and nothing else.

        Here is an example:
        Post Text: "my vacation"
        Image: [An image of a beach]
        Your Response: 2

        Now, analyze the following post:
        Post Text: "{text_content}"
        Image: [An image is provided]
        Your Response:
        """

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "images": [image_b64]
        }

        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1}/{max_retries}")
                
                # Longer timeout for vision models
                response = requests.post(self.api_url, json=payload, timeout=120)
                response.raise_for_status()

                response_json = response.json()
                score_text = response_json.get('response', '0').strip()
                
                # Extract number from response
                import re
                match = re.search(r'\d+', score_text)
                if match:
                    score = int(match.group(0))
                    print(f"Ollama response: '{score_text}', Extracted score: {score}")
                    return min(10, max(0, score))
                else:
                    print(f"Warning: Could not parse a number from Ollama response: '{score_text}'")
                    if attempt < max_retries - 1:
                        print("Retrying...")
                        time.sleep(2)
                        continue
                    return 0

            except requests.exceptions.Timeout:
                print(f"ERROR: Request timed out (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    print("Retrying with longer timeout...")
                    time.sleep(5)
                    continue
                else:
                    print("All retry attempts exhausted")
                    return 0
                    
            except requests.exceptions.ConnectionError:
                print(f"ERROR: Connection error (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    print("Retrying...")
                    time.sleep(3)
                    continue
                else:
                    print("Could not establish connection to Ollama server")
                    return 0
                    
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    print("Retrying...")
                    time.sleep(2)
                    continue
                else:
                    return 0
                    
            except json.JSONDecodeError:
                print(f"ERROR: Failed to decode JSON response from Ollama (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    print("Retrying...")
                    time.sleep(2)
                    continue
                else:
                    return 0

        return 0  # Fallback if all retries fail

    def test_connection(self) -> dict:
        """Test connection and return diagnostic information."""
        diagnostics = {}
        
        # Test server health
        diagnostics['server_accessible'] = self._check_ollama_health()
        
        # Test model availability
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=10)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]
                diagnostics['available_models'] = model_names
                diagnostics['target_model_available'] = any(self.model_name in name for name in model_names)
            else:
                diagnostics['available_models'] = []
                diagnostics['target_model_available'] = False
        except Exception as e:
            diagnostics['model_check_error'] = str(e)
            diagnostics['available_models'] = []
            diagnostics['target_model_available'] = False
        
        return diagnostics