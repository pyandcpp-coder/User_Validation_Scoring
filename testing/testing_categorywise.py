#!/usr/bin/env python3
"""
Test script for the new category-wise qualification system.
This script tests the new feature where users can qualify for rewards in individual categories.
"""

import requests
import json
import time

# Configuration
API_BASE_URL = "http://localhost:8000"
TEST_USERS = [
    "0x1111111111111111111111111111111111111111",  # User 1 - Will qualify for posts only
    "0x2222222222222222222222222222222222222222",  # User 2 - Will qualify for likes only  
    "0x3333333333333333333333333333333333333333",  # User 3 - Will qualify for crypto only
    "0x4444444444444444444444444444444444444444",  # User 4 - Will qualify for multiple categories
    "0x5555555555555555555555555555555555555555",  # User 5 - Will not qualify for any (empathy candidate)
]

def create_test_activities():
    """Create diverse activities to test category-wise qualification."""
    print("🎯 Creating Test Activities for Category-wise Analysis...")
    
    # User 1: Qualify for POSTS only (2 posts, but insufficient likes/comments/crypto)
    print(f"\n--- User 1: Post Qualification Test ---")
    for i in range(2):  # Meets POST_LIMIT_DAY = 2
        response = create_post(TEST_USERS[0], f"Quality post content {i+1} from user 1")
        print(f"   Post {i+1}: {response.get('status', 'unknown')}")
    
    # Add 1 like (insufficient for LIKE_LIMIT_DAY = 5)
    response = create_like(TEST_USERS[0])
    print(f"   Like 1: {response.get('status', 'unknown')}")
    
    # User 2: Qualify for LIKES only (5 likes, but insufficient posts/comments/crypto)
    print(f"\n--- User 2: Like Qualification Test ---")
    for i in range(5):  # Meets LIKE_LIMIT_DAY = 5
        response = create_like(TEST_USERS[1])
        print(f"   Like {i+1}: {response.get('status', 'unknown')}")
    
    # Add 1 post (insufficient for POST_LIMIT_DAY = 2)
    response = create_post(TEST_USERS[1], "Single post from user 2")
    print(f"   Post 1: {response.get('status', 'unknown')}")
    
    # User 3: Qualify for CRYPTO only (3 crypto interactions)
    print(f"\n--- User 3: Crypto Qualification Test ---")
    for i in range(3):  # Meets CRYPTO_LIMIT_DAY = 3
        response = create_crypto(TEST_USERS[2], f"BTC_TRADE_{i+1}")
        print(f"   Crypto {i+1}: {response.get('status', 'unknown')}")
    
    # Add insufficient activities for other categories
    response = create_like(TEST_USERS[2])
    print(f"   Like 1: {response.get('status', 'unknown')}")
    
    # User 4: Qualify for MULTIPLE categories (posts, likes, comments)
    print(f"\n--- User 4: Multiple Category Qualification Test ---")
    
    # 2 posts (meets POST_LIMIT_DAY)
    for i in range(2):
        response = create_post(TEST_USERS[3], f"Multi-category post {i+1} from user 4")
        print(f"   Post {i+1}: {response.get('status', 'unknown')}")
    
    # 5 likes (meets LIKE_LIMIT_DAY)
    for i in range(5):
        response = create_like(TEST_USERS[3])
        print(f"   Like {i+1}: {response.get('status', 'unknown')}")
    
    # 5 comments (meets COMMENT_LIMIT_DAY)
    for i in range(5):
        response = create_comment(TEST_USERS[3], f"Insightful comment {i+1}")
        print(f"   Comment {i+1}: {response.get('status', 'unknown')}")
    
    # User 5: Qualify for NOTHING (empathy candidate with some historical activity)
    print(f"\n--- User 5: Empathy Candidate Test ---")
    
    # Just 1 post (insufficient for qualification but shows some activity)
    response = create_post(TEST_USERS[4], "Single post from potential empathy user")
    print(f"   Post 1: {response.get('status', 'unknown')}")
    
    # 2 likes (insufficient for qualification)
    for i in range(2):
        response = create_like(TEST_USERS[4])
        print(f"   Like {i+1}: {response.get('status', 'unknown')}")

def create_post(user_wallet, content):
    """Create a post for testing."""
    try:
        # Note: This creates a simple text post without image
        post_data = {
            "creatorAddress": user_wallet,
            "interactorAddress": user_wallet,
            "interactionType": "post",
            "data": content,
            "webhookUrl": "https://httpbin.org/post"  # Test webhook
        }
        
        response = requests.post(
            f"{API_BASE_URL}/v1/submit_post",
            data=post_data,
            timeout=10
        )
        
        return {"status": "success" if response.status_code == 202 else "failed"}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

def create_like(user_wallet):
    """Create a like interaction."""
    try:
        like_request = {
            "creatorAddress": "0x9999999999999999999999999999999999999999",  # Some other user
            "interactorAddress": user_wallet,
            "Interaction": {
                "interactionType": "like",
                "data": "post_123"
            }
        }
        
        response = requests.post(
            f"{API_BASE_URL}/v1/submit_action",
            json=like_request,
            timeout=5
        )
        
        return {"status": "success" if response.status_code == 200 else "failed"}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

