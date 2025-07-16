from scoring_engine import ScoringEngine
import time

engine = ScoringEngine()

USER_ID = "user-alpha-007"


print("--- Day 1: Registration ---")
engine.add_registration_points(USER_ID)
engine.get_final_score(USER_ID)
# Note: At this point, the final score is 0 because one-time points are a bonus,
# they don't contribute to the 0-100 monthly activity scale.

print("\n--- Day 2: User gets 5 likes and posts once ---")
# Let's assume your app validated 5 likes and sent them to the engine
for _ in range(5):
    engine.add_like_points(USER_ID)
    
# The user's post is validated by the AI service, so we award points
# (Your app would have called the AI API first and gotten an "approved" status)
engine.add_post_points(USER_ID)
engine.get_final_score(USER_ID)

print(f"\n--- Day 5: User posts 60 more times to hit the monthly cap ---")
for i in range(60):
    print(f"Simulating post {i+2}:")
    engine.add_post_points(USER_ID)
engine.get_final_score(USER_ID)


print("\n--- Day 10: User tries to add another like (should be at cap) ---")
# Simulate adding likes until the cap is hit
# User already has 0.5 points from 5 likes. Max is 15. So 14.5 more points to go.
# At 0.1 points/like, that's 145 more likes.
for _ in range(145):
    engine.add_like_points(USER_ID)
    
print("--- Attempting one more like ---")
engine.add_like_points(USER_ID) # This one should be rejected
engine.get_final_score(USER_ID)