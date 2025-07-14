from datetime import datetime, timedelta
from collections import defaultdict

class ScoringSystem:
    def __init__(self):
        self.user_data = defaultdict(lambda: {
            "posts": [],
            "likes": 0,
            "comments": 0,
            "referrals": 0,
            "tipping": 0,
            "verification": False,
            "token_generation": False,
            "registration": False,
            "weekly_leaderboard": False,
            "monthly_leaderboard": False,
        })

    def add_post(self, user_id, content):
        if len(self.user_data[user_id]["posts"]) >= 2:
            print("Post limit reached for the month.")
            return False
        if self.is_duplicate_content(content):
            print("Duplicate content detected.")
            return False
        if self.is_gibberish_content(content):
            print("Gibberish content detected.")
            return False
        self.user_data[user_id]["posts"].append({"content": content, "timestamp": datetime.now()})
        return True

    def add_like(self, user_id):
        if self.user_data[user_id]["likes"] >= 5:
            print("Daily like limit reached.")
            return False
        self.user_data[user_id]["likes"] += 1
        return True

    def add_comment(self, user_id):
        if self.user_data[user_id]["comments"] >= 5:
            print("Daily comment limit reached.")
            return False
        self.user_data[user_id]["comments"] += 1
        return True

    def add_referral(self, user_id):
        self.user_data[user_id]["referrals"] += 1

    def add_tipping(self, user_id, amount):
        self.user_data[user_id]["tipping"] += amount

    def verify_user(self, user_id):
        self.user_data[user_id]["verification"] = True

    def generate_token(self, user_id):
        self.user_data[user_id]["token_generation"] = True

    def register_user(self, user_id):
        self.user_data[user_id]["registration"] = True

    def calculate_score(self, user_id):
        data = self.user_data[user_id]
        score = 0

        # Post scoring
        score += min(len(data["posts"]), 2) * 0.5

        # Like scoring
        score += min(data["likes"], 5) * 0.1

        # Comment scoring
        score += min(data["comments"], 5) * 0.1

        # Referral scoring
        score += min(data["referrals"], 10)

        # Tipping scoring
        score += min(data["tipping"], 20)

        # Verification scoring
        if data["verification"]:
            score += 10

        # Token generation scoring
        if data["token_generation"]:
            score += 10

        # Registration scoring
        if data["registration"]:
            score += 10

        # Weekly leaderboard scoring
        if data["weekly_leaderboard"]:
            score += 3

        # Monthly leaderboard scoring
        if data["monthly_leaderboard"]:
            score += 3

        # Cap the score at 100
        return min(score, 100)

    def is_duplicate_content(self, content):
        # Placeholder for duplicate content detection logic
        return False

    def is_gibberish_content(self, content):
        # Placeholder for gibberish content detection logic
        return False

    def detect_plagiarism(self, content):
        # Placeholder for plagiarism detection using vector database
        return False


# Example usage
if __name__ == "__main__":
    scoring_system = ScoringSystem()
    user_id = "user123"

    scoring_system.register_user(user_id)
    scoring_system.verify_user(user_id)
    scoring_system.add_post(user_id, "This is my first post!")
    scoring_system.add_like(user_id)
    scoring_system.add_comment(user_id)
    scoring_system.add_referral(user_id)
    scoring_system.add_tipping(user_id, 10)

    print(f"User Score: {scoring_system.calculate_score(user_id)}")