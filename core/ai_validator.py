import weaviate
from transformers import pipeline
from PIL import Image
import base64
import uuid
import os
from typing import Optional
from collections import Counter # ADDED THE MISSING IMPORT
from weaviate.classes.config import Configure, Property, DataType
from collections import Counter # <-- ADD THIS LINE
# --- Gibberish Classifier Setup ---
# This setup is done once when the module is imported.
try:
    gibberish_classifier = pipeline("text-classification", model="unitary/toxic-bert")
    print("ContentValidator: Gibberish classifier 'unitary/toxic-bert' loaded.")
except Exception as e:
    print(f"ContentValidator: Could not load primary gibberish model, trying fallback. Error: {e}")
    try:
        gibberish_classifier = pipeline("text-classification", model="madhurjindal/autonlp-Gibberish-Detector-492513457")
        print("ContentValidator: Gibberish classifier 'madhurjindal' loaded.")
    except Exception as fallback_e:
        print(f"ContentValidator WARNING: Could not load any gibberish classifier model. Rule-based checks will still apply. Error: {fallback_e}")
        gibberish_classifier = None


class ContentValidator:
    def __init__(self):
        """Initializes the connection to Weaviate using environment variables."""
        db_host = os.getenv("WEAVIATE_HOST", "localhost")
        try:
            self.client = weaviate.connect_to_custom(
                http_host=db_host,
                http_port=int(os.getenv("WEAVIATE_PORT", 8080)),
                http_secure=False,
                grpc_host=db_host,
                grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", 50051)),
                grpc_secure=False
            )
            print(f"ContentValidator: Successfully connected to Weaviate at {db_host}.")
            self._setup_schema()
        except Exception as e:
            print(f"FATAL: ContentValidator could not connect to Weaviate. Details: {e}")
            raise

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

    def check_for_duplicates(self, text_content: str, image_path: Optional[str], threshold: float = 0.26) -> tuple[bool, float]:
        # --- FIX: Lowered the default threshold from 0.26 to 0.15 for stricter duplicate checking ---
        """Robustly checks for duplicates using the correct Weaviate vector search method."""
        print("--- Checking for duplicate content ---")
        try:
            posts_collection = self.client.collections.get("Post")


            response = posts_collection.query.near_text(
                query=text_content,
                limit=1,
                return_metadata=["distance"]
            )
            
            if not response.objects: return (False, 1.0)
            
            distance = response.objects[0].metadata.distance
            is_duplicate = distance < threshold
            
            print(f"Most similar post found with distance: {distance:.4f} (Threshold is < {threshold})")
            if is_duplicate: print("DUPLICATE DETECTED!")
                
            return (is_duplicate, distance)
        except Exception as e:
            print(f"ERROR during duplicate check: {e}")
            return (False, 1.0)

    def process_new_post(self, user_id: str, text_content: str, image_path: Optional[str]) -> tuple[str, float] | None:
        """Main validation pipeline. Returns (post_id, distance) on success."""
        print(f"\n--- Processing new post for user: {user_id} ---")
        if not text_content or self.is_gibberish(text_content):
            print("Post rejected: Content is empty or gibberish.")
            return None
        
        is_duplicate, distance = self.check_for_duplicates(text_content, image_path)
        if is_duplicate:
            print(f"Post rejected: Content is a duplicate.")
            return None
            
        print("Content is valid and original. Adding to Weaviate.")
        try:
            post_object = {"content": text_content, "user_id": user_id}
            if image_path:
                post_object["image"] = self._image_to_base64(image_path)
            
            posts_collection = self.client.collections.get("Post")
            post_uuid = uuid.uuid4()
            posts_collection.data.insert(properties=post_object, uuid=post_uuid)
            
            new_uuid_str = str(post_uuid)
            print(f"Successfully added post to Weaviate with UUID: {new_uuid_str}")
            return (new_uuid_str, distance)
            
        except Exception as e:
            print(f"Error adding post to Weaviate: {e}")
            return None

    def close(self):
        """Closes the connection to the Weaviate client."""
        print("Closing Weaviate connection...")
        if hasattr(self, 'client') and self.client:
            self.client.close()