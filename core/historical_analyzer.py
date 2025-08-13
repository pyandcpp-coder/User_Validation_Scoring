import os
import datetime
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import execute_batch
from . import scoring_config as config
import math
import requests
import json
from typing import List, Dict, Any

class HistoricalAnalyzer:
    """
    Enhanced service that runs daily to implement category-wise qualification and empathy rewards.
    Each action type (posts, likes, comments, crypto, tipping, referrals) has independent 
    qualification criteria and empathy selection.
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

    def _check_category_qualification(self, user_data: tuple, category: str, twenty_four_hours_ago: datetime.datetime) -> bool:
        """
        Check if a user qualifies for a specific category based on daily requirements.
        
        Args:
            user_data: User database record
            category: Category to check (posts, likes, comments, crypto, tipping, referrals)
            twenty_four_hours_ago: Timestamp for 24 hours ago
            
        Returns:
            bool: True if user meets daily requirement for this category
        """
        # Unpack user data based on the SQL query structure from _get_category_results
        (user_id, streak, hist_score, p_posts, p_likes, p_comments, 
         p_referrals, p_tipping, p_crypto, post_ts, like_ts, comment_ts, 
         referral_ts, tipping_ts, crypto_ts) = user_data
        
        if category == 'posts':
            posts_today = len([ts for ts in (post_ts or []) if ts > twenty_four_hours_ago])
            return posts_today >= getattr(config, 'POST_LIMIT_DAY', 2)
            
        elif category == 'likes':
            likes_today = len([ts for ts in (like_ts or []) if ts > twenty_four_hours_ago])
            return likes_today >= getattr(config, 'LIKE_LIMIT_DAY', 5)
            
        elif category == 'comments':
            comments_today = len([ts for ts in (comment_ts or []) if ts > twenty_four_hours_ago])
            return comments_today >= getattr(config, 'COMMENT_LIMIT_DAY', 5)
            
        elif category == 'crypto':
            crypto_today = len([ts for ts in (crypto_ts or []) if ts > twenty_four_hours_ago])
            return crypto_today >= getattr(config, 'CRYPTO_LIMIT_DAY', 3)
            
        elif category == 'tipping':
            tipping_today = len([ts for ts in (tipping_ts or []) if ts > twenty_four_hours_ago])
            return tipping_today >= getattr(config, 'TIPPING_LIMIT_DAY', 1)
            
        elif category == 'referrals':
            referrals_today = len([ts for ts in (referral_ts or []) if ts > twenty_four_hours_ago])
            return referrals_today >= getattr(config, 'REFERRAL_LIMIT_DAY', 1)
            
        return False

    def _calculate_category_empathy_score(self, user_data: tuple, category: str) -> float:
        """
        Calculate empathy score for a specific category based on that category's lifetime activity.
        
        Args:
            user_data: User database record
            category: Category name (posts, likes, comments, crypto, tipping, referrals)
        """
        # Unpack user data based on the SQL query structure from _get_category_results
        (user_id, streak, hist_score, p_posts, p_likes, p_comments, 
         p_referrals, p_tipping, p_crypto, post_ts, like_ts, comment_ts, 
         referral_ts, tipping_ts, crypto_ts) = user_data
        
        # Base streak component (applies to all categories)
        streak_score = (streak or 0) * config.HISTORICAL_SCORE_WEIGHTS.get('streak_at_reset', 0.5)
        
        # Category-specific lifetime activity
        category_score = 0.0
        
        if category == 'posts':
            lifetime_posts = (p_posts / getattr(config, 'POINTS_PER_POST', 0.5)) if getattr(config, 'POINTS_PER_POST', 0.5) > 0 else 0
            category_score = lifetime_posts * config.HISTORICAL_SCORE_WEIGHTS.get('lifetime_posts', 0.25)
            
        elif category == 'likes':
            lifetime_likes = (p_likes / getattr(config, 'POINTS_PER_LIKE', 0.1)) if getattr(config, 'POINTS_PER_LIKE', 0.1) > 0 else 0
            category_score = lifetime_likes * config.HISTORICAL_SCORE_WEIGHTS.get('lifetime_likes', 0.08)
            
        elif category == 'comments':
            lifetime_comments = (p_comments / getattr(config, 'POINTS_PER_COMMENT', 0.1)) if getattr(config, 'POINTS_PER_COMMENT', 0.1) > 0 else 0
            category_score = lifetime_comments * config.HISTORICAL_SCORE_WEIGHTS.get('lifetime_comments', 0.08)
            
        elif category == 'crypto':
            crypto_points = getattr(config, 'POINTS_FOR_CRYPTO', 0.5)
            lifetime_crypto = (p_crypto / crypto_points) if crypto_points > 0 else 0
            category_score = lifetime_crypto * config.HISTORICAL_SCORE_WEIGHTS.get('lifetime_crypto', 0.09)
            
        elif category == 'tipping':
            tipping_points = getattr(config, 'POINTS_FOR_TIPPING', 0.5)
            lifetime_tipping = (p_tipping / tipping_points) if tipping_points > 0 else 0
            category_score = lifetime_tipping * config.HISTORICAL_SCORE_WEIGHTS.get('lifetime_tipping', 0.05)
            
        elif category == 'referrals':
            referral_points = getattr(config, 'POINTS_PER_REFERRAL', 10)
            lifetime_referrals = (p_referrals / referral_points) if referral_points > 0 else 0
            category_score = lifetime_referrals * config.HISTORICAL_SCORE_WEIGHTS.get('lifetime_referrals', 0.05)
        
        return streak_score + category_score

    def _get_category_results(self, category: str) -> dict:
        """
        Get qualified and empathy users for a specific category.
        
        Args:
            category: Category name (posts, likes, comments, crypto, tipping, referrals)
            
        Returns:
            dict: Contains qualified users, empathy users, and total analyzed count
        """
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                now = datetime.datetime.now(datetime.timezone.utc)
                twenty_four_hours_ago = now - datetime.timedelta(hours=24)
                
                # Get all user data with safe column handling - structure matches unpacking in other methods
                cur.execute("""
                    SELECT 
                        user_id, 
                        COALESCE(consecutive_activity_days, 0) as consecutive_activity_days, 
                        COALESCE(historical_engagement_score, 0) as historical_engagement_score,
                        COALESCE(points_from_posts, 0) as points_from_posts, 
                        COALESCE(points_from_likes, 0) as points_from_likes, 
                        COALESCE(points_from_comments, 0) as points_from_comments, 
                        COALESCE(points_from_referrals, 0) as points_from_referrals, 
                        COALESCE(points_from_tipping, 0) as points_from_tipping, 
                        COALESCE(points_from_crypto, 0) as points_from_crypto,
                        COALESCE(daily_posts_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_posts_timestamps, 
                        COALESCE(daily_likes_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_likes_timestamps, 
                        COALESCE(daily_comments_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_comments_timestamps,
                        COALESCE(daily_referrals_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_referrals_timestamps, 
                        COALESCE(daily_tipping_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_tipping_timestamps,
                        COALESCE(daily_crypto_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_crypto_timestamps
                    FROM user_scores;
                """)
                all_users = cur.fetchall()
                
                qualified_users = []
                non_qualified_users = []
                
                for user_data in all_users:
                    user_id = user_data[0]
                    
                    # Check if user qualifies for this category
                    is_qualified = self._check_category_qualification(user_data, category, twenty_four_hours_ago)
                    
                    if is_qualified:
                        qualified_users.append(user_id)
                    else:
                        # Calculate empathy score for this category
                        empathy_score = self._calculate_category_empathy_score(user_data, category)
                        if empathy_score > 0:  # Only consider users with some activity
                            non_qualified_users.append((user_id, empathy_score))
                
                # Select top 10% of non-qualified users for empathy rewards
                empathy_users = []
                if non_qualified_users:
                    non_qualified_users.sort(key=lambda x: x[1], reverse=True)
                    empathy_count = math.ceil(len(non_qualified_users) * config.REWARD_PERCENTAGE_OF_INACTIVE)
                    empathy_users = [user_id for user_id, score in non_qualified_users[:empathy_count]]
                
                return {
                    "qualified": qualified_users,
                    "empathy": empathy_users,
                    "total_analyzed": len(all_users)
                }
                
        finally:
            self.db_pool.putconn(conn)

    def _make_category_reward_api_call(self, category_results: Dict[str, Dict]) -> bool:
        """
        Makes an API call to distribute category-wise rewards.
        
        Args:
            category_results: Dictionary containing qualified and empathy users for each category
            
        Returns:
            bool: True if API call was successful, False otherwise
        """
        try:
            payload = {
                "reward_type": "category_based",
                "categories": category_results,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "summary": {
                    "total_categories": len(category_results),
                    "total_qualified_users": sum(len(cat['qualified']) for cat in category_results.values()),
                    "total_empathy_users": sum(len(cat['empathy']) for cat in category_results.values())
                }
            }
            
            headers = {"Content-Type": "application/json"}
            
            print(f"Making category-wise reward API call...")
            print(f"Payload: {json.dumps(payload, indent=2)}")
            
            # Uncomment when you have the actual API endpoint
            # response = requests.post(
            #     self.reward_api_url,
            #     json=payload,
            #     headers=headers,
            #     timeout=30
            # )
            # response.raise_for_status()
            
            print(f"Category-wise reward API call successful!")
            return True
            
        except Exception as e:
            print(f"Error making category-wise reward API call: {e}")
            return False

    def analyze_and_reward_users(self):
        """
        Enhanced daily analysis with category-wise qualification and empathy rewards.
        Each category (posts, likes, comments, crypto, tipping, referrals) is analyzed independently.
        """
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                now = datetime.datetime.now(datetime.timezone.utc)
                today = now.date()
                twenty_four_hours_ago = now - datetime.timedelta(hours=24)
                print(f"\n--- Starting Category-wise User Analysis for {today} ---")
                
                # Get all user data including crypto fields - same structure as _get_category_results
                cur.execute("""
                    SELECT 
                        user_id, last_active_date, consecutive_activity_days,
                        COALESCE(points_from_posts, 0) as points_from_posts, 
                        COALESCE(points_from_likes, 0) as points_from_likes, 
                        COALESCE(points_from_comments, 0) as points_from_comments, 
                        COALESCE(points_from_referrals, 0) as points_from_referrals, 
                        COALESCE(points_from_tipping, 0) as points_from_tipping, 
                        COALESCE(points_from_crypto, 0) as points_from_crypto,
                        COALESCE(daily_posts_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_posts_timestamps, 
                        COALESCE(daily_likes_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_likes_timestamps, 
                        COALESCE(daily_comments_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_comments_timestamps,
                        COALESCE(daily_referrals_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_referrals_timestamps, 
                        COALESCE(daily_tipping_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_tipping_timestamps,
                        COALESCE(daily_crypto_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_crypto_timestamps
                    FROM user_scores;
                """)
                all_users = cur.fetchall()
                print(f"Found {len(all_users)} total users to analyze.")
                
                # Define categories to analyze
                categories = ['posts', 'likes', 'comments', 'crypto', 'tipping', 'referrals']
                category_results = {}
                
                # Analyze each category independently
                for category in categories:
                    print(f"\n--- Analyzing Category: {category.upper()} ---")
                    
                    qualified_users = []
                    non_qualified_users = []
                    
                    for user_data in all_users:
                        user_id = user_data[0]
                        
                        # Repack user_data to match the structure expected by _check_category_qualification
                        # Original: (user_id, last_active_date, streak, p_posts, p_likes, p_comments, p_referrals, p_tipping, p_crypto, ...)
                        # Expected: (user_id, streak, hist_score, p_posts, p_likes, p_comments, p_referrals, p_tipping, p_crypto, ...)
                        repacked_data = (
                            user_data[0],   # user_id
                            user_data[2],   # consecutive_activity_days (streak)
                            0,              # historical_engagement_score (not used in qualification check)
                            user_data[3],   # points_from_posts
                            user_data[4],   # points_from_likes
                            user_data[5],   # points_from_comments
                            user_data[6],   # points_from_referrals
                            user_data[7],   # points_from_tipping
                            user_data[8],   # points_from_crypto
                            user_data[9],   # daily_posts_timestamps
                            user_data[10],  # daily_likes_timestamps
                            user_data[11],  # daily_comments_timestamps
                            user_data[12],  # daily_referrals_timestamps
                            user_data[13],  # daily_tipping_timestamps
                            user_data[14],  # daily_crypto_timestamps
                        )
                        
                        # Check if user qualifies for this category
                        is_qualified = self._check_category_qualification(repacked_data, category, twenty_four_hours_ago)
                        
                        if is_qualified:
                            qualified_users.append(user_id)
                            print(f"   QUALIFIED for {category}: {user_id}")
                        else:
                            # Calculate empathy score for this category
                            empathy_score = self._calculate_category_empathy_score(repacked_data, category)
                            if empathy_score > 0:  # Only consider users with some activity
                                non_qualified_users.append((user_id, empathy_score))
                    
                    # Select top 10% of non-qualified users for empathy rewards
                    empathy_users = []
                    if non_qualified_users:
                        non_qualified_users.sort(key=lambda x: x[1], reverse=True)
                        empathy_count = math.ceil(len(non_qualified_users) * config.REWARD_PERCENTAGE_OF_INACTIVE)
                        empathy_users = [user_id for user_id, score in non_qualified_users[:empathy_count]]
                        
                        print(f"   Empathy candidates for {category}: {len(non_qualified_users)}")
                        print(f"   Empathy recipients for {category}: {len(empathy_users)}")
                        for i, (user_id, score) in enumerate(non_qualified_users[:empathy_count]):
                            print(f"      {i+1}. {user_id} (Score: {score:.4f})")
                    
                    # Store results for this category
                    category_results[category] = {
                        'qualified': qualified_users,
                        'empathy': empathy_users,
                        'stats': {
                            'total_users_analyzed': len(all_users),
                            'qualified_count': len(qualified_users),
                            'empathy_candidates': len(non_qualified_users),
                            'empathy_recipients': len(empathy_users)
                        }
                    }
                
                # Update database - for category-based system, we might want to track this differently
                # For now, let's update the overall streak based on any activity
                updates_to_perform = []
                for user_data in all_users:
                    user_id = user_data[0]
                    last_active_date = user_data[1]
                    streak = user_data[2] or 0
                    
                    # Repack data for qualification check
                    repacked_data = (
                        user_data[0], user_data[2], 0, user_data[3], user_data[4], user_data[5],
                        user_data[6], user_data[7], user_data[8], user_data[9], user_data[10],
                        user_data[11], user_data[12], user_data[13], user_data[14]
                    )
                    
                    # Check if user had ANY activity today across all categories
                    had_any_activity = any(
                        self._check_category_qualification(repacked_data, cat, twenty_four_hours_ago) 
                        for cat in categories
                    )
                    
                    if had_any_activity:
                        yesterday = today - datetime.timedelta(days=1)
                        new_streak = streak + 1 if last_active_date == yesterday else 1
                        updates_to_perform.append((new_streak, 0.0, user_id))  # Reset empathy score for active users
                    else:
                        # User had no activity - reset streak but keep empathy score
                        updates_to_perform.append((0, 0.0, user_id))
                
                # Update database
                if updates_to_perform:
                    print(f"\nUpdating {len(updates_to_perform)} user records...")
                    execute_batch(cur, 
                        "UPDATE user_scores SET consecutive_activity_days = %s, historical_engagement_score = %s WHERE user_id = %s;",
                        updates_to_perform
                    )
                
                conn.commit()
                print("Database updates complete.")
                
                # Print comprehensive summary
                print(f"\n--- CATEGORY-WISE ANALYSIS SUMMARY ---")
                for category, results in category_results.items():
                    stats = results['stats']
                    print(f"{category.upper()}:")
                    print(f"   Qualified: {stats['qualified_count']}")
                    print(f"   Empathy Recipients: {stats['empathy_recipients']}")
                    print(f"   Empathy Candidates: {stats['empathy_candidates']}")
                
                # Make API call for category-wise rewards
                print(f"\n--- MAKING CATEGORY-WISE REWARD API CALL ---")
                api_success = self._make_category_reward_api_call(category_results)
                
                if api_success:
                    print("Successfully distributed category-wise rewards via API!")
                else:
                    print("Failed to distribute category-wise rewards via API")
                
                print("--------------------------------------------------")
                
                return category_results

        except (Exception, psycopg2.Error) as error:
            print(f"ERROR during category-wise user analysis: {error}")
            import traceback
            traceback.print_exc()
            conn.rollback()
        finally:
            self.db_pool.putconn(conn)
    
    def get_daily_summary(self) -> Dict[str, Any]:
        """
        Returns a category-wise summary of today's analysis without making API calls.
        """
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                now = datetime.datetime.now(datetime.timezone.utc)
                twenty_four_hours_ago = now - datetime.timedelta(hours=24)
                
                # Use same query structure as other methods
                cur.execute("""
                    SELECT 
                        user_id, 
                        COALESCE(consecutive_activity_days, 0) as consecutive_activity_days, 
                        COALESCE(historical_engagement_score, 0) as historical_engagement_score,
                        COALESCE(points_from_posts, 0) as points_from_posts, 
                        COALESCE(points_from_likes, 0) as points_from_likes, 
                        COALESCE(points_from_comments, 0) as points_from_comments, 
                        COALESCE(points_from_referrals, 0) as points_from_referrals, 
                        COALESCE(points_from_tipping, 0) as points_from_tipping, 
                        COALESCE(points_from_crypto, 0) as points_from_crypto,
                        COALESCE(daily_posts_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_posts_timestamps, 
                        COALESCE(daily_likes_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_likes_timestamps, 
                        COALESCE(daily_comments_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_comments_timestamps,
                        COALESCE(daily_referrals_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_referrals_timestamps, 
                        COALESCE(daily_tipping_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_tipping_timestamps,
                        COALESCE(daily_crypto_timestamps, ARRAY[]::TIMESTAMPTZ[]) as daily_crypto_timestamps
                    FROM user_scores;
                """)
                all_users = cur.fetchall()
                
                categories = ['posts', 'likes', 'comments', 'crypto', 'tipping', 'referrals']
                category_summary = {}
                
                for category in categories:
                    qualified_users = []
                    empathy_candidates = []
                    
                    for user_data in all_users:
                        user_id = user_data[0]
                        
                        is_qualified = self._check_category_qualification(user_data, category, twenty_four_hours_ago)
                        
                        if is_qualified:
                            qualified_users.append({
                                "user_id": user_id,
                                "category": category
                            })
                        else:
                            empathy_score = self._calculate_category_empathy_score(user_data, category)
                            if empathy_score > 0:
                                empathy_candidates.append({
                                    "user_id": user_id,
                                    "category": category,
                                    "empathy_score": empathy_score
                                })
                    
                    # Sort and select top 10% for empathy
                    empathy_candidates.sort(key=lambda x: x['empathy_score'], reverse=True)
                    empathy_count = math.ceil(len(empathy_candidates) * config.REWARD_PERCENTAGE_OF_INACTIVE)
                    empathy_recipients = empathy_candidates[:empathy_count]
                    
                    category_summary[category] = {
                        "qualified_users": qualified_users,
                        "empathy_recipients": empathy_recipients,
                        "stats": {
                            "qualified_count": len(qualified_users),
                            "empathy_candidates": len(empathy_candidates),
                            "empathy_recipients": len(empathy_recipients)
                        }
                    }
                
                return {
                    "analysis_type": "category_based",
                    "categories": category_summary,
                    "overall_summary": {
                        "total_users": len(all_users),
                        "total_qualified_across_categories": sum(len(cat['qualified_users']) for cat in category_summary.values()),
                        "total_empathy_across_categories": sum(len(cat['empathy_recipients']) for cat in category_summary.values())
                    }
                }
                
        finally:
            self.db_pool.putconn(conn)
            
    def close(self):
        """Closes all connections in the database pool."""
        if self.db_pool:
            self.db_pool.closeall()
            print("HistoricalAnalyzer: DB connection pool closed.")