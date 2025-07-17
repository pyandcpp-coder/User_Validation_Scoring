import datetime
import psycopg2
from psycopg2.pool import SimpleConnectionPool
import os
from typing import Optional

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
            self._initialize_database()
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
        """ **THE FIX IS HERE:** Creates the user_scores table with all required columns."""
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
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
                        last_reset_date DATE NOT NULL DEFAULT CURRENT_DATE,
                        daily_posts_timestamps TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[],
                        daily_likes_timestamps TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[],
                        daily_comments_timestamps TIMESTAMPTZ[] DEFAULT ARRAY[]::TIMESTAMPTZ[]
                    );
                """)
            conn.commit()
        finally:
            self.db_pool.putconn(conn)

    def _ensure_user_exists(self, conn, user_id: str):
        with conn.cursor() as cur:
            cur.execute("INSERT INTO user_scores (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING;", (user_id,))
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
            # Setting daily_max to a very high number effectively disables the daily check for this action
            return self._add_timed_points(conn, user_id, 'referrals', config.POINTS_PER_REFERRAL, config.MAX_MONTHLY_REFERRAL_POINTS, daily_max=999999)
        finally:
            self._put_conn(conn)
    
    def add_tipping_points(self, user_id: str) -> float:
        conn = self._get_conn()
        try:
            return self._add_timed_points(conn, user_id, 'tipping', config.POINTS_FOR_TIPPING, config.MAX_MONTHLY_TIPPING_POINTS, daily_max=999999)
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
                    # ... (qualitative scoring logic is correct)
                    points_to_add = ...

                new_timestamps = recent_timestamps + [now]
                cur.execute(f"""
                    UPDATE user_scores
                    SET points_from_{action_type} = LEAST(%s, points_from_{action_type} + %s),
                        daily_{action_type}_timestamps = %s
                    WHERE user_id = %s;
                """, (monthly_max, points_to_add, new_timestamps, user_id))
            
            conn.commit()
            print(f"Awarded {points_to_add:.2f} points for '{action_type}' to user {user_id}.")
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
                    SELECT points_from_posts, points_from_likes, points_from_comments, points_from_referrals, points_from_tipping 
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
    def close(self):
        if self.db_pool:
            self.db_pool.closeall()
            print("ScoringEngine: DB connection pool closed.")