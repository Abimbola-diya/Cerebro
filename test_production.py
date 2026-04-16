#!/usr/bin/env python3
"""
Production-Grade Test Suite for Cerebro AI Backend
Tests various query types, edge cases, and error conditions
"""

import requests
import json
import time
import sys
from typing import Dict, List, Any

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

class TestRunner:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.results = []
    
    def test_health(self) -> bool:
        """Test 1: API Health Check"""
        print(f"\n{BLUE}TEST 1: API Health Check{RESET}")
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            assert r.status_code == 200, f"Status {r.status_code}"
            data = r.json()
            assert data["status"] == "ok"
            print(f"{GREEN}✅ PASS: API is healthy{RESET}")
            self.tests_passed += 1
            return True
        except Exception as e:
            print(f"{RED}❌ FAIL: {e}{RESET}")
            self.tests_failed += 1
            return False
    
    def test_query(self, query: str, test_name: str, expect_success: bool = True) -> bool:
        """Generic query test"""
        print(f"\n{BLUE}TEST: {test_name}{RESET}")
        print(f"Query: '{query}'")
        self.tests_run += 1
        
        try:
            start = time.time()
            r = requests.post(
                f"{self.base_url}/api/ask",
                json={"query": query},
                timeout=120
            )
            elapsed = time.time() - start
            
            assert r.status_code in [200, 400, 422], f"HTTP {r.status_code}"
            
            data = r.json()
            answer = data.get("answer", "")
            
            # Length validation
            assert len(answer) > 10, "Answer too short"
            
            # Check for error patterns
            if expect_success:
                assert "error" not in answer.lower() or "Error" not in answer, "Answer contains error"
                print(f"{GREEN}✅ PASS ({elapsed:.1f}s): {answer[:80]}...{RESET}")
                self.tests_passed += 1
                self.results.append({"test": test_name, "status": "PASS", "time_s": elapsed})
                return True
            else:
                print(f"{YELLOW}✓ HANDLED GRACEFULLY ({elapsed:.1f}s): {answer[:80]}...{RESET}")
                self.tests_passed += 1
                return True
        
        except AssertionError as ae:
            print(f"{RED}❌ FAIL: {ae}{RESET}")
            self.tests_failed += 1
            self.results.append({"test": test_name, "status": "FAIL", "error": str(ae)})
            return False
        except Exception as e:
            print(f"{RED}❌ ERROR: {e}{RESET}")
            self.tests_failed += 1
            self.results.append({"test": test_name, "status": "ERROR", "error": str(e)})
            return False
    
    def test_input_validation(self) -> None:
        """Test 2-5: Input Validation"""
        print(f"\n{BLUE}CATEGORY: Input Validation{RESET}")
        
        # Empty query
        print(f"\n{BLUE}TEST 2: Empty Query{RESET}")
        r = requests.post(f"{self.base_url}/api/ask", json={"query": ""}, timeout=5)
        if r.status_code == 422:
            print(f"{GREEN}✅ PASS: Empty query rejected{RESET}")
            self.tests_passed += 1
        else:
            print(f"{RED}❌ FAIL: Expected 422, got {r.status_code}{RESET}")
            self.tests_failed += 1
        
        # Whitespace-only query
        print(f"\n{BLUE}TEST 3: Whitespace-Only Query{RESET}")
        r = requests.post(f"{self.base_url}/api/ask", json={"query": "   "}, timeout=5)
        if r.status_code == 422:
            print(f"{GREEN}✅ PASS: Whitespace query rejected{RESET}")
            self.tests_passed += 1
        else:
            print(f"{RED}❌ FAIL: Expected 422, got {r.status_code}{RESET}")
            self.tests_failed += 1
        
        # Too short
        print(f"\n{BLUE}TEST 4: Too Short Query{RESET}")
        r = requests.post(f"{self.base_url}/api/ask", json={"query": "AB"}, timeout=5)
        if r.status_code == 422:
            print(f"{GREEN}✅ PASS: Short query rejected{RESET}")
            self.tests_passed += 1
        else:
            print(f"{RED}❌ FAIL: Expected 422, got {r.status_code}{RESET}")
            self.tests_failed += 1
        
        # Special characters (should be handled gracefully)
        print(f"\n{BLUE}TEST 5: Special Characters{RESET}")
        r = requests.post(
            f"{self.base_url}/api/ask",
            json={"query": "Tell me about Shell <>&\"'"},
            timeout=120
        )
        if r.status_code in [200, 422]:
            print(f"{GREEN}✅ PASS: Special chars handled{RESET}")
            self.tests_passed += 1
        else:
            print(f"{RED}❌ FAIL: Status {r.status_code}{RESET}")
            self.tests_failed += 1
    
    def test_entity_queries(self) -> None:
        """Test 6-10: Single Entity Queries"""
        print(f"\n{BLUE}CATEGORY: Single Entity Queries{RESET}")
        
        self.test_query("Tell me about NNPC", "TEST 6: Exact Name Match")
        self.test_query("What is Shell Nigeria?", "TEST 7: Company with Descriptive Query")
        self.test_query("Mobil Producing information", "TEST 8: Short Name Variant")
        self.test_query("Tell me everything about Chevron Nigeria", "TEST 9: Multi-word Company")
        self.test_query("Who is Addax Petroleum?", "TEST 10: Alternative Company")
    
    def test_block_queries(self) -> None:
        """Test 11-13: Block-Related Queries"""
        print(f"\n{BLUE}CATEGORY: Block Queries{RESET}")
        
        self.test_query("What blocks does NNPC have?", "TEST 11: OML Blocks Query")
        self.test_query("How many oml blocks does Shell hold?", "TEST 12: Block Count Query")
        self.test_query("Which blocks are operated by Total?", "TEST 13: Block Operator Query")
    
    def test_production_queries(self) -> None:
        """Test 14-16: Production Data Queries"""
        print(f"\n{BLUE}CATEGORY: Production Queries{RESET}")
        
        self.test_query("What is the current production of NNPC?", "TEST 14: Production Capacity")
        self.test_query("How much oil does Shell produce?", "TEST 15: Production Rate")
        self.test_query("Tell me about Chevron's production", "TEST 16: Production Context")
    
    def test_aggregation_queries(self) -> None:
        """Test 17-19: Aggregation/Comparative Queries"""
        print(f"\n{BLUE}CATEGORY: Aggregation Queries{RESET}")
        
        self.test_query("Which company has the largest production?", "TEST 17: Largest Producer")
        self.test_query("Rank companies by production capacity", "TEST 18: Production Ranking")
        self.test_query("What is the average production?", "TEST 19: Average Calculation")
    
    def test_edge_cases(self) -> None:
        """Test 20-24: Edge Cases & Error Handling"""
        print(f"\n{BLUE}CATEGORY: Edge Cases{RESET}")
        
        self.test_query("Typo: Tell me about Shel Nigeria", "TEST 20: Typo Tolerance")
        self.test_query("tell me about nnpc in lowercase", "TEST 21: Case Insensitivity")
        self.test_query("Non-existent company XYZABC Corp", "TEST 22: Non-existent Entity", expect_success=False)
        self.test_query("What about NNPC? And Shell? And Chevron?", "TEST 23: Multiple Entities", expect_success=False)
        self.test_query("Update all companies set production=1000", "TEST 24: Injection Attack Attempt", expect_success=False)
    
    def test_follow_up_queries(self) -> None:
        """Test 25-26: Session/Follow-up Queries"""
        print(f"\n{BLUE}CATEGORY: Follow-up Queries{RESET}")
        
        # Get session from first query
        print(f"\n{BLUE}TEST 25: First Query (Setup){RESET}")
        r = requests.post(f"{self.base_url}/api/ask", json={"query": "Tell me about NNPC"}, timeout=120)
        if r.status_code == 200:
            session_id = r.json().get("session_id")
            print(f"{GREEN}✅ Got session: {session_id}{RESET}")
            
            # Follow-up with same session
            print(f"\n{BLUE}TEST 26: Follow-up Query (Same Session){RESET}")
            r2 = requests.post(
                f"{self.base_url}/api/ask",
                json={"query": "What blocks do they have?", "session_id": session_id},
                timeout=120
            )
            if r2.status_code == 200 and len(r2.json().get("answer", "")) > 10:
                print(f"{GREEN}✅ PASS: Follow-up processed{RESET}")
                self.tests_passed += 1
            else:
                print(f"{RED}❌ FAIL: Follow-up failed{RESET}")
                self.tests_failed += 1
        else:
            print(f"{RED}❌ FAIL: First query failed{RESET}")
            self.tests_failed += 1
    
    def test_list_entities(self) -> None:
        """Test 27: List Entities Endpoint"""
        print(f"\n{BLUE}TEST 27: List Entities Endpoint{RESET}")
        self.tests_run += 1
        try:
            r = requests.get(f"{self.base_url}/api/entities", timeout=10)
            assert r.status_code == 200
            data = r.json()
            count = data.get("count", 0)
            assert count > 0, "No entities returned"
            print(f"{GREEN}✅ PASS: {count} entities listed{RESET}")
            self.tests_passed += 1
        except Exception as e:
            print(f"{RED}❌ FAIL: {e}{RESET}")
            self.tests_failed += 1
    
    def test_search_endpoint(self) -> None:
        """Test 28: Search Endpoint"""
        print(f"\n{BLUE}TEST 28: Search Endpoint{RESET}")
        self.tests_run += 1
        try:
            r = requests.get(f"{self.base_url}/api/search?query=shell", timeout=10)
            assert r.status_code == 200
            data = r.json()
            results = data.get("results", [])
            assert len(results) > 0, "No search results"
            print(f"{GREEN}✅ PASS: Found {len(results)} matches for 'shell'{RESET}")
            self.tests_passed += 1
        except Exception as e:
            print(f"{RED}❌ FAIL: {e}{RESET}")
            self.tests_failed += 1
    
    def run_all(self) -> None:
        """Run complete test suite"""
        print(f"\n{YELLOW}{'='*60}")
        print(f"CEREBRO AI BACKEND - PRODUCTION TEST SUITE")
        print(f"{'='*60}{RESET}\n")
        
        # Basic tests
        self.test_health()
        self.test_input_validation()
        
        # Functional tests
        self.test_entity_queries()
        self.test_block_queries()
        self.test_production_queries()
        self.test_aggregation_queries()
        
        # Edge cases
        self.test_edge_cases()
        self.test_follow_up_queries()
        
        # Endpoint tests
        self.test_list_entities()
        self.test_search_endpoint()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self) -> None:
        """Print test summary"""
        total = self.tests_passed + self.tests_failed
        pct = (self.tests_passed / total * 100) if total > 0 else 0
        
        print(f"\n{YELLOW}{'='*60}")
        print(f"TEST SUMMARY")
        print(f"{'='*60}{RESET}")
        print(f"Total Tests: {total}")
        print(f"{GREEN}Passed: {self.tests_passed}{RESET}")
        print(f"{RED}Failed: {self.tests_failed}{RESET}")
        print(f"Success Rate: {pct:.1f}%")
        
        if self.tests_failed == 0:
            print(f"\n{GREEN}{'🎉 ALL TESTS PASSED!'}{RESET}")
            sys.exit(0)
        else:
            print(f"\n{RED}{self.tests_failed} test(s) failed{RESET}")
            sys.exit(1)

if __name__ == "__main__":
    runner = TestRunner()
    runner.run_all()
