import datetime
import scoring_config as config

class ScoringEngine:
    def __init__(self):
        """
        Initializes the scoring engine.
        In a real application, this would connect to a database (e.g., Redis, SQL).
        For this example, we'll store user data in a Python dictionary.
        """
        self.users_data = {}

    def _get_user(self, user_id: str):
        """
        Helper to retrieve a user's data or create it if it doesn't exist.
        Also handles resetting monthly scores.
        """
        if user_id not in self.users_data:
            self.users_data[user_id] = self._create_new_user_data()
        
        user = self.users_data[user_id]
        
        today = datetime.date.today()
        if user['last_reset_date'].month != today.month or user['last_reset_date'].year != today.year:
            one_time_events = user['one_time_events']
            self.users_data[user_id] = self._create_new_user_data()
            self.users_data[user_id]['one_time_events'] = one_time_events
            print(f"Monthly scores reset for user {user_id}.")

        return self.users_data[user_id]

    def _create_new_user_data(self) -> dict:
        """Returns a dictionary with the default structure for a user's scoring data."""
        return {
            "monthly_raw_score": 0.0,
            "points_from_posts": 0.0,
            "points_from_likes": 0.0,
            "points_from_comments": 0.0,
            "points_from_referrals": 0.0,
            "points_from_tipping": 0.0,
            "one_time_events": set(), # To track 'registered', 'verified'
            "last_reset_date": datetime.date.today()
        }

    def add_post_points(self, user_id: str):
        """Adds points for a new, AI-validated post."""
        user = self._get_user(user_id)
        if user['points_from_posts'] < config.MAX_MONTHLY_POST_POINTS:
            user['points_from_posts'] += config.POINTS_PER_POST
            print(f"Added {config.POINTS_PER_POST} points for a post to user {user_id}.")
        else:
            print(f"User {user_id} has reached the monthly post point limit.")

    def add_like_points(self, user_id: str):
        """Adds points for a new, validated like."""
        user = self._get_user(user_id)
        if user['points_from_likes'] < config.MAX_MONTHLY_LIKE_POINTS:
            user['points_from_likes'] += config.POINTS_PER_LIKE
            print(f"Added {config.POINTS_PER_LIKE} points for a like to user {user_id}.")
        else:
            print(f"User {user_id} has reached the monthly like point limit.")
            
    def add_comment_points(self, user_id: str):
        """Adds points for a new, validated comment."""
        user = self._get_user(user_id)
        if user['points_from_comments'] < config.MAX_MONTHLY_COMMENT_POINTS:
            user['points_from_comments'] += config.POINTS_PER_COMMENT
            print(f"Added {config.POINTS_PER_COMMENT} points for a comment to user {user_id}.")
        else:
            print(f"User {user_id} has reached the monthly comment point limit.")
            

    def add_registration_points(self, user_id: str):
        """Adds points for completing registration, only once."""
        user = self._get_user(user_id)
        if 'registered' not in user['one_time_events']:
            # These are added to the base raw score and are permanent
            user['monthly_raw_score'] += config.POINTS_FOR_REGISTRATION
            user['one_time_events'].add('registered')
            print(f"Awarded {config.POINTS_FOR_REGISTRATION} one-time registration points to {user_id}.")
        else:
            print(f"User {user_id} has already received registration points.")
            

    def add_referral_points(self,user_id: str):
        user = self._get_user(user_id)
        if 'user_id' not in user['one_time_events']:
            user['monthly_raw_score'] += config.POINTS_FOR_REFERRAL
            user['one_time_events'].add('user_id')
            print(f"Awarded {config.POINTS_FOR_REFERRAL} one-time referral points to {user_id}.")
        else:
            print(f"User {user_id} has already received referral points.")

    def add_tipping_points(self, user_id: str):
        user = self._get_user(user_id)
        if 'tipping' not in user['one_time_events']:
            user['monthly_raw_score'] += config.POINTS_FOR_TIPPING
            user['one_time_events'].add('tipping')
            print(f"Awarded {config.POINTS_FOR_TIPPING} one-time tipping points to {user_id}.")
        else:
            print(f"User {user_id} has already received tipping points.")


    def get_final_score(self, user_id: str) -> float:
        """
        Calculates the user's total raw score and normalizes it to a 0-100 scale.
        """
        user = self._get_user(user_id)
        
        total_monthly_points = (
            user['points_from_posts'] +
            user['points_from_likes'] +
            user['points_from_comments'] +
            user['points_from_referrals'] +
            user['points_from_tipping']
        )
        
        current_raw_score = total_monthly_points + user['monthly_raw_score']
        total_possible = config.TOTAL_POSSIBLE_MONTHLY_POINTS
        
        if total_possible == 0:
            return 0.0 
        normalized_score = (total_monthly_points / total_possible) * 100
        final_score = max(0.0, min(normalized_score, 100.0))
        
        print(f"\nUser {user_id} Vitals:")
        print(f"  - Raw Monthly Points: {total_monthly_points:.2f} / {total_possible:.2f}")
        print(f"  - Permanent Bonus Points: {user['monthly_raw_score']:.2f}")
        print(f"  - Final Score (0-100 Scale): {final_score:.2f}")
        
        return final_score