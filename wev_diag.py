# weaviate_diagnostics.py
import weaviate
import os
from weaviate.classes.query import Filter
import traceback

def run_weaviate_diagnostics():
    """Complete diagnostic of Weaviate client methods and capabilities"""
    
    print("=" * 80)
    print("WEAVIATE DIAGNOSTICS")
    print("=" * 80)
    
    # Connect to Weaviate
    db_host = os.getenv("WEAVIATE_HOST", "localhost")
    try:
        client = weaviate.connect_to_custom(
            http_host=db_host,
            http_port=int(os.getenv("WEAVIATE_PORT", 8080)),
            http_secure=False,
            grpc_host=db_host,
            grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", 50051)),
            grpc_secure=False
        )
        print(f"✅ Connected to Weaviate at {db_host}")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return
    
    # Get Weaviate version info
    print("\n" + "=" * 40)
    print("CLIENT VERSION INFO")
    print("=" * 40)
    print(f"Weaviate client version: {weaviate.__version__}")
    
    # Get collection
    try:
        posts_collection = client.collections.get("Post")
        print(f"✅ Got 'Post' collection")
        print(f"Collection type: {type(posts_collection)}")
        print(f"Collection class name: {posts_collection.__class__.__name__}")
    except Exception as e:
        print(f"❌ Failed to get collection: {e}")
        return
    
    # Examine query object
    print("\n" + "=" * 40)
    print("QUERY OBJECT ANALYSIS")
    print("=" * 40)
    query_obj = posts_collection.query
    print(f"Query object type: {type(query_obj)}")
    print(f"Query object class: {query_obj.__class__.__name__}")
    
    # List all methods of query object
    print("\n" + "=" * 40)
    print("AVAILABLE QUERY METHODS")
    print("=" * 40)
    methods = [m for m in dir(query_obj) if not m.startswith('_')]
    for method in sorted(methods):
        print(f"  - {method}")
    
    # Try different query approaches
    print("\n" + "=" * 40)
    print("TESTING QUERY METHODS")
    print("=" * 40)
    
    # Test 1: Basic fetch_objects
    print("\n1. Testing basic fetch_objects():")
    try:
        result = posts_collection.query.fetch_objects(limit=2)
        print(f"   ✅ Success! Retrieved {len(result.objects)} objects")
        if result.objects:
            print(f"   First object properties: {result.objects[0].properties.keys()}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Test 2: Check if bm25 method exists
    print("\n2. Checking for bm25 method:")
    if hasattr(query_obj, 'bm25'):
        print("   ✅ bm25 method exists")
        try:
            # Try BM25 search with properties filter
            result = posts_collection.query.bm25(
                query="1234",
                query_properties=["post_id"],
                limit=1
            )
            print(f"   ✅ BM25 search worked")
        except Exception as e:
            print(f"   ❌ BM25 search failed: {e}")
    else:
        print("   ❌ bm25 method not found")
    
    # Test 3: Check for near_text method
    print("\n3. Checking for near_text method:")
    if hasattr(query_obj, 'near_text'):
        print("   ✅ near_text method exists")
    else:
        print("   ❌ near_text method not found")
    
    # Test 4: Try to filter using different approaches
    print("\n4. Testing filter approaches:")
    
    # Approach A: Check if there's a filter method
    if hasattr(posts_collection, 'filter'):
        print("   Testing collection.filter():")
        try:
            result = posts_collection.filter(
                Filter.by_property("post_id").equal("1234")
            ).objects()
            print(f"   ✅ Filter on collection worked")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    # Approach B: Check data.fetch_objects (instead of query)
    if hasattr(posts_collection, 'data'):
        print("\n   Testing collection.data methods:")
        data_methods = [m for m in dir(posts_collection.data) if not m.startswith('_')]
        print(f"   Available data methods: {', '.join(data_methods[:10])}")
    
    # Test 5: Try aggregate to get all posts with specific properties
    print("\n5. Testing aggregate methods:")
    if hasattr(posts_collection, 'aggregate'):
        try:
            agg_result = posts_collection.aggregate.over_all(
                group_by="user_id",
                total_count=True
            )
            print(f"   ✅ Aggregate worked")
        except Exception as e:
            print(f"   ❌ Aggregate failed: {e}")
    
    # Test 6: Inspect fetch_objects signature
    print("\n6. Inspecting fetch_objects signature:")
    import inspect
    try:
        sig = inspect.signature(posts_collection.query.fetch_objects)
        print(f"   Parameters: {list(sig.parameters.keys())}")
        for param_name, param in sig.parameters.items():
            print(f"   - {param_name}: {param.annotation if param.annotation != inspect.Parameter.empty else 'Any'}")
    except Exception as e:
        print(f"   ❌ Could not inspect: {e}")
    
    # Test 7: Try to get specific post using different methods
    print("\n" + "=" * 40)
    print("FINDING SPECIFIC POST (post_id='1234')")
    print("=" * 40)
    
    # Method 1: Using BM25 if available
    if hasattr(query_obj, 'bm25'):
        print("\nMethod 1: Using BM25 search:")
        try:
            result = posts_collection.query.bm25(
                query="1234",
                query_properties=["post_id"],
                limit=5
            )
            print(f"   Found {len(result.objects)} objects")
            for obj in result.objects:
                if obj.properties.get("post_id") == "1234":
                    print(f"   ✅ Found post with UUID: {obj.uuid}")
                    print(f"   Properties: {obj.properties}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    # Method 2: Get all and filter in Python
    print("\nMethod 2: Fetch all and filter in Python:")
    try:
        all_posts = posts_collection.query.fetch_objects(limit=100)
        matching_posts = [
            obj for obj in all_posts.objects 
            if obj.properties.get("post_id") == "1234" and 
               obj.properties.get("user_id") == "1234567"
        ]
        if matching_posts:
            print(f"   ✅ Found {len(matching_posts)} matching posts")
            print(f"   First match UUID: {matching_posts[0].uuid}")
            print(f"   Properties: {matching_posts[0].properties}")
        else:
            print("   ❌ No matching posts found")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Clean up
    client.close()
    print("\n" + "=" * 80)
    print("DIAGNOSTICS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    run_weaviate_diagnostics()