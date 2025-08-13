#!/usr/bin/env python3
"""
Test script for the new category-specific reward endpoints.
Tests each category endpoint individually.
"""

import requests
import json

# Configuration
API_BASE_URL = "http://localhost:8000"

def test_category_endpoint(category):
    """Test a specific category endpoint."""
    print(f"\n🎯 Testing {category.upper()} Category Endpoint...")
    
    try:
        response = requests.get(f"{API_BASE_URL}/api/rewards/{category}", timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ {category.capitalize()} endpoint successful!")
            
            print(f"   Daily Requirement: {result.get('daily_requirement', 'unknown')}")
            print(f"   Qualified Users: {result.get('stats', {}).get('qualified_count', 0)}")
            print(f"   Empathy Users: {result.get('stats', {}).get('empathy_count', 0)}")
            
            # Show some qualified users (first 3)
            qualified = result.get('qualified_users', [])
            if qualified:
                print(f"   Qualified Examples: {qualified[:3]}")
            
            # Show some empathy users (first 3)
            empathy = result.get('empathy_users', [])
            if empathy:
                print(f"   Empathy Examples: {empathy[:3]}")
                
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_generic_endpoint():
    """Test the generic /api/rewards/{category} endpoint."""
    print(f"\n🔧 Testing Generic Category Endpoint...")
    
    # Test valid category
    try:
        response = requests.get(f"{API_BASE_URL}/api/rewards/posts", timeout=10)
        if response.status_code == 200:
            print("✅ Generic endpoint works for valid category!")
        else:
            print("❌ Generic endpoint failed for valid category")
    except Exception as e:
        print(f"❌ Error testing generic endpoint: {e}")
    
    # Test invalid category
    try:
        response = requests.get(f"{API_BASE_URL}/api/rewards/invalid", timeout=10)
        if response.status_code == 400:
            print("✅ Generic endpoint correctly rejects invalid category!")
        else:
            print("❌ Generic endpoint should reject invalid categories")
    except Exception as e:
        print(f"❌ Error testing invalid category: {e}")

def test_all_categories_endpoint():
    """Test the /api/rewards/all endpoint."""
    print(f"\n📊 Testing All Categories Endpoint...")
    
    try:
        response = requests.get(f"{API_BASE_URL}/api/rewards/all", timeout=15)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ All categories endpoint successful!")
            
            categories = result.get('categories', {})
            summary = result.get('summary', {})
            
            print(f"   Categories Found: {len(categories)}")
            print(f"   Total Qualified: {summary.get('total_qualified_across_categories', 0)}")
            print(f"   Total Empathy: {summary.get('total_empathy_across_categories', 0)}")
            
            # Show breakdown by category
            for cat_name, cat_data in categories.items():
                print(f"   {cat_name}: {cat_data.get('qualified_count', 0)} qualified, {cat_data.get('empathy_count', 0)} empathy")
                
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def compare_with_old_endpoint():
    """Compare results with the old combined endpoint."""
    print(f"\n🔄 Comparing with Old Admin Endpoint...")
    
    try:
        # Get old endpoint data
        old_response = requests.get(f"{API_BASE_URL}/admin/daily-summary", timeout=10)
        
        if old_response.status_code == 200:
            old_result = old_response.json()
            old_categories = old_result.get('data', {}).get('categories', {})
            
            print("✅ Old endpoint working - comparing results...")
            
            # Compare each category
            categories = ['posts', 'likes', 'comments', 'crypto', 'tipping', 'referrals']
            for category in categories:
                new_response = requests.get(f"{API_BASE_URL}/api/rewards/{category}", timeout=5)
                
                if new_response.status_code == 200:
                    new_result = new_response.json()
                    old_data = old_categories.get(category, {}).get('stats', {})
                    
                    old_qualified = old_data.get('qualified_count', 0)
                    new_qualified = new_result.get('stats', {}).get('qualified_count', 0)
                    
                    match_icon = "✅" if old_qualified == new_qualified else "⚠️"
                    print(f"   {category}: {match_icon} Old: {old_qualified}, New: {new_qualified}")
                else:
                    print(f"   {category}: ❌ New endpoint failed")
                    
        else:
            print("❌ Old endpoint not working - cannot compare")
            
    except Exception as e:
        print(f"❌ Error comparing endpoints: {e}")

def main():
    """Run all category endpoint tests."""
    print("🚀 Testing Category-Specific Reward Endpoints")
    print("=" * 60)
    
    # Test individual category endpoints
    categories = ['posts', 'likes', 'comments', 'crypto', 'tipping', 'referrals']
    success_count = 0
    
    for category in categories:
        if test_category_endpoint(category):
            success_count += 1
    
    # Test generic endpoint
    test_generic_endpoint()
    
    # Test all categories endpoint
    test_all_categories_endpoint()
    
    # Compare with old endpoint
    compare_with_old_endpoint()
    
    print("\n" + "=" * 60)
    print(f"🏁 Testing Complete! {success_count}/{len(categories)} category endpoints working")
    
    print("\n📋 Available Endpoints:")
    for category in categories:
        print(f"   GET /api/rewards/{category}")
    print(f"   GET /api/rewards/all")
    print(f"   GET /api/rewards/{{category}} (generic)")

if __name__ == "__main__":
    main()