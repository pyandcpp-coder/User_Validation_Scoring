import weaviate
import torch
from transformers import pipeline
from PIL import Image
import base64
import uuid
import re
import string
from collections import Counter
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.data import DataObject
from core.ollama_scorer import OllamaQualityScorer
import weaviate
from transformers import pipeline
from PIL import Image
import base64
import uuid
from typing import Optional # MOVED to top of file
from weaviate.classes.config import Configure, Property, DataType
try:
    gibberish_classifier = pipeline(
        "text-classification", 
        model="unitary/toxic-bert"
    )
    print("Using unitary/toxic-bert model")
except:
    try:
        gibberish_classifier = pipeline(
            "text-classification", 
            model="madhurjindal/autonlp-Gibberish-Detector-492513457"
        )
        print("Using madhurjindal gibberish detector")
    except:
        print("Warning: Could not load gibberish classifier, using rule-based detection only")
        gibberish_classifier = None

class ContentValidator:
    def __init__(self):
        """
        Initializes the connection to Weaviate and sets up the database schema.
        """
        try:
            self.client = weaviate.connect_to_custom(
                http_host="localhost",
                http_port=8080,
                http_secure=False,       # HTTP not HTTPS
                grpc_host="localhost",
                grpc_port=50051,
                grpc_secure=False        # gRPC insecure
            )

            print("Successfully connected to Weaviate.")
        except Exception as e:
            print(f"Error connecting to Weaviate: {e}")
            raise

        self._setup_schema()

    def _setup_schema(self):
        """
        Defines and creates the 'Post' collection in Weaviate if it doesn't exist.
        This schema is configured to use the multimodal CLIP vectorizer.
        """
        try:
            if self.client.collections.exists("Post"):
                print("'Post' collection already exists.")
                return
            
            print("Creating 'Post' collection in Weaviate...")

            self.client.collections.create(
                name="Post",
                description="A user post with text and an image.",
                vectorizer_config=Configure.Vectorizer.multi2vec_clip(
                    image_fields=["image"],
                    text_fields=["content"]
                ),
                properties=[
                    Property(
                        name="content",
                        data_type=DataType.TEXT,
                        description="The text content of the post."
                    ),
                    Property(
                        name="image",
                        data_type=DataType.BLOB,
                        description="The image content of the post (base64 encoded)."
                    ),
                    Property(
                        name="user_id",
                        data_type=DataType.TEXT,
                        description="The ID of the user who made the post."
                    )
                ]
            )
            
            print("Collection created successfully.")
            
        except Exception as e:
            print(f"Error setting up schema: {e}")
            raise

    def is_gibberish(self, text: str) -> bool:
        """
        Comprehensive gibberish detection using multiple methods.
        Returns True if gibberish, False otherwise.
        """
        cleaned_text = text.strip().lower()
        
        # Rule-based checks
        if self._rule_based_gibberish_check(cleaned_text):
            print(f"Gibberish detected by rule-based analysis")
            return True
        
        # Statistical checks
        if self._statistical_gibberish_check(cleaned_text):
            print(f"Gibberish detected by statistical analysis")
            return True
        
        # ML model check (if available)
        if gibberish_classifier:
            if self._ml_gibberish_check(text):
                print(f"Gibberish detected by ML model")
                return True
        
        print("Text appears to be clean.")
        return False
    
    def _rule_based_gibberish_check(self, text: str) -> bool:
        """Rule-based gibberish detection"""
        # Check for minimum length
        if len(text.strip()) < 3:
            return True
        
        # Check for excessive repeating characters
        if len(set(text.replace(' ', ''))) < 3:
            return True
        
        # Check for keyboard patterns
        keyboard_patterns = [
            'qwerty', 'asdf', 'zxcv', 'qazwsx', 'wsxedc', 'rfvtgb', 'yhnujm',
            'abcdef', '123456', 'aaaaaa', 'xxxxxx', 'zzzzz'
        ]
        
        for pattern in keyboard_patterns:
            if pattern in text or pattern[::-1] in text:
                return True
        
        # Check for excessive consonants or vowels
        vowels = 'aeiou'
        consonants = 'bcdfghjklmnpqrstvwxyz'
        
        vowel_count = sum(1 for char in text if char in vowels)
        consonant_count = sum(1 for char in text if char in consonants)
        total_letters = vowel_count + consonant_count
        
        if total_letters > 0:
            vowel_ratio = vowel_count / total_letters
            consonant_ratio = consonant_count / total_letters
            
            # Flag if too many consonants or too few vowels
            if consonant_ratio > 0.8 or vowel_ratio < 0.1:
                return True
        
        return False
    
    def _statistical_gibberish_check(self, text: str) -> bool:
        """Statistical analysis for gibberish detection"""
        words = text.split()
        
        # Check average word length
        if words:
            avg_word_length = sum(len(word) for word in words) / len(words)
            if avg_word_length > 10 or avg_word_length < 2:
                return True
        
        # Check for words with no vowels (except common ones like "by", "my")
        common_no_vowel_words = {'by', 'my', 'gym', 'fly', 'try', 'cry', 'dry', 'fry', 'shy', 'spy', 'why'}
        
        for word in words:
            if len(word) > 3 and word not in common_no_vowel_words:
                if not any(vowel in word for vowel in 'aeiou'):
                    return True
        
        # Check character frequency distribution
        char_freq = Counter(char for char in text if char.isalpha())
        if char_freq:
            # Check if any character appears more than 40% of the time
            total_chars = sum(char_freq.values())
            max_freq = max(char_freq.values())
            if max_freq / total_chars > 0.4:
                return True
        
        return False
    
    def _ml_gibberish_check(self, text: str) -> bool:
        """ML model-based gibberish detection"""
        try:
            results = gibberish_classifier(text)
            
            # Handle different model outputs
            if isinstance(results, list) and len(results) > 0:
                result = results[0]
                
                # For the madhurjindal model, LABEL_0 means gibberish
                if 'madhurjindal' in str(gibberish_classifier.model.config._name_or_path):
                    if result['label'] == 'LABEL_0' and result['score'] > 0.7:
                        return True
                
                # For toxic-bert, we look for non-toxic (clean) text
                elif 'toxic-bert' in str(gibberish_classifier.model.config._name_or_path):
                    if result['label'] == 'TOXIC' and result['score'] > 0.8:
                        return True
                elif result['score'] > 0.8:
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error in ML gibberish detection: {e}")
            return False

    def _image_to_base64(self, image_path: str) -> str:
        """Helper function to convert an image file to a base64 string."""
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')

    def check_for_duplicates(self, text_content: str, image_path: str, threshold: float = 0.26) -> dict | None:
        """
        Checks for duplicate or very similar content in Weaviate before insertion.
        
        Args:
            text_content: The text of the new post.
            image_path: The path to the new post's image.
            threshold: The distance threshold to consider an item a duplicate. 
                       Lower values mean more similar (0 = identical, 1 = completely different).

        Returns:
            A dictionary with info about the duplicate if found, otherwise None.
        """
        print("--- Checking for duplicate content ---")
        try:
            image_b64 = self._image_to_base64(image_path)
            posts_collection = self.client.collections.get("Post")

            # Use near_text for similarity search
            response = posts_collection.query.near_text(
                query=text_content,
                limit=3,
                return_metadata=["distance"]
            )
            if not response.objects:
                return (False, 1.0) # No duplicates, and maximum possible distance

            most_similar_post = response.objects[0]
            similarity_distance = most_similar_post.metadata.distance

            if similarity_distance < threshold:
                print(f"DUPLICATE DETECTED! Distance: {similarity_distance:.4f}")
                return (True, similarity_distance) # It's a duplicate
            
            print(f"Post appears original. Distance: {similarity_distance:.4f}")
            return (False, similarity_distance) # Not a duplicate
        except Exception as e:
            print(f"Error during duplicate check: {e}")
            

    from typing import Optional 

    def process_new_post(self, user_id: str, text_content: str, image_path: Optional[str]) -> tuple[str, float] | None:
        """
        Main pipeline function for processing and validating a new post.
        Handles both text-only and text-with-image posts.
        """
        print(f"\n--- Processing new post for user: {user_id} ---")
        
        # 1. Gibberish Check
        if not text_content or self.is_gibberish(text_content):
            print("Post rejected: Content is empty or gibberish.")
            return None
        
        # 2. Duplicate Check
        is_duplicate, distance = self.check_for_duplicates(text_content, image_path)
        if is_duplicate:
            print(f"Post rejected: Content is a duplicate (distance: {distance:.4f}).")
            return None
            
        # 3. If all checks pass, add to Database
        print("Content is valid and original. Adding to Weaviate.")
        try:
            # Define the base object
            post_object = {
                "content": text_content,
                "user_id": user_id
            }
            # Conditionally add the image if it exists
            if image_path:
                image_b64 = self._image_to_base64(image_path)
                post_object["image"] = image_b64

            posts_collection = self.client.collections.get("Post")
            
            # CORRECTED: Define post_uuid before using it
            post_uuid = uuid.uuid4() 
            
            posts_collection.data.insert(
                properties=post_object,
                uuid=post_uuid
            )
            
            new_uuid_str = str(post_uuid)
            print(f"Successfully added post to Weaviate with UUID: {new_uuid_str}")
            
            # Return the new UUID and the calculated originality distance
            return (new_uuid_str, distance)
            
        except Exception as e:
            print(f"Error adding post to Weaviate: {e}")
            return None

    def close(self):
        """Closes the connection to the Weaviate client."""
        print("Closing Weaviate connection...")
        if hasattr(self, 'client'):
            self.client.close()
if __name__ == '__main__':
    validator = ContentValidator()
    print("Content Validator initialized successfully.")
    
    validator.close()