def create_comment(user_wallet, content):
    """Create a comment interaction."""
    try:
        comment_request = {
            "creatorAddress": "0x9999999999999999999999999999999999999999",  # Some other user
            "interactorAddress": user_wallet,
            "Interaction": {
                "interactionType": "comment",
                "data": content
            },
            "webhookUrl": "https://httpbin.org/post"
        }
        
        response = requests.post(
            f"{API_BASE_URL}/v1/submit_action",
            json=comment_request,
            timeout=5
        )
        
        return {"status": "success" if response.status_code in [200, 202] else "failed"}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

def create_crypto(user_wallet, transaction_data):
    """Create a crypto interaction."""
    try:
        crypto_request = {
            "creatorAddress": user_wallet,
            "interactorAddress": user_wallet,
            "Interaction": {
                "interactionType": "crypto",
                "data": transaction_data
            }
        }
        
        response = requests.post(
            f"{API_BASE_URL}/v1/submit_action",
            json=crypto_request,
            timeout=5
        )
        
        return {"status": "success" if response.status_code == 200 else "failed"}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

def run_category_analysis():
    """Run the category-wise daily analysis."""
    print("\n🔍 Running Category-wise Daily Analysis...")
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/admin/run-daily-analysis",
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Category-wise analysis completed successfully!")
            
            if "results" in result:
                print("\n📊 CATEGORY-WISE RESULTS:")
                for category, data in result["results"].items():
                    qualified_count = len(data.get("qualified", []))
                    empathy_count = len(data.get("empathy", []))
                    
                    print(f"\n{category.upper()}:")
                    print(f"   Qualified Users: {qualified_count}")
                    if qualified_count > 0:
                        for user in data.get("qualified", []):
                            print(f"      ✅ {user}")
                    
                    print(f"   Empathy Recipients: {empathy_count}")
                    if empathy_count > 0:
                        for user in data.get("empathy", []):
                            print(f"      💝 {user}")
            
            return True
        else:
            print(f"❌ Analysis failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error running analysis: {e}")
        return False

def check_user_category_status():
    """Check category-wise status for each test user."""
    print("\n👥 Checking Individual User Category Status...")
    
    for i, user_wallet in enumerate(TEST_USERS):
        print(f"\n--- User {i+1}: {user_wallet} ---")
        
        try:
            response = requests.get(
                f"{API_BASE_URL}/admin/user-activity/{user_wallet}",
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if "category_breakdown" in result:
                    category_breakdown = result["category_breakdown"]
                    qualified_categories = result.get("summary", {}).get("qualified_categories", [])
                    
                    print(f"   Qualified Categories: {qualified_categories}")
                    print(f"   Final Score: {result.get('summary', {}).get('final_score', 0)}")
                    
                    print(f"   Category Details:")
                    for category, status in category_breakdown.items():
                        activity = status.get("activity_today", 0)
                        required = status.get("required_for_qualification", 0)
                        qualified = status.get("qualified", False)
                        status_icon = "✅" if qualified else "❌"
                        
                        print(f"      {category}: {status_icon} {activity}/{required} (Qualified: {qualified})")
                
            else:
                print(f"   ❌ Failed to get user data: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

def get_category_summary():
    """Get overall category summary."""
    print("\n📋 Getting Category Summary...")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/admin/category-summary",
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Category summary retrieved!")
            
            categories = result.get("categories", {})
            for category, info in categories.items():
                print(f"\n{category.upper()}:")
                print(f"   Name: {info.get('name')}")
                print(f"   Daily Requirement: {info.get('daily_requirement')}")
                print(f"   Point Value: {info.get('point_value')}")
            
            empathy_config = result.get("empathy_config", {})
            print(f"\nEmpathy Configuration:")
            print(f"   Percentage Selected: {empathy_config.get('percentage_selected', 0)*100}%")
            
        else:
            print(f"❌ Failed to get category summary: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Run the complete category-wise qualification test."""
    print("🚀 Starting Category-wise Qualification System Test")
    print("=" * 70)
    
    # Step 1: Create test activities
    create_test_activities()
    
    # Step 2: Wait a moment for processing
    print("\n⏳ Waiting for background processing...")
    time.sleep(3)
    
    # Step 3: Run category analysis
    run_category_analysis()
    
    # Step 4: Check individual user status
    check_user_category_status()
    
    # Step 5: Get category summary
    get_category_summary()
    
    print("\n" + "=" * 70)
    print("🏁 Category-wise qualification testing complete!")
    print("\nExpected Results:")
    print("   User 1: Qualified for POSTS only")
    print("   User 2: Qualified for LIKES only")
    print("   User 3: Qualified for CRYPTO only")
    print("   User 4: Qualified for POSTS, LIKES, and COMMENTS")
    print("   User 5: Not qualified for any category (empathy candidate)")

if __name__ == "__main__":
    main()