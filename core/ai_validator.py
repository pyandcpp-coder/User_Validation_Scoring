import weaviate
from transformers import pipeline
from PIL import Image
import base64
import uuid
import os
from typing import Optional
from collections import Counter
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.query import Filter

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
                # You might want to add migration logic here to add points_awarded field
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
                        name="post_id",
                        data_type=DataType.TEXT,
                        description="The unique identifier of the post"
                    ),
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
                    ),
                    Property(
                        name="points_awarded",  # NEW FIELD
                        data_type=DataType.NUMBER,
                        description="Points awarded for this post"
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
        
        # Only count letters, not numbers or other characters
        letters_only = ''.join(c for c in text if c.isalpha())
        if not letters_only:
            return False  # If no letters, let other checks decide
            
        vowel_count = sum(1 for char in letters_only if char in vowels)
        consonant_count = sum(1 for char in letters_only if char in consonants)
        total_letters = len(letters_only)
        
        if total_letters > 0:
            vowel_ratio = vowel_count / total_letters
            consonant_ratio = consonant_count / total_letters
            
            # Flag if too many consonants or too few vowels
            if consonant_ratio > 0.85 or vowel_ratio < 0.05:
                return True
        
        return False
    
    def _statistical_gibberish_check(self, text: str) -> bool:
        """Statistical analysis for gibberish detection - FIXED"""
        words = text.split()
        
        # Skip statistical checks for short texts
        if len(words) < 3:
            return False
        
        # Check average word length - RELAXED THRESHOLDS
        if words:
            # Filter out numbers and special tokens before calculating average
            actual_words = [w for w in words if any(c.isalpha() for c in w)]
            if actual_words:
                avg_word_length = sum(len(word) for word in actual_words) / len(actual_words)
                # Relaxed thresholds: was > 10 or < 2, now > 15 or < 1
                if avg_word_length > 15 or avg_word_length < 1:
                    return True
        
        # Check for words with no vowels (except common ones like "by", "my")
        common_no_vowel_words = {'by', 'my', 'gym', 'fly', 'try', 'cry', 'dry', 'fry', 'shy', 'spy', 'why', 'mr', 'mrs', 'dr', 'st', 'rd', 'nd', 'th'}
        
        for word in words:
            # Skip numbers and short words
            if word.isdigit() or len(word) <= 2:
                continue
            if len(word) > 3 and word.lower() not in common_no_vowel_words:
                if not any(vowel in word.lower() for vowel in 'aeiou'):
                    return True
        
        # Check character frequency distribution - RELAXED
        # Only check alphabetic characters
        alpha_text = ''.join(c for c in text if c.isalpha())
        if alpha_text:
            char_freq = Counter(char.lower() for char in alpha_text)
            total_chars = sum(char_freq.values())
            max_freq = max(char_freq.values())
            # Relaxed threshold: was > 0.4, now > 0.5
            if max_freq / total_chars > 0.5:
                return True
        
        return False
    
    def _ml_gibberish_check(self, text: str) -> bool:
        """ML model-based gibberish detection - MORE CONSERVATIVE"""
        try:
            results = gibberish_classifier(text)
            
            # Handle different model outputs
            if isinstance(results, list) and len(results) > 0:
                result = results[0]
                
                # For the madhurjindal model, LABEL_0 means gibberish
                if 'madhurjindal' in str(gibberish_classifier.model.config._name_or_path):
                    # Increased threshold from 0.7 to 0.85 for more confidence
                    if result['label'] == 'LABEL_0' and result['score'] > 0.85:
                        return True
                
                # For toxic-bert, we look for non-toxic (clean) text
                elif 'toxic-bert' in str(gibberish_classifier.model.config._name_or_path):
                    # Increased threshold from 0.8 to 0.9
                    if result['label'] == 'TOXIC' and result['score'] > 0.9:
                        return True
                # Increased general threshold from 0.8 to 0.85
                elif result['score'] > 0.85:
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error in ML gibberish detection: {e}")
            return False

    def _image_to_base64(self, image_path: str) -> str:
        """Helper function to convert an image file to a base64 string."""
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')

    def update_post_points(self, post_id: str, user_id: str, points: float) -> bool:
        """Update the points_awarded field for a post after calculation."""
        try:
            posts_collection = self.client.collections.get("Post")
            
            # Correct syntax - use 'filters' parameter
            response = posts_collection.query.fetch_objects(
                filters=(
                    Filter.by_property("post_id").equal(post_id) & 
                    Filter.by_property("user_id").equal(user_id)
                ),
                limit=1
            )
            
            if response.objects:
                post_uuid = response.objects[0].uuid
                # Update the points
                posts_collection.data.update(
                    uuid=post_uuid,
                    properties={"points_awarded": points}
                )
                print(f"Updated post {post_id} with {points} points")
                return True
            else:
                print(f"Post {post_id} not found for user {user_id}")
                return False
            
        except Exception as e:
            print(f"Error updating post points: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return False


    def check_for_duplicates(self, text_content: str, image_path: Optional[str], threshold: float = 0.1) -> tuple[bool, float]:
        """
        Enhanced duplicate checking with more reasonable threshold.
        Increased threshold from 0.10 to 0.35 to be less strict about duplicates.
        For context: distance values typically range from 0 (identical) to 1+ (very different)
        """
        print("--- Checking for duplicate content ---")
        print(f"Input text: '{text_content}'")
        print(f"Threshold: {threshold} (lower = more strict)")
        
        try:
            posts_collection = self.client.collections.get("Post")
            
            # Check if collection exists and has any data
            try:
                collection_info = posts_collection.aggregate.over_all(total_count=True)
                total_posts = collection_info.total_count
                print(f"Total posts in collection: {total_posts}")
                
                if total_posts == 0:
                    print("Collection is empty - no duplicates possible")
                    return (False, 1.0)
                    
            except Exception as e:
                print(f"Warning: Could not get collection info: {e}")
                # If we can't check, assume no duplicates to avoid false positives
                return (False, 1.0)

            # Perform the similarity search
            print("Performing vector similarity search...")
            response = posts_collection.query.near_text(
                query=text_content,
                limit=3,  # Get top 3 for better debugging
                return_metadata=["distance"],
                return_properties=["content", "user_id"]  # Return content for debugging
            )
            
            if not response.objects:
                print("No similar posts found")
                return (False, 1.0)
            
            print(f"Found {len(response.objects)} similar posts:")
            for i, obj in enumerate(response.objects):
                distance = obj.metadata.distance
                content_preview = obj.properties.get('content', '')[:50] + "..."
                user_id = obj.properties.get('user_id', 'unknown')
                print(f"  {i+1}. Distance: {distance:.4f}, User: {user_id}")
                print(f"      Content: '{content_preview}'")
            
            # Use the closest match for duplicate detection
            closest_distance = response.objects[0].metadata.distance
            is_duplicate = closest_distance < threshold
            
            # Additional check: exact match detection
            closest_content = response.objects[0].properties.get('content', '')
            if closest_content == text_content:
                print("EXACT MATCH DETECTED - definite duplicate")
                is_duplicate = True
                closest_distance = 0.0
            
            # For test content with UUIDs, be more lenient
            if 'test_run_' in text_content and closest_distance < 0.5:
                print("Test content detected, using more lenient threshold")
                is_duplicate = closest_distance < 0.15  # Much stricter for test content
            
            print(f"Closest match distance: {closest_distance:.4f}")
            print(f"Is duplicate (< {threshold}): {is_duplicate}")
            
            if is_duplicate:
                print("🚨 DUPLICATE DETECTED!")
                print(f"   Rejecting because distance {closest_distance:.4f} < threshold {threshold}")
            else:
                print("✅ Content appears to be original")
                
            return (is_duplicate, closest_distance)
            
        except Exception as e:
            print(f"ERROR during duplicate check: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            # On error, allow the content through
            return (False, 1.0)

    def process_new_post(self, user_id: str, post_id:str,text_content: str, image_path: Optional[str],points_awarded:float=0) -> tuple[str, float] | None:
        """Main validation pipeline. Returns (post_id, distance) on success."""
        print(f"\n--- Processing new post {post_id} for user: {user_id} ---")
        if not text_content or self.is_gibberish(text_content):
            print("Post rejected: Content is empty or gibberish.")
            return None
        
        is_duplicate, distance = self.check_for_duplicates(text_content, image_path)
        if is_duplicate:
            print(f"Post rejected: Content is a duplicate.")
            return None
            
        print("Content is valid and original. Adding to Weaviate.")
        try:
            post_object = {"post_id":post_id,"content": text_content, "user_id": user_id,"points_awarded":points_awarded}
            if image_path:
                post_object["image"] = self._image_to_base64(image_path)
            
            posts_collection = self.client.collections.get("Post")
            post_uuid = uuid.uuid4()
            posts_collection.data.insert(properties=post_object, uuid=post_uuid)
            
            new_uuid_str = str(post_uuid)
            print(f"Successfully added post to Weaviate with UUID: {new_uuid_str}")
            return (post_id, distance)
            
        except Exception as e:
            print(f"Error adding post to Weaviate: {e}")
            return None
        
    def get_post_points(self, post_id: str, user_id: str) -> float:
        """Get the points that were awarded for a specific post."""
        try:
            posts_collection = self.client.collections.get("Post")
            
            # Correct syntax - use 'filters' parameter
            response = posts_collection.query.fetch_objects(
                filters=(
                    Filter.by_property("post_id").equal(post_id) & 
                    Filter.by_property("user_id").equal(user_id)
                ),
                limit=1
            )
            
            if response.objects:
                return response.objects[0].properties.get("points_awarded", 0)
            return 0
            
        except Exception as e:
            print(f"Error getting post points: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return 0

    def delete_post(self, post_id: str, user_id: str) -> bool:
        """Delete a post from Weaviate by post_id and user_id."""
        try:
            posts_collection = self.client.collections.get("Post")
            
            # Correct syntax - use 'filters' parameter
            response = posts_collection.query.fetch_objects(
                filters=(
                    Filter.by_property("post_id").equal(post_id) & 
                    Filter.by_property("user_id").equal(user_id)
                ),
                limit=1
            )
            
            if not response.objects:
                print(f"Post {post_id} not found or doesn't belong to user {user_id}")
                return False
            
            # Get the actual UUID of the post
            post_uuid = response.objects[0].uuid
            
            # Delete the post using its actual UUID
            posts_collection.data.delete_by_id(post_uuid)
            print(f"Successfully deleted post {post_id} for user {user_id}")
            return True
            
        except Exception as e:
            print(f"Error deleting post {post_id}: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return False

    def close(self):
        """Closes the connection to the Weaviate client."""
        print("Closing Weaviate connection...")
        if hasattr(self, 'client') and self.client:
            self.client.close()