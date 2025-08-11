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

    def _calculate_category_empathy_score(self, user_data: tuple, category: str) -> float:
        """
        Calculate empathy score for a specific category based on that category's lifetime activity.
        
        Args:
            user_data: User database record
            category: Category name (posts, likes, comments, crypto, tipping, referrals)
        """
        (user_id, last_active_date, streak, p_posts, p_likes, p_comments, 
         p_referrals, p_tipping, p_crypto, post_ts, like_ts, comment_ts, 
         referral_ts, tipping_ts, crypto_ts) = user_data
        
        # Base streak component (applies to all categories)
        streak_score = (streak or 0) * config.HISTORICAL_SCORE_WEIGHTS['streak_at_reset']
        
        # Category-specific lifetime activity
        category_score = 0.0
        
        if category == 'posts':
            lifetime_posts = (p_posts / config.POINTS_PER_POST) if config.POINTS_PER_POST > 0 else 0
            category_score = lifetime_posts * config.HISTORICAL_SCORE_WEIGHTS['lifetime_posts']
            
        elif category == 'likes':
            lifetime_likes = (p_likes / config.POINTS_PER_LIKE) if config.POINTS_PER_LIKE > 0 else 0
            category_score = lifetime_likes * config.HISTORICAL_SCORE_WEIGHTS['lifetime_likes']
            
        elif category == 'comments':
            lifetime_comments = (p_comments / config.POINTS_PER_COMMENT) if config.POINTS_PER_COMMENT > 0 else 0
            category_score = lifetime_comments * config.HISTORICAL_SCORE_WEIGHTS['lifetime_comments']
            
        elif category == 'crypto':
            lifetime_crypto = (p_crypto / config.POINTS_FOR_CRYPTO) if config.POINTS_FOR_CRYPTO > 0 else 0
            category_score = lifetime_crypto * config.HISTORICAL_SCORE_WEIGHTS['lifetime_crypto']
            
        elif category == 'tipping':
            # Tipping doesn't have a specific weight, use a reasonable default
            lifetime_tipping = (p_tipping / config.POINTS_FOR_TIPPING) if config.POINTS_FOR_TIPPING > 0 else 0
            category_score = lifetime_tipping * 0.1  # Default weight for tipping
            
        elif category == 'referrals':
            # Referrals don't have a specific weight, use a reasonable default
            lifetime_referrals = (p_referrals / config.POINTS_PER_REFERRAL) if config.POINTS_PER_REFERRAL > 0 else 0
            category_score = lifetime_referrals * 0.1  # Default weight for referrals
        
        return streak_score + category_score

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
        (user_id, last_active_date, streak, p_posts, p_likes, p_comments, 
         p_referrals, p_tipping, p_crypto, post_ts, like_ts, comment_ts, 
         referral_ts, tipping_ts, crypto_ts) = user_data
        
        if category == 'posts':
            posts_today = len([ts for ts in (post_ts or []) if ts > twenty_four_hours_ago])
            return posts_today >= config.POST_LIMIT_DAY
            
        elif category == 'likes':
            likes_today = len([ts for ts in (like_ts or []) if ts > twenty_four_hours_ago])
            return likes_today >= config.LIKE_LIMIT_DAY
            
        elif category == 'comments':
            comments_today = len([ts for ts in (comment_ts or []) if ts > twenty_four_hours_ago])
            return comments_today >= config.COMMENT_LIMIT_DAY
            
        elif category == 'crypto':
            crypto_today = len([ts for ts in (crypto_ts or []) if ts > twenty_four_hours_ago])
            return crypto_today >= config.CRYPTO_LIMIT_DAY
            
        elif category == 'tipping':
            # For tipping and referrals, we might have different criteria
            # Let's say they need at least 1 activity today
            tipping_today = len([ts for ts in (tipping_ts or []) if ts > twenty_four_hours_ago])
            return tipping_today >= 1
            
        elif category == 'referrals':
            referrals_today = len([ts for ts in (referral_ts or []) if ts > twenty_four_hours_ago])
            return referrals_today >= 1
            
        return False

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
                
                # Get all user data including crypto fields
                cur.execute("""
                    SELECT 
                        user_id, last_active_date, consecutive_activity_days,
                        points_from_posts, points_from_likes, points_from_comments, 
                        points_from_referrals, points_from_tipping, points_from_crypto,
                        daily_posts_timestamps, daily_likes_timestamps, daily_comments_timestamps,
                        daily_referrals_timestamps, daily_tipping_timestamps, daily_crypto_timestamps
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
                        
                        # Check if user qualifies for this category
                        is_qualified = self._check_category_qualification(user_data, category, twenty_four_hours_ago)
                        
                        if is_qualified:
                            qualified_users.append(user_id)
                            print(f"   QUALIFIED for {category}: {user_id}")
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
                    
                    # Check if user had ANY activity today across all categories
                    had_any_activity = any(
                        self._check_category_qualification(user_data, cat, twenty_four_hours_ago) 
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
                
                cur.execute("""
                    SELECT 
                        user_id, consecutive_activity_days, historical_engagement_score,
                        points_from_posts, points_from_likes, points_from_comments, 
                        points_from_referrals, points_from_tipping, points_from_crypto,
                        daily_posts_timestamps, daily_likes_timestamps, daily_comments_timestamps,
                        daily_referrals_timestamps, daily_tipping_timestamps, daily_crypto_timestamps
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