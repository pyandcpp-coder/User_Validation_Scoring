#!/usr/bin/env python3
"""
Simple test script to check the category-wise status of the test users.
This will help verify that the admin endpoints are working correctly.
"""

import requests
import json

# Configuration
API_BASE_URL = "http://localhost:8000"

# The users from your test
TEST_USERS = [
    "0x1111111111111111111111111111111111111111",  # User 1
    "0x2222222222222222222222222222222222222222",  # User 2  
    "0x3333333333333333333333333333333333333333",  # User 3
    "0x4444444444444444444444444444444444444444",  # User 4
    "0x5555555555555555555555555555555555555555",  # User 5
]

def test_category_summary():
    """Test the category summary endpoint."""
    print("📋 Testing Category Summary Endpoint...")
    
    try:
        response = requests.get(f"{API_BASE_URL}/admin/category-summary", timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Category summary successful!")
            print(f"Analysis Type: {result.get('analysis_type')}")
            
            categories = result.get('categories', {})
            print(f"\nFound {len(categories)} categories:")
            for cat_name, cat_info in categories.items():
                print(f"  {cat_name}: {cat_info.get('daily_requirement')} required/day")
                
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_user_activity(user_id):
    """Test user activity for a specific user."""
    print(f"\n👤 Testing User Activity for {user_id}...")
    
    try:
        response = requests.get(f"{API_BASE_URL}/admin/user-activity/{user_id}", timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ User activity retrieved successfully!")
            
            summary = result.get('summary', {})
            print(f"Final Score: {summary.get('final_score', 0)}")
            print(f"Qualified Categories: {summary.get('qualified_categories', [])}")
            
            category_breakdown = result.get('category_breakdown', {})
            print(f"Category Breakdown:")
            for cat, status in category_breakdown.items():
                activity = status.get('activity_today', 0)
                required = status.get('required_for_qualification', 0)
                qualified = status.get('qualified', False)
                status_icon = "✅" if qualified else "❌"
                print(f"  {cat}: {status_icon} {activity}/{required}")
                
        elif response.status_code == 404:
            print("❌ User not found in database")
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_daily_summary():
    """Test the daily summary endpoint."""
    print("\n📊 Testing Daily Summary Endpoint...")
    
    try:
        response = requests.get(f"{API_BASE_URL}/admin/daily-summary", timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Daily summary retrieved successfully!")
            
            data = result.get('data', {})
            overall = data.get('overall_summary', {})
            
            print(f"Total Users: {overall.get('total_users', 0)}")
            print(f"Total Qualified (across categories): {overall.get('total_qualified_across_categories', 0)}")
            print(f"Total Empathy (across categories): {overall.get('total_empathy_across_categories', 0)}")
            
            categories = data.get('categories', {})
            for cat_name, cat_data in categories.items():
                stats = cat_data.get('stats', {})
                print(f"\n{cat_name.upper()}:")
                print(f"  Qualified: {stats.get('qualified_count', 0)}")
                print(f"  Empathy: {stats.get('empathy_recipients', 0)}")
                
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Run simple tests for the category system."""
    print("🧪 Simple Category System Test")
    print("=" * 50)
    
    # Test 1: Category Summary
    test_category_summary()
    
    # Test 2: Daily Summary
    test_daily_summary()
    
    # Test 3: Individual User Activity (test a few users)
    for i, user in enumerate(TEST_USERS[:3]):  # Test first 3 users
        test_user_activity(user)
    
    print("\n" + "=" * 50)
    print("🏁 Simple testing complete!")

if __name__ == "__main__":
    main()