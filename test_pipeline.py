#!/usr/bin/env python3
"""
Test script for Cerebro MVP Backend
Tests database connectivity and basic pipeline flow
"""

import os
import sys

# Add the cerebro_backend directory to path
sys.path.insert(0, '/home/abimbola/Desktop/Cerebro/cerebro_backend')

print("=" * 60)
print("CEREBRO MVP BACKEND - TEST SCRIPT")
print("=" * 60)

# Test 1: Database connectivity
print("\n[TEST 1] Database Connectivity")
print("-" * 60)
try:
    from database import db
    db.connect()
    print("✅ Connected to Neo4j Aura")
except Exception as e:
    print(f"❌ Failed to connect: {e}")
    sys.exit(1)

# Test 2: Query all entities
print("\n[TEST 2] Query All Entities (Step 3)")
print("-" * 60)
try:
    entities = db.query_all_entities()
    print(f"✅ Found {len(entities)} entities")
    print(f"   Sample: {entities[0]['name']}")
except Exception as e:
    print(f"❌ Failed to query entities: {e}")
    sys.exit(1)

# Test 3: Search entities
print("\n[TEST 3] Search Entities (Step 4)")
print("-" * 60)
try:
    results = db.search_entities_by_keyword("NNPC")
    print(f"✅ Found {len(results)} matches for 'NNPC'")
    if results:
        print(f"   Match: {results[0]['name']}")
except Exception as e:
    print(f"❌ Failed to search: {e}")
    sys.exit(1)

# Test 4: Discover properties
print("\n[TEST 4] Discover Properties (Step 5)")
print("-" * 60)
try:
    if results:
        entity_id = results[0]['id']
        properties = db.discover_properties(entity_id)
        print(f"✅ Found {len(properties)} properties on {entity_id}")
        print(f"   Properties: {', '.join(list(properties.keys())[:5])}...")
except Exception as e:
    print(f"❌ Failed to discover properties: {e}")
    sys.exit(1)

# Test 5: Retrieve data
print("\n[TEST 5] Retrieve Entity Data (Step 7)")
print("-" * 60)
try:
    if results and properties:
        relevant_props = list(properties.keys())[:5]
        data = db.retrieve_entity_data(entity_id, relevant_props)
        print(f"✅ Retrieved data for {len(data)} properties")
        for key, value in list(data.items())[:3]:
            print(f"   {key}: {value}")
except Exception as e:
    print(f"❌ Failed to retrieve data: {e}")
    sys.exit(1)

# Test 6: Session management
print("\n[TEST 6] Session Management")
print("-" * 60)
try:
    from session import session_manager
    session_id = "test-session-123"
    session = session_manager.get_session(session_id)
    print(f"✅ Created session: {session_id}")
    
    session_manager.set_current_entity(session_id, entity_id, results[0]['name'])
    current = session_manager.get_current_entity(session_id)
    print(f"✅ Set current entity: {current['name']}")
    
    session_manager.add_message(session_id, "user", "Tell me about this company")
    history = session_manager.get_conversation_history(session_id)
    print(f"✅ Stored message, history length: {len(history)}")
except Exception as e:
    print(f"❌ Failed session test: {e}")
    sys.exit(1)

# Test 7: LLM initialization check
print("\n[TEST 7] LLM Pipeline Initialization")
print("-" * 60)
try:
    # Optional token for local test; never hardcode secrets in source.
    os.environ["GITHUB_TOKEN"] = os.getenv("GITHUB_TOKEN", "")
    
    # Force reimport
    import importlib
    import llm
    importlib.reload(llm)
    
    if llm.llm_pipeline:
        print("✅ LLM Pipeline initialized successfully")
    else:
        print("⚠️  LLM Pipeline not available (this is OK if GitHub token issues)")
except Exception as e:
    print(f"⚠️  LLM Pipeline initialization issue: {e}")

# Summary
print("\n" + "=" * 60)
print("✅ ALL CORE TESTS PASSED")
print("=" * 60)
print("\nPipeline is ready to use!")
print("Key modules working:")
print("  ✅ Neo4j Database Driver")
print("  ✅ Entity Queries (A, B, C)")
print("  ✅ Session Management")
print("  ✅ LLM Pipeline (when GitHub token is available)")

db.close()
