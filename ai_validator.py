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
                
                # Generic handling for other models
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

    def check_for_duplicates(self, text_content: str, image_path: str, threshold: float = 0.3) -> dict | None:
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
            text_response = posts_collection.query.near_text(
                query=text_content,
                limit=3,
                return_metadata=["distance"]
            )
            
            if not text_response.objects:
                print("No similar posts found in the database.")
                return None 

            most_similar_post = text_response.objects[0]
            similarity_distance = most_similar_post.metadata.distance
            similarity_percentage = (1 - similarity_distance) * 100
            
            print(f"Most similar post found with distance: {similarity_distance:.4f} (similarity: {similarity_percentage:.1f}%)")

            # Lower distance means higher similarity - if distance is below threshold, it's a duplicate
            if similarity_distance < threshold:
                print(f"DUPLICATE DETECTED! Distance ({similarity_distance:.4f}) is below threshold ({threshold}).")
                print(f"This indicates {similarity_percentage:.1f}% similarity.")
                return {
                    "duplicate_id": most_similar_post.uuid,
                    "distance": similarity_distance,
                    "similarity_percentage": similarity_percentage
                }
            
            print(f"Post appears to be original (similarity: {similarity_percentage:.1f}% < {(1-threshold)*100:.1f}% threshold).")
            return None
            
        except Exception as e:
            print(f"Error during duplicate check: {e}")
            return None

    def process_new_post(self, user_id: str, text_content: str, image_path: str) -> str | None:
        """
        Main pipeline function for processing and validating a new post.
        """
        print(f"\n--- Processing new post for user: {user_id} ---")
        
        # 1. Gibberish Check
        if self.is_gibberish(text_content):
            print("Post rejected: Content is gibberish.")
            return None
        
        # 2. Duplicate Check
        duplicate_info = self.check_for_duplicates(text_content, image_path)
        if duplicate_info:
            print(f"Post rejected: Content is a duplicate of {duplicate_info['duplicate_id']} with {duplicate_info['similarity_percentage']:.1f}% similarity.")
            return None
            
        # 3. If all checks pass, add to Database
        print("Content is valid and original. Adding to Weaviate.")
        
        try:
            image_b64 = self._image_to_base64(image_path)
            posts_collection = self.client.collections.get("Post")
            
            post_object = {
                "content": text_content,
                "image": image_b64,
                "user_id": user_id
            }

            new_uuid = posts_collection.data.insert(
                properties=post_object,
                uuid=uuid.uuid4()
            )
            
            print(f"Successfully added post to Weaviate with UUID: {new_uuid}")
            return str(new_uuid)
            
        except Exception as e:
            print(f"Error adding post to Weaviate: {e}")
            return None

    def close(self):
        """Close the Weaviate connection to avoid resource warnings."""
        if hasattr(self, 'client'):
            self.client.close()

if __name__ == '__main__':
    validator = None
    try:
        try:
            Image.new('RGB', (60, 30), color='red').save('test_image.png')
        except Exception as e:
            print(f"Could not create dummy image: {e}")

        validator = ContentValidator()

        valid_text = "My family enjoying a wonderful vacation at the beach this summer."
        post_id_1 = validator.process_new_post(
            user_id="user-123", 
            text_content=valid_text, 
            image_path="test_image.png"
        )
        if post_id_1:
            print(f"VALIDATION PASSED. Post ID: {post_id_1}")

        gibberish_text = "asdf qwerty kljh poiu zxcvb mnbvcx"
        post_id_2 = validator.process_new_post(
            user_id="user-456", 
            text_content=gibberish_text, 
            image_path="test_image.png"
        )
        if not post_id_2:
            print("VALIDATION FAILED AS EXPECTED.")
        else:
            print("WARNING: Gibberish was not detected properly!")
        print("\n--- Testing with more obvious gibberish ---")
        extreme_gibberish = "aaaaaaaaaaaaaaaa"
        post_id_3 = validator.process_new_post(
            user_id="user-789", 
            text_content=extreme_gibberish, 
            image_path="test_image.png"
        )
        if not post_id_3:
            print("VALIDATION FAILED AS EXPECTED for extreme gibberish.")
        else:
            print("WARNING: Extreme gibberish was not detected!")
            
        print("\n--- Testing with keyboard mashing ---")
        keyboard_mash = "lkjhgfdsa poiuytrewq"
        post_id_4 = validator.process_new_post(
            user_id="user-000", 
            text_content=keyboard_mash, 
            image_path="test_image.png"
        )
        if not post_id_4:
            print("VALIDATION FAILED AS EXPECTED for keyboard mashing.")
        else:
            print("WARNING: Keyboard mashing was not detected!")
        print("\n--- Testing duplicate detection ---")
        duplicate_text = "My family enjoying a wonderful vacation at the beach this summer."
        post_id_duplicate = validator.process_new_post(
            user_id="user-duplicate", 
            text_content=duplicate_text, 
            image_path="test_image.png"
        )
        if not post_id_duplicate:
            print("DUPLICATE DETECTION WORKING: Post was rejected as duplicate.")
        else:
            print("WARNING: Duplicate was not detected properly!")
            
    except Exception as e:
        print(f"Error during execution: {e}")
    finally:
        # Always close the connection
        if validator:
            validator.close()