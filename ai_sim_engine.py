from scoring_engine import ScoringEngine
from ai_validator import ContentValidator
from PIL import Image

print("Initializing AI Validator...")
validator = ContentValidator()
print("Initializing Scoring Engine...")
engine = ScoringEngine()

USER_ID = "user-qualitative-001"

# Create some dummy images for testing
Image.new('RGB', (100, 80), color = 'blue').save('ocean_pic.png')
Image.new('RGB', (100, 80), color = 'green').save('forest_pic.png')

# --- SIMULATION FUNCTION ---
def simulate_user_post(user_id, text_content, image_path):
    print(f"\n{'='*20} SIMULATING NEW POST {'='*20}")
    print(f"User: {user_id} | Text: '{text_content}'")

    # 1. The application's backend calls the ContentValidator first.
    validation_result = validator.process_new_post(user_id, text_content, image_path)

    # 2. Check the result from the validator
    if validation_result:
        # The post is valid! The validator returns the ID and originality score.
        post_id, originality_distance = validation_result
        print(f"VALIDATION PASSED. Post ID: {post_id}, Originality Distance: {originality_distance:.4f}")

        # 3. The application now calls the ScoringEngine to award points.
        engine.add_qualitative_post_points(
            user_id=user_id,
            text_content=text_content,
            image_path=image_path,
            originality_distance=originality_distance
        )
    else:
        # The post was rejected by the validator.
        print("VALIDATION FAILED. No points awarded.")

    # 4. Finally, get the user's updated total score.
    engine.get_final_score(user_id)

# --- EXECUTION BLOCK ---
# This condition is now correct and will run the code below.
if __name__ == "__main__":
    print("\n\n--- STARTING QUALITATIVE SCORING SIMULATION ---")
    print("Ensure your Ollama and Weaviate services are running.")
    
    # --- Test Case 1: A high-effort, original post ---
    simulate_user_post(
        user_id=USER_ID,
        text_content="Just returned from a breathtaking trip to the coast. The deep blue of the ocean was mesmerizing and the sunsets were unforgettable.",
        image_path="ocean_pic.png"
    )

    # --- Test Case 2: A low-effort post ---
    simulate_user_post(
        user_id=USER_ID,
        text_content="a tree",
        image_path="forest_pic.png"
    )

    # --- Test Case 3: A duplicate post ---
    simulate_user_post(
        user_id=USER_ID,
        text_content="Just returned from a breathtaking trip to the coast. The deep blue of the ocean was mesmerizing and the sunsets were unforgettable.",
        image_path="ocean_pic.png"
    )
    
    print("\n--- SIMULATION COMPLETE ---")
    # Close the validator's connection when done to prevent resource warnings.
    validator.close()