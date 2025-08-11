#!/usr/bin/env python3
"""
Test script for crypto interactions in the scoring system.
Run this after implementing the crypto changes to test the functionality.
"""

import requests
import json
import time

# Configuration
API_BASE_URL = "http://localhost:8000"
TEST_USER_WALLET = "0x1234567890abcdef1234567890abcdef12345678"

def test_crypto_interaction():
    """Test a crypto interaction submission."""
    print("🪙 Testing Crypto Interaction...")
    
    crypto_request = {
        "creatorAddress": TEST_USER_WALLET,
        "interactorAddress": TEST_USER_WALLET,  # Same user doing crypto action
        "Interaction": {
            "interactionType": "crypto",
            "data": "BTC_TRADE_12345"  # Could be transaction ID, trade info, etc.
        }
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/submit_action",
            json=crypto_request,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            result = response.json()
            points = result.get("validation", {}).get("significanceScore", 0)
            final_score = result.get("validation", {}).get("finalUserScore", 0)
            print(f"✅ Crypto interaction successful!")
            print(f"   Points awarded: {points}")
            print(f"   Final user score: {final_score}")
        else:
            print(f"❌ Crypto interaction failed!")
            
    except Exception as e:
        print(f"❌ Error testing crypto interaction: {e}")

def test_multiple_crypto_interactions():
    """Test multiple crypto interactions to check daily limits."""
    print("\n Testing Multiple Crypto Interactions (Daily Limit Test)...")
    
    for i in range(15):  # Try to exceed daily limit of 10
        print(f"   Crypto interaction #{i+1}")
        
        crypto_request = {
            "creatorAddress": TEST_USER_WALLET,
            "interactorAddress": TEST_USER_WALLET,
            "Interaction": {
                "interactionType": "crypto",
                "data": f"ETH_STAKE_{i+1}"
            }
        }
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/v1/submit_action",
                json=crypto_request,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                points = result.get("validation", {}).get("significanceScore", 0)
                if points > 0:
                    print(f"      ✅ Awarded {points} points")
                else:
                    print(f"      🚫 Daily limit reached")
                    break
            else:
                print(f"      ❌ Failed: {response.status_code}")
                break
                
        except Exception as e:
            print(f"      ❌ Error: {e}")
            break
        
        time.sleep(0.5)  # Small delay between requests

def check_user_activity():
    """Check the user's activity summary including crypto."""
    print(f"\n📊 Checking User Activity for {TEST_USER_WALLET}...")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/admin/user-activity/{TEST_USER_WALLET}",
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ User activity retrieved successfully!")
            
            activity = result.get("activity_summary", {})
            scoring = result.get("scoring_details", {})
            
            print(f"   Today's Activities:")
            print(f"      Posts: {activity.get('posts_today', 0)}")
            print(f"      Likes: {activity.get('likes_today', 0)}")
            print(f"      Comments: {activity.get('comments_today', 0)}")
            print(f"      Crypto: {activity.get('crypto_today', 0)}")
            
            print(f"   Point Breakdown:")
            print(f"      From Posts: {scoring.get('points_from_posts', 0)}")
            print(f"      From Likes: {scoring.get('points_from_likes', 0)}")
            print(f"      From Comments: {scoring.get('points_from_comments', 0)}")
            print(f"      From Crypto: {scoring.get('points_from_crypto', 0)}")
            print(f"      Final Score: {scoring.get('final_score', 0)}")
            
        else:
            print(f"❌ Failed to get user activity: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error checking user activity: {e}")

def main():
    """Run all crypto tests."""
    print("🚀 Starting Crypto Interaction Tests...")
    print(f"Testing with user wallet: {TEST_USER_WALLET}")
    print("=" * 60)
    
    # Test single crypto interaction
    test_crypto_interaction()
    
    # Test multiple interactions to check limits
    test_multiple_crypto_interactions()
    
    # Check final user activity
    check_user_activity()
    
    print("\n" + "=" * 60)
    print("🏁 Crypto testing complete!")

if __name__ == "__main__":
    main()