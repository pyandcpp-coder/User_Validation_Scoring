#!/usr/bin/env python3
"""
Robust Database Cleanup Script - Handles connection issues properly
Run this script to reset all data before testing.

Usage: python robust_cleanup.py
"""

import os
import sys
import psycopg2
import traceback
import warnings
import time

# Suppress resource warnings temporarily
warnings.filterwarnings("ignore", category=ResourceWarning)

def cleanup_postgresql():
    """Clean all data from PostgreSQL database."""
    print("🗑️  Cleaning PostgreSQL database...")
    
    connection = None
    try:
        # Connect to PostgreSQL using the same config as your app
        db_host = os.getenv("POSTGRES_HOST", "localhost")
        connection = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "scoring_db"),
            user=os.getenv("POSTGRES_USER", "scoring_user"),
            password=os.getenv("POSTGRES_PASSWORD", "scoring_password"),
            host=db_host,
            port=os.getenv("POSTGRES_PORT", "5432")
        )
        
        with connection.cursor() as cursor:
            # Check if user_scores table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'user_scores'
                );
            """)
            table_exists = cursor.fetchone()[0]
            
            if table_exists:
                # Get count before deletion
                cursor.execute("SELECT COUNT(*) FROM user_scores;")
                record_count = cursor.fetchone()[0]
                print(f"   Found {record_count} records in user_scores table")
                
                # Delete all records
                cursor.execute("DELETE FROM user_scores;")
                print(f"   ✅ Deleted all {record_count} records from user_scores table")
                
                # Reset any auto-increment sequences (if they exist)
                cursor.execute("""
                    SELECT sequence_name FROM information_schema.sequences 
                    WHERE sequence_schema = 'public';
                """)
                sequences = cursor.fetchall()
                
                for seq in sequences:
                    cursor.execute(f"ALTER SEQUENCE {seq[0]} RESTART WITH 1;")
                    print(f"   ✅ Reset sequence {seq[0]}")
                
            else:
                print("   ⚠️  user_scores table does not exist - nothing to clean")
        
        connection.commit()
        print("   ✅ PostgreSQL cleanup completed successfully")
        return True
        
    except psycopg2.Error as e:
        print(f"   ❌ PostgreSQL Error: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error cleaning PostgreSQL: {e}")
        return False
    finally:
        if connection:
            connection.close()

def cleanup_weaviate_simple():
    """Clean Weaviate using simple HTTP requests to avoid connection issues."""
    print("🗑️  Cleaning Weaviate database...")
    
    try:
        import requests
        
        weaviate_host = os.getenv("WEAVIATE_HOST", "localhost")
        weaviate_port = int(os.getenv("WEAVIATE_PORT", 8080))
        base_url = f"http://{weaviate_host}:{weaviate_port}"
        
        print(f"   Connecting to Weaviate at {base_url}")
        
        # First, check if Weaviate is accessible
        try:
            response = requests.get(f"{base_url}/v1/meta", timeout=5)
            if response.status_code != 200:
                print(f"   ❌ Weaviate not accessible (HTTP {response.status_code})")
                return False
            print("   ✅ Weaviate is accessible")
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Cannot connect to Weaviate: {e}")
            return False
        
        # Check if Post collection exists
        try:
            response = requests.get(f"{base_url}/v1/schema/Post", timeout=5)
            if response.status_code == 200:
                collection_data = response.json()
                print("   Found Post collection")
                
                # Get object count
                try:
                    count_response = requests.get(
                        f"{base_url}/v1/objects",
                        params={"class": "Post", "limit": 1},
                        timeout=10
                    )
                    if count_response.status_code == 200:
                        objects = count_response.json().get("objects", [])
                        print(f"   Found objects in Post collection")
                    
                    # Delete the entire Post collection/schema
                    delete_response = requests.delete(f"{base_url}/v1/schema/Post", timeout=10)
                    if delete_response.status_code in [200, 204]:
                        print("   ✅ Deleted Post collection successfully")
                    else:
                        print(f"   ⚠️  Delete response: HTTP {delete_response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    print(f"   ⚠️  Could not get object count: {e}")
                    # Try to delete anyway
                    delete_response = requests.delete(f"{base_url}/v1/schema/Post", timeout=10)
                    if delete_response.status_code in [200, 204]:
                        print("   ✅ Deleted Post collection successfully")
                
            elif response.status_code == 404:
                print("   ✅ Post collection does not exist - nothing to clean")
            else:
                print(f"   ⚠️  Unexpected response checking Post collection: HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Error checking/deleting Post collection: {e}")
            return False
        
        print("   ✅ Weaviate cleanup completed successfully")
        return True
        
    except ImportError:
        print("   ⚠️  requests library not available")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error cleaning Weaviate: {e}")
        print(f"   Traceback: {traceback.format_exc()}")
        return False

def cleanup_redis():
    """Clean Redis cache (Celery broker/backend)."""
    print("🗑️  Cleaning Redis database...")
    
    redis_client = None
    try:
        import redis
        
        # Connect to Redis using default settings
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        
        redis_client = redis.Redis(host=redis_host, port=redis_port, db=0, socket_timeout=5)
        
        # Test connection
        redis_client.ping()
        
        # Get key count before deletion
        key_count = redis_client.dbsize()
        print(f"   Found {key_count} keys in Redis database")
        
        if key_count > 0:
            # Flush all keys in the current database
            redis_client.flushdb()
            print(f"   ✅ Deleted all {key_count} keys from Redis database")
        else:
            print(f"   ✅ Redis database is already empty")
        
        return True
        
    except ImportError:
        print("   ⚠️  Redis library not installed - skipping Redis cleanup")
        print("   Install with: pip install redis")
        return True  # Not a critical failure
    except redis.exceptions.ConnectionError as e:
        print(f"   ❌ Cannot connect to Redis: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Error cleaning Redis: {e}")
        return False
    finally:
        if redis_client:
            try:
                redis_client.close()
            except:
                pass

def cleanup_temp_files():
    """Clean temporary uploaded files."""
    print("🗑️  Cleaning temporary files...")
    
    try:
        upload_folder = "uploads"
        cleaned_count = 0
        
        if os.path.exists(upload_folder):
            import glob
            files = glob.glob(os.path.join(upload_folder, "*"))
            file_count = len(files)
            
            for file_path in files:
                try:
                    os.remove(file_path)
                    cleaned_count += 1
                except Exception as e:
                    print(f"   ⚠️  Could not remove {file_path}: {e}")
            
            print(f"   ✅ Cleaned {cleaned_count} temporary files from {upload_folder}/")
        else:
            print(f"   ⚠️  Upload folder '{upload_folder}' does not exist")
        
        # Also clean test image if it exists
        test_image = "test_post_image.png"
        if os.path.exists(test_image):
            os.remove(test_image)
            print(f"   ✅ Removed test image: {test_image}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error cleaning temporary files: {e}")
        return False

def main():
    """Main cleanup function."""
    print("🧹 Robust Database Cleanup")
    print("=" * 60)
    
    # Track success of each cleanup operation
    results = {
        "postgresql": cleanup_postgresql(),
        "weaviate": cleanup_weaviate_simple(), 
        "redis": cleanup_redis(),
        "temp_files": cleanup_temp_files()
    }
    
    print("=" * 60)
    print("📊 Cleanup Summary:")
    
    all_success = True
    for service, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"   {service.upper()}: {status}")
        if not success:
            all_success = False
    
    if all_success:
        print("\n🎉 All cleanup operations completed successfully!")
        print("   Your databases are now clean and ready for testing.")
    else:
        print("\n⚠️  Some cleanup operations failed.")
        print("   Check the error messages above for details.")
        
        # Provide manual alternatives for failed services
        if not results["weaviate"]:
            print("\n   Manual Weaviate reset options:")
            print("   1. Restart Weaviate service/container")
            print("   2. Use: curl -X DELETE http://localhost:8080/v1/schema")
        
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error during cleanup: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)