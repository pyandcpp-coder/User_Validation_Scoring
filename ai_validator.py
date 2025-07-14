import weaviate
import torch
from transformers import pipeline
from PIL import Image
import base64
import uuid

gibberish_classifier = pipeline(
    "text-classification", 
    model="madhurjindal/autonlp-Gibberish-Detector-49251346"
)

class ContentValidator:
    def __init__(self, weaviate_host="http://localhost:8080"):
        """
        Initializes the connection to Weaviate and sets up the database schema.
        """
        try:
            self.client = weaviate.Client(weaviate_host)
            print("Successfully connected to Weaviate.")
        except Exception as e:
            print(f"Error connecting to Weaviate: {e}")
            raise

        self._setup_schema()

    def _setup_schema(self):
        """
        Defines and creates the 'Post' schema in Weaviate if it doesn't exist.
        This schema is configured to use the multimodal CLIP vectorizer.
        """
        schema = {
            "classes": [
                {
                    "class": "Post",
                    "description": "A user post with text and an image.",
                    "vectorizer": "multi2vec-clip",
                    "moduleConfig": {
                        "multi2vec-clip": {
                            "imageFields": ["image"],
                            "textFields": ["content"],
                        }
                    },
                    "properties": [
                        {
                            "name": "content",
                            "dataType": ["text"],
                            "description": "The text content of the post.",
                        },
                        {
                            "name": "image",
                            "dataType": ["blob"],
                            "description": "The image content of the post (base64 encoded).",
                        },
                        {
                            "name": "user_id",
                            "dataType": ["string"],
                            "description": "The ID of the user who made the post.",
                        }
                    ],
                }
            ]
        }

        if not self.client.schema.exists("Post"):
            print("Creating 'Post' schema in Weaviate...")
            self.client.schema.create(schema)
            print("Schema created successfully.")
        else:
            print("'Post' schema already exists.")

    def is_gibberish(self, text: str) -> bool:
        """
        Checks if a given text is gibberish using the pre-loaded model.
        Returns True if gibberish, False otherwise.
        """
        results = gibberish_classifier(text)
        # The model returns a 'LABEL_1' for clean text and 'LABEL_0' for gibberish.
        if results[0]['label'] == 'LABEL_0':
            print(f"Gibberish detected with score: {results[0]['score']:.4f}")
            return True
        print("Text appears to be clean.")
        return False

    def _image_to_base64(self, image_path: str) -> str:
        """Helper function to convert an image file to a base64 string."""
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')

    def process_new_post(self, user_id: str, text_content: str, image_path: str) -> str | None:
        """
        Main pipeline function for processing and validating a new post.
        """
        print(f"\n--- Processing new post for user: {user_id} ---")
        
        if self.is_gibberish(text_content):
            print("Post rejected: Content is gibberish.")
            return None # Reject post

        # 2. Add to Database (Weaviate handles the embedding automatically)
        print("Content is valid. Adding to Weaviate for vectorization.")
        
        try:
            image_b64 = self._image_to_base64(image_path)
            
            post_object = {
                "content": text_content,
                "image": image_b64,
                "user_id": user_id
            }

            new_uuid = self.client.data_object.create(
                data_object=post_object,
                class_name="Post",
                uuid=uuid.uuid4() # Generate a unique ID for the post
            )
            
            print(f"Successfully added post to Weaviate with UUID: {new_uuid}")
            return new_uuid # Return the ID of the newly stored object

        except Exception as e:
            print(f"Error adding post to Weaviate: {e}")
            return None


# --- Part 3: Example Usage ---
if __name__ == '__main__':
    # Create a dummy image file for testing
    try:
        Image.new('RGB', (60, 30), color = 'red').save('test_image.png')
    except Exception as e:
        print(f"Could not create dummy image: {e}")

    # Initialize our validator
    validator = ContentValidator()

    # --- Test Case 1: A valid post ---
    valid_text = "My family enjoying a wonderful vacation at the beach this summer."
    post_id_1 = validator.process_new_post(
        user_id="user-123", 
        text_content=valid_text, 
        image_path="test_image.png"
    )
    if post_id_1:
        print(f"VALIDATION PASSED. Post ID: {post_id_1}")

    # --- Test Case 2: A gibberish post ---
    gibberish_text = "asdf qwerty kljh poiu zxcvb"
    post_id_2 = validator.process_new_post(
        user_id="user-456", 
        text_content=gibberish_text, 
        image_path="test_image.png"
    )
    if not post_id_2:
        print("VALIDATION FAILED AS EXPECTED.")