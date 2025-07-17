import requests
import base64
import json
import time
import os
import re 
from typing import Optional

class OllamaQualityScorer:
    def __init__(self, host: Optional[str] = None):
        """
        Initializes the scorer with the Ollama server URL from environment variables.
        """
        # Use environment variable for host, with a default for local testing
        self.host = host or os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
        self.api_url = f"{self.host}/api/generate"
        self.model_name = "qwen2.5vl"
        print(f"OllamaQualityScorer: Initialized for model '{self.model_name}' at {self.host}")

    def _image_to_base64(self, image_path: str) -> str:
        """Helper function to convert an image file to a base64 string."""
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')

    def get_quality_score(self, text_content: str, image_path: Optional[str], max_retries: int = 3) -> int:
        """
        Gets a quality score from the local Ollama LLM.
        This version is robust, handles text-only posts, and has a better prompt.
        """
        print("--- Querying Ollama for content quality score ---")
        
        # --- 1. Prepare Prompt and Payload Conditionally ---
        if image_path:
            prompt_context = f"""Analyze the following post which includes text and an image.
Post Text: "{text_content}"
Image: [An image is provided]"""
        else:
            prompt_context = f"""Analyze the following text-only post.
Post Text: "{text_content}"
Image: [No image provided]"""

        prompt = f"""You are a Content Quality Analyst. Your task is to rate a post on a scale of 0 to 10 based on effort, creativity, and clarity.
{prompt_context}
Based on your analysis, provide a single integer score and nothing else. Your entire response must be only the number.
Score:"""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }
        
        if image_path:
            try:
                image_b64 = self._image_to_base64(image_path)
                payload["images"] = [image_b64]
            except Exception as e:
                print(f"ERROR: Failed to encode image at path {image_path}. Details: {e}")
                return 0

        # --- 2. Execute API Call with Retry Loop ---
        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1}/{max_retries} to contact Ollama...")
                response = requests.post(self.api_url, json=payload, timeout=120)
                response.raise_for_status()

                response_json = response.json()
                score_text = response_json.get('response', '0').strip()
                
                match = re.search(r'\d+', score_text)
                if match:
                    score = int(match.group(0))
                    print(f"Ollama response: '{score_text}', Extracted score: {score}")
                    return min(10, max(0, score))
                
                print(f"Warning: Could not parse a number from Ollama response: '{score_text}'")
                if attempt < max_retries - 1:
                    print("Retrying...")
                    time.sleep(2)
                else:
                    print("Could not parse a score after all retries.")
                    return 0

            except requests.exceptions.Timeout:
                print(f"ERROR: Request timed out on attempt {attempt + 1}")
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Request failed on attempt {attempt + 1}. Details: {e}")
            
            if attempt < max_retries - 1:
                print("Retrying after error...")
                time.sleep(3)
            else:
                print("All retry attempts to contact Ollama have failed.")
                return 0

        return 0