import os
import datetime
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import execute_batch
from . import scoring_config as config

class HistoricalAnalyzer:
    """
    A service that runs daily to implement an "empathy" reward system.
    It identifies users who did not meet full daily criteria, resets their streak,
    and calculates a Historical Engagement Score based on their past loyalty.
    """
    def __init__(self):
        """Initializes the database connection pool."""
        db_host = os.getenv("POSTGRES_HOST", "localhost")
        try:
            self.db_pool = SimpleConnectionPool(
                minconn=1, maxconn=5,
                dbname=os.getenv("POSTGRES_DB", "scoring_db"),
                user=os.getenv("POSTGRES_USER", "scoring_user"),
                password=os.getenv("POSTGRES_PASSWORD", "scoring_password"),
                host=db_host,
                port=os.getenv("POSTGRES_PORT", "5432")
            )
            print("HistoricalAnalyzer: DB connection pool created.")
        except psycopg2.OperationalError as e:
            print(f"FATAL: HistoricalAnalyzer could not connect to PostgreSQL. Details: {e}")
            raise

    def analyze_and_reward_users(self):
        """
        The main daily task. It categorizes users, updates streaks, and calculates
        historical scores for those who didn't meet full daily limits.
        """
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                now = datetime.datetime.now(datetime.timezone.utc)
                today = now.date()
                twenty_four_hours_ago = now - datetime.timedelta(hours=24)
                print(f"\n--- Starting User Empathy Analysis for {today} ---")

                cur.execute("""
                    SELECT 
                        user_id, last_active_date, consecutive_activity_days,
                        points_from_posts, points_from_likes, points_from_comments,
                        daily_posts_timestamps, daily_likes_timestamps, daily_comments_timestamps
                    FROM user_scores;
                """)
                all_users = cur.fetchall()
                print(f"Found {len(all_users)} total users to analyze.")

                updates_to_perform = []

                for user in all_users:
                    (user_id, last_active_date, streak, p_posts, p_likes, p_comments,
                     post_ts, like_ts, comment_ts) = user

                    # Count actions in the last 24 hours
                    posts_today = len([ts for ts in (post_ts or []) if ts > twenty_four_hours_ago])
                    likes_today = len([ts for ts in (like_ts or []) if ts > twenty_four_hours_ago])
                    comments_today = len([ts for ts in (comment_ts or []) if ts > twenty_four_hours_ago])

                    # Check if the user met the FULL daily criteria
                    met_full_criteria = (
                        posts_today >= config.POST_LIMIT_DAY and
                        likes_today >= config.LIKE_LIMIT_DAY and
                        comments_today >= config.COMMENT_LIMIT_DAY
                    )

                    if met_full_criteria:
                        # --- CATEGORY: CRITERIA MET ---
                        # They are fully rewarded. Maintain and increment their streak.
                        yesterday = today - datetime.timedelta(days=1)
                        # Increment streak if they were also active yesterday, else start a new streak of 1.
                        new_streak = streak + 1 if last_active_date == yesterday else 1
                        new_hist_score = 0.0 # Not eligible for empathy score.
                        
                        updates_to_perform.append((new_streak, new_hist_score, user_id))
                    else:
                        # --- CATEGORY: CRITERIA NOT MET (Partial or Zero activity) ---
                        # They are a candidate for the empathy reward. Their streak is lost.
                        new_streak = 0 # Streak is reset as per the logic.

                        # Calculate historical score based on their lifetime contributions and the streak they *had*.
                        lifetime_posts = (p_posts / config.POINTS_PER_POST) if config.POINTS_PER_POST > 0 else 0
                        lifetime_likes = (p_likes / config.POINTS_PER_LIKE) if config.POINTS_PER_LIKE > 0 else 0
                        lifetime_comments = (p_comments / config.POINTS_PER_COMMENT) if config.POINTS_PER_COMMENT > 0 else 0

                        # The score is based on the 'streak' value from BEFORE it was reset. This is the empathy.
                        new_hist_score = (
                            (streak * config.HISTORICAL_SCORE_WEIGHTS['streak_at_reset']) +
                            (lifetime_posts * config.HISTORICAL_SCORE_WEIGHTS['lifetime_posts']) +
                            (lifetime_likes * config.HISTORICAL_SCORE_WEIGHTS['lifetime_likes']) +
                            (lifetime_comments * config.HISTORICAL_SCORE_WEIGHTS['lifetime_comments'])
                        )
                        updates_to_perform.append((new_streak, new_hist_score, user_id))

                # Perform a single batch update for all users
                if updates_to_perform:
                    print(f"Batch-updating {len(updates_to_perform)} users...")
                    execute_batch(cur, 
                        "UPDATE user_scores SET consecutive_activity_days = %s, historical_engagement_score = %s WHERE user_id = %s;",
                        updates_to_perform
                    )
                
                conn.commit()
                print("Database update complete.")

                # Identify and log the top N users who are candidates for the empathy reward
                print(f"\n--- Top {config.TOP_INACTIVE_USERS_TO_REWARD} Candidates for Empathy Reward ---")
                cur.execute("""
                    SELECT user_id, historical_engagement_score
                    FROM user_scores
                    WHERE historical_engagement_score > 0
                    ORDER BY historical_engagement_score DESC
                    LIMIT %s;
                """, (config.TOP_INACTIVE_USERS_TO_REWARD,))
                
                top_users = cur.fetchall()
                if not top_users:
                    print("No users were eligible for the empathy reward today.")
                else:
                    for i, (user_id, score) in enumerate(top_users):
                        print(f"{i+1}. User: {user_id}, Empathy Score: {score:.4f}")
                print("--------------------------------------------------")

        except (Exception, psycopg2.Error) as error:
            print(f"ERROR during user empathy analysis: {error}")
            import traceback
            traceback.print_exc()
            conn.rollback()
        finally:
            self.db_pool.putconn(conn)
            
    def close(self):
        """Closes all connections in the database pool."""
        if self.db_pool:
            self.db_pool.closeall()
            print("HistoricalAnalyzer: DB connection pool closed.")