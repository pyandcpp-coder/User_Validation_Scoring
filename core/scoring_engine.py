import datetime
import psycopg2
import os
from . import scoring_config as config
from .ollama_scorer import OllamaQualityScorer

class ScoringEngine:
    def __init__(self):
        """Initializes the engine and connects to the PostgreSQL database."""
        self.quality_scorer = OllamaQualityScorer()
        try:
            self.conn = psycopg2.connect(
                dbname="scoring_db",
                user="scoring_user",
                password="scoring_password",
                host="localhost",
                port="5432"
            )
            self._initialize_database()
            print("Successfully connected to PostgreSQL database.")
        except psycopg2.OperationalError as e:
            print(f"FATAL: Could not connect to PostgreSQL. Is the Docker container running? Details: {e}")
            raise

    def _initialize_database(self):
        """Creates the scoring table if it doesn't already exist."""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_scores (
                    user_id VARCHAR(255) PRIMARY KEY,
                    points_from_posts REAL DEFAULT 0.0,
                    points_from_likes REAL DEFAULT 0.0,
                    points_from_comments REAL DEFAULT 0.0,
                    points_from_referrals REAL DEFAULT 0.0,
                    points_from_tipping REAL DEFAULT 0.0,
                    one_time_points REAL DEFAULT 0.0,
                    one_time_events TEXT[] DEFAULT ARRAY[]::TEXT[],
                    last_reset_date DATE NOT NULL DEFAULT CURRENT_DATE
                );
            """)
            self.conn.commit()

    def _ensure_user_exists(self, user_id: str):
        """A private helper to create a user record if it's missing."""
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO user_scores (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING;", (user_id,))
            self.conn.commit()

    def _get_user(self, user_id: str) -> dict:
        """Fetches user data from the database and returns it as a dictionary."""
        self._ensure_user_exists(user_id)
        
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, points_from_posts, points_from_likes, points_from_comments, 
                       points_from_referrals, points_from_tipping, one_time_points, one_time_events
                FROM user_scores WHERE user_id = %s;
            """, (user_id,))
            record = cur.fetchone()
            
            if record:
                return {
                    'user_id': record[0],
                    'points_from_posts': record[1],
                    'points_from_likes': record[2],
                    'points_from_comments': record[3],
                    'points_from_referrals': record[4],
                    'points_from_tipping': record[5],
                    'one_time_points': record[6],
                    'one_time_events': set(record[7]) if record[7] else set()
                }
            else:
                # This shouldn't happen due to _ensure_user_exists, but just in case
                return {
                    'user_id': user_id,
                    'points_from_posts': 0.0,
                    'points_from_likes': 0.0,
                    'points_from_comments': 0.0,
                    'points_from_referrals': 0.0,
                    'points_from_tipping': 0.0,
                    'one_time_points': 0.0,
                    'one_time_events': set()
                }

    def _update_user(self, user_data: dict):
        """Updates user data in the database."""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE user_scores 
                SET points_from_posts = %s, points_from_likes = %s, points_from_comments = %s,
                    points_from_referrals = %s, points_from_tipping = %s, one_time_points = %s,
                    one_time_events = %s
                WHERE user_id = %s;
            """, (
                user_data['points_from_posts'],
                user_data['points_from_likes'],
                user_data['points_from_comments'],
                user_data['points_from_referrals'],
                user_data['points_from_tipping'],
                user_data['one_time_points'],
                list(user_data['one_time_events']),
                user_data['user_id']
            ))
            self.conn.commit()

    def add_qualitative_post_points(self, user_id: str, text_content: str, image_path: str, originality_distance: float):
        """Calculates and adds qualitative post points to the database."""
        self._ensure_user_exists(user_id)

        # 1. Fetch the user's current post points first
        with self.conn.cursor() as cur:
            cur.execute("SELECT points_from_posts FROM user_scores WHERE user_id = %s;", (user_id,))
            current_post_points = cur.fetchone()[0]

        # 2. Check if the user has already reached the monthly cap
        if round(current_post_points, 2) >= config.MAX_MONTHLY_POST_POINTS:
            print(f"User {user_id} has reached the monthly post point limit.")
            return

        # 3. Calculate the new points (this logic is CPU-bound and fine)
        llm_score = self.quality_scorer.get_quality_score(text_content, image_path)
        originality_score = min(originality_distance / 0.6, 1.0)
        max_points_for_post = 2.5
        points_from_originality = originality_score * (max_points_for_post * 0.4)
        points_from_quality = (llm_score / 10.0) * (max_points_for_post * 0.6)
        total_post_points = points_from_originality + points_from_quality
        
        # 4. Atomically update the score in the database
        with self.conn.cursor() as cur:
            # Use LEAST to ensure the new score doesn't exceed the max cap
            cur.execute("""
                UPDATE user_scores
                SET points_from_posts = LEAST(%s, points_from_posts + %s)
                WHERE user_id = %s;
            """, (config.MAX_MONTHLY_POST_POINTS, total_post_points, user_id))
            self.conn.commit()
        
        print(f"Awarded {total_post_points:.2f} qualitative points to user {user_id}.")
        print(f"  - Originality: {points_from_originality:.2f}, Quality: {points_from_quality:.2f}")

    def add_post_points(self, user_id: str):
        """Adds standard post points."""
        user = self._get_user(user_id)
        # By rounding, we avoid floating point errors.
        if round(user['points_from_posts'], 2) < config.MAX_MONTHLY_POST_POINTS:
            user['points_from_posts'] += config.POINTS_PER_POST
            self._update_user(user)
            print(f"Added {config.POINTS_PER_POST} points for a post.")
        else:
            print(f"User {user_id} has reached the monthly post point limit.")

    def add_like_points(self, user_id: str):
        """Adds points for likes."""
        user = self._get_user(user_id)
        if round(user['points_from_likes'], 2) < config.MAX_MONTHLY_LIKE_POINTS:
            user['points_from_likes'] += config.POINTS_PER_LIKE
            self._update_user(user)
            print(f"Added {config.POINTS_PER_LIKE} points for a like.")
        else:
            print(f"User {user_id} has reached the monthly like point limit.")
            
    def add_comment_points(self, user_id: str):
        """Adds points for comments."""
        user = self._get_user(user_id)
        if round(user['points_from_comments'], 2) < config.MAX_MONTHLY_COMMENT_POINTS:
            user['points_from_comments'] += config.POINTS_PER_COMMENT
            self._update_user(user)
            print(f"Added {config.POINTS_PER_COMMENT} points for a comment.")
        else:
            print(f"User {user_id} has reached the monthly comment point limit.")
    
    def add_referral_points(self, user_id: str):
        """Adds points for referrals."""
        user = self._get_user(user_id)
        if round(user['points_from_referrals'], 2) < config.MAX_MONTHLY_REFERRAL_POINTS:
            user['points_from_referrals'] += config.POINTS_PER_REFERRAL
            self._update_user(user)
            print(f"Added {config.POINTS_PER_REFERRAL} points for a referral.")
        else:
            print(f"User {user_id} has reached the monthly referral point limit.")
    
    def add_tipping_points(self, user_id: str):
        """Adds points for using tipping feature."""
        user = self._get_user(user_id)
        if round(user['points_from_tipping'], 2) < config.MAX_MONTHLY_TIPPING_POINTS:
            user['points_from_tipping'] = config.MAX_MONTHLY_TIPPING_POINTS
            self._update_user(user)
            print(f"Added {config.MAX_MONTHLY_TIPPING_POINTS} points for using tipping feature.")
        else:
            print(f"User {user_id} has already received tipping points this month.")

    def add_registration_points(self, user_id: str):
        """Adds one-time registration points."""
        user = self._get_user(user_id)
        if 'registered' not in user['one_time_events']:
            user['one_time_points'] += config.POINTS_FOR_REGISTRATION
            user['one_time_events'].add('registered')
            self._update_user(user)
            print(f"Awarded {config.POINTS_FOR_REGISTRATION} one-time registration points.")
        else:
            print(f"User {user_id} has already received registration points.")

    def add_verification_points(self, user_id: str):
        """Adds one-time verification points."""
        user = self._get_user(user_id)
        if 'verified' not in user['one_time_events']:
            user['one_time_points'] += config.POINTS_FOR_VERIFICATION
            user['one_time_events'].add('verified')
            self._update_user(user)
            print(f"Awarded {config.POINTS_FOR_VERIFICATION} one-time verification points.")
        else:
            print(f"User {user_id} has already received verification points.")

    def get_final_score(self, user_id: str) -> float:
        """Fetches all of a user's points and calculates their final 0-100 score."""
        self._ensure_user_exists(user_id)
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT points_from_posts, points_from_likes, points_from_comments, 
                       points_from_referrals, points_from_tipping, one_time_points
                FROM user_scores WHERE user_id = %s;
            """, (user_id,))
            record = cur.fetchone()

            if not record: 
                return 0.0
            
            total_monthly_points = sum(record[:5])  # First 5 fields are monthly points
            one_time_points = record[5]
            total_possible = config.TOTAL_POSSIBLE_MONTHLY_POINTS

            if total_possible == 0: 
                return 0.0

            normalized_score = (total_monthly_points / total_possible) * 100
            final_score = max(0.0, min(normalized_score, 100.0))
            
            print(f"\n--- User {user_id} Vitals ---")
            print(f"  - Monthly Score: {total_monthly_points:.2f} / {total_possible:.2f}")
            print(f"  - One-Time Bonus Points: {one_time_points:.2f}")
            print(f"  - Final Normalized Score (0-100): {final_score:.2f}")
            
            return final_score

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            print("PostgreSQL connection closed.")