import datetime
import psycopg2
from psycopg2.pool import SimpleConnectionPool
import os
from typing import Optional
import datetime
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from . import scoring_config as config
from .ollama_scorer import OllamaQualityScorer

class ScoringEngine:
    def __init__(self):
        self.quality_scorer = OllamaQualityScorer()
        db_host = os.getenv("POSTGRES_HOST", "localhost")
        try:
            self.db_pool = SimpleConnectionPool(
                minconn=1, maxconn=10,
                dbname=os.getenv("POSTGRES_DB", "scoring_db"),
                user=os.getenv("POSTGRES_USER", "scoring_user"),
                password=os.getenv("POSTGRES_PASSWORD", "scoring_password"),
                host=db_host,
                port=os.getenv("POSTGRES_PORT", "5432")
            )
            print(f"ScoringEngine: DB connection pool created for {db_host}.")
        except psycopg2.OperationalError as e:
            print(f"FATAL: ScoringEngine could not connect to PostgreSQL. Details: {e}")
            raise
    
    def _get_conn(self):
        """Gets a connection from the pool."""
        return self.db_pool.getconn()

    def _put_conn(self, conn):
        """Returns a connection to the pool."""
        self.db_pool.putconn(conn)

    def _initialize_database(self):
        """Creates or updates the user_scores table with all required columns including crypto."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                print("Ensuring 'user_scores' table exists...")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_scores (
                        user_id VARCHAR(255) PRIMARY KEY,
                        points_from_posts REAL DEFAULT 0.0,
                        points_from_likes REAL DEFAULT 0.0,
                        points_from_comments REAL DEFAULT 0.0,
                        points_from_referrals REAL DEFAULT 0.0,
                        points_from_tipping REAL DEFAULT 0.0,
                        points_from_crypto REAL DEFAULT 0.0,
                        one_time_points REAL DEFAULT 0.0,
                        one_time_events TEXT[] DEFAULT ARRAY[]::TEXT[],
                        last_reset_date DATE NOT NULL DEFAULT CURRENT_DATE,
                        daily_posts_timestamps TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[],
                        daily_likes_timestamps TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[],
                        daily_comments_timestamps TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[],
                        daily_referrals_timestamps TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[],
                        daily_tipping_timestamps TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[],
                        daily_crypto_timestamps TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[],
                        last_active_date DATE,
                        consecutive_activity_days INTEGER DEFAULT 0,
                        historical_engagement_score REAL DEFAULT 0.0
                    );
                """)
                print("'user_scores' table exists.")
            self._update_database_schema(conn)
            conn.commit()
            print("Database schema is up-to-date.")
        except Exception as e:
            print(f"DATABASE INITIALIZATION ERROR: {e}")
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    def _update_database_schema(self, conn):
        """
        Checks for and adds new columns to an existing user_scores table
        to ensure backward compatibility without manual database changes.
        """
        columns_to_add = {
            "last_active_date": "DATE",
            "consecutive_activity_days": "INTEGER DEFAULT 0",
            "historical_engagement_score": "REAL DEFAULT 0.0",
            "points_from_crypto": "REAL DEFAULT 0.0",  
            "daily_crypto_timestamps": "TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[]"  
        }

        with conn.cursor() as cur:
            for column_name, column_type in columns_to_add.items():
                cur.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='user_scores' AND column_name=%s;
                """, (column_name,))
                
                if cur.fetchone():
                    print(f"Column '{column_name}' already exists.")
                else:
                    print(f"Column '{column_name}' not found. Adding it...")
                    cur.execute(f"ALTER TABLE user_scores ADD COLUMN {column_name} {column_type};")
                    print(f"Column '{column_name}' added successfully.")
        
    def _ensure_user_exists(self, conn, user_id: str):
        """Ensures a user record exists in the database before proceeding."""
        with conn.cursor() as cur:
            cur.execute("INSERT INTO user_scores (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING;", (user_id,))

    # Existing methods remain the same...
    def add_qualitative_post_points(self, user_id: str, text_content: str, image_path: Optional[str], originality_distance: float) -> float:
        conn = self._get_conn()
        try:
            return self._add_timed_points(
                conn, user_id, 'posts', 0, config.MAX_MONTHLY_POST_POINTS, config.POST_LIMIT_DAY, 
                is_post=True, text_content=text_content, image_path=image_path, originality_distance=originality_distance
            )
        finally:
            self._put_conn(conn)

    def add_like_points(self, user_id: str) -> float:
        conn = self._get_conn()
        try:
            return self._add_timed_points(conn, user_id, 'likes', config.POINTS_PER_LIKE, config.MAX_MONTHLY_LIKE_POINTS, config.LIKE_LIMIT_DAY)
        finally:
            self._put_conn(conn)

    def add_comment_points(self, user_id: str) -> float:
        conn = self._get_conn()
        try:
            return self._add_timed_points(conn, user_id, 'comments', config.POINTS_PER_COMMENT, config.MAX_MONTHLY_COMMENT_POINTS, config.COMMENT_LIMIT_DAY)
        finally:
            self._put_conn(conn)

    def add_referral_points(self, user_id: str) -> float:
        conn = self._get_conn()
        try:
            return self._add_timed_points(conn, user_id, 'referrals', config.POINTS_PER_REFERRAL, config.MAX_MONTHLY_REFERRAL_POINTS, 999999)
        finally:
            self._put_conn(conn)
    
    def add_tipping_points(self, user_id: str) -> float:
        conn = self._get_conn()
        try:
            return self._add_timed_points(conn, user_id, 'tipping', config.POINTS_FOR_TIPPING, config.MAX_MONTHLY_TIPPING_POINTS, 999999)
        finally:
            self._put_conn(conn)

    # NEW METHOD: Add crypto interaction points
    def add_crypto_points(self, user_id: str) -> float:
        """Award points for crypto-related interactions (trading, staking, etc.)."""
        conn = self._get_conn()
        try:
            return self._add_timed_points(conn, user_id, 'crypto', config.POINTS_FOR_CRYPTO, config.MAX_MONTHLY_CRYPTO_POINTS, config.CRYPTO_LIMIT_DAY)
        finally:
            self._put_conn(conn)

    def _add_timed_points(self, conn, user_id: str, action_type: str, points_to_add: float, monthly_max: float, daily_max: int, **kwargs) -> float:
        """A generic and robust helper that checks daily and monthly limits in a safe transaction."""
        try:
            self._ensure_user_exists(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(f"SELECT points_from_{action_type}, daily_{action_type}_timestamps FROM user_scores WHERE user_id = %s FOR UPDATE;", (user_id,))
                record = cur.fetchone()
                current_monthly_points = record[0] if record else 0.0
                timestamps = record[1] if record and record[1] else []

                if round(current_monthly_points, 2) >= monthly_max:
                    print(f"User {user_id} has reached the monthly '{action_type}' limit.")
                    conn.rollback()
                    return 0.0
                
                now = datetime.datetime.now(datetime.timezone.utc)
                twenty_four_hours_ago = now - datetime.timedelta(hours=24)
                
                recent_timestamps = [ts for ts in timestamps if ts > twenty_four_hours_ago]
                
                if len(recent_timestamps) >= daily_max:
                    print(f"User {user_id} has reached the daily '{action_type}' limit of {daily_max}.")
                    conn.rollback()
                    return 0.0

                if kwargs.get('is_post'):
                    print("--- Performing qualitative scoring for post ---")
                    text_content = kwargs.get('text_content', '')
                    image_path = kwargs.get('image_path')
                    originality_distance = kwargs.get('originality_distance', 0.0)

                    # Get the 0-10 quality score from the AI model
                    quality_score = self.quality_scorer.get_quality_score(text_content, image_path)
                    
                    # Define a bonus based on the quality score (e.g., up to 1 extra point)
                    quality_bonus = (quality_score / 10.0) * 1.0 
                    
                    # Define a smaller bonus based on originality (e.g., up to 0.25 extra points)
                    # The distance is higher for more original content, so we can use it directly
                    originality_bonus = originality_distance * 0.25

                    # Calculate the final points for this specific post
                    points_to_add = config.POINTS_PER_POST + quality_bonus + originality_bonus
                    print(f"Qualitative Score Breakdown: Base({config.POINTS_PER_POST}) + Quality({quality_bonus:.2f}) + Originality({originality_bonus:.2f}) = {points_to_add:.2f}")

                new_timestamps = recent_timestamps + [now]
                cur.execute(f"""
                    UPDATE user_scores
                    SET points_from_{action_type} = LEAST(%s, points_from_{action_type} + %s),
                        daily_{action_type}_timestamps = %s,
                        last_active_date = %s
                    WHERE user_id = %s;
                """, (monthly_max, points_to_add, new_timestamps, now.date(), user_id))
            
            conn.commit()
            print(f"Awarded {points_to_add:.4f} points for '{action_type}' to user {user_id}. Activity date recorded.")
            return points_to_add
        except psycopg2.Error as e:
            print(f"DATABASE ERROR in _add_timed_points: {e}")
            conn.rollback()
            return 0.0
        except Exception as e:
            print(f"UNEXPECTED ERROR in _add_timed_points for user {user_id}: {e}")
            conn.rollback()
            return 0.0

    def get_final_score(self, user_id: str) -> float:
        """Fetches all points from the DB and calculates the final 0-100 score."""
        conn = self._get_conn()
        try:
            self._ensure_user_exists(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT points_from_posts, points_from_likes, points_from_comments, 
                           points_from_referrals, points_from_tipping, points_from_crypto 
                    FROM user_scores WHERE user_id = %s;
                """, (user_id,))
                record = cur.fetchone()
                if not record: return 0.0
                
                total_monthly_points = sum(record)
                total_possible = config.TOTAL_POSSIBLE_MONTHLY_POINTS
                if total_possible == 0: return 0.0
                
                normalized_score = (total_monthly_points / total_possible) * 100
                return max(0.0, min(normalized_score, 100.0))
        finally:
            self._put_conn(conn)
    def deduct_post_points(self, user_id: str, points_to_deduct: float) -> bool:
        """Deduct points from a user's post score when a post is deleted."""
        conn = self._get_conn()
        try:
            self._ensure_user_exists(conn, user_id)
            with conn.cursor() as cur:
                # Get current points
                cur.execute(
                    "SELECT points_from_posts FROM user_scores WHERE user_id = %s FOR UPDATE;", 
                    (user_id,)
                )
                record = cur.fetchone()
                current_points = record[0] if record else 0.0
                
                # Calculate new points (ensure it doesn't go negative)
                new_points = max(0.0, current_points - points_to_deduct)
                
                # Update the points
                cur.execute(
                    "UPDATE user_scores SET points_from_posts = %s WHERE user_id = %s;",
                    (new_points, user_id)
                )
                
            conn.commit()
            print(f"Deducted {points_to_deduct:.4f} points from user {user_id}. New post points: {new_points:.4f}")
            return True
            
        except Exception as e:
            print(f"ERROR deducting points for user {user_id}: {e}")
            conn.rollback()
            return False
            
        finally:
            self._put_conn(conn)
            
    def close(self):
        if self.db_pool:
            self.db_pool.closeall()
            print("ScoringEngine: DB connection pool closed.")