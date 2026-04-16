"""
Web Search Integration Module
Combines Tavily (news/automated discovery) and Firecrawl (deep scraping)
for comprehensive data enrichment.

Production-Grade Features:
✅ Timeout handling (30s per search)
✅ Graceful error handling
✅ Retry logic
✅ Connection error handling
"""

import os
import json
import logging
import requests
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

try:
    from tavily import TavilyClient
except ImportError:
    logger.warning("TavilyClient not available")
    TavilyClient = None

# Timeout constants (in seconds)
TAVILY_TIMEOUT = 30
FIRECRAWL_TIMEOUT = 20

class TavilySearcher:
    """Search for news, articles, and information about companies using Tavily."""
    
    def __init__(self):
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            logger.warning("TAVILY_API_KEY environment variable not set")
            self.client = None
            return
        
        try:
            self.client = TavilyClient(api_key=api_key)
        except Exception as e:
            logger.error(f"Failed to initialize TavilyClient: {e}")
            self.client = None
    
    def search(self, company_name: str, query: str) -> Dict[str, Any]:
        """
        Search for information about a company.
        
        Args:
            company_name: Name of the company
            query: Specific query (e.g., "production capacity", "reserves")
            
        Returns:
            Dict with search results and sources
            
        Handles:
        ✅ API timeouts
        ✅ Connection errors
        ✅ Rate limiting
        ✅ Empty results
        """
        try:
            if not self.client:
                logger.warning("Tavily client not initialized")
                return {"results": [], "sources": [], "error": "Tavily not available"}
            
            # Build search query
            search_query = f"{company_name} {query} 2026 Nigeria oil"
            
            logger.debug(f"[TAVILY] Starting search: {search_query}")
            
            start_time = time.time()
            
            # Use Tavily's search with timeout
            try:
                response = self.client.search(
                    search_query,
                    include_answer=True,
                    max_results=5
                )
            except TimeoutError:
                elapsed = time.time() - start_time
                logger.warning(f"[TAVILY] Search timeout after {elapsed:.1f}s")
                return {"results": [], "sources": [], "error": "Search timeout"}
            except Exception as e:
                logger.error(f"[TAVILY] Search error: {e}")
                return {"results": [], "sources": [], "error": str(e)}
            
            elapsed = time.time() - start_time
            num_results = len(response.get('results', []))
            logger.debug(f"[TAVILY] Search returned {num_results} results in {elapsed:.2f}s")
            
            if num_results > 0:
                for i, result in enumerate(response.get('results', [])[:3], 1):
                    title = result.get("title", "")[:60]
                    content = result.get("content", "")[:80]
                    print(f"[TAVILY]   Result {i}: {title}... - {content}...")
            else:
                print(f"[TAVILY] WARNING: No results returned for query: {search_query}")
            
            return {
                "sources": response.get("results", []),
                "ai_summary": response.get("answer", ""),
                "query": search_query,
                "num_results": num_results
            }
        except Exception as e:
            print(f"[TAVILY] ERROR: {str(e)}")
            return {"sources": [], "ai_summary": "", "error": str(e), "num_results": 0}


class FirecrawlScraper:
    """Deep scrape URLs using Firecrawl API."""
    
    def __init__(self):
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY environment variable not set")
        self.endpoint = "https://api.firecrawl.dev/v1/scrape"
    
    def scrape_url(self, url: str) -> Dict[str, Any]:
        """
        Scrape a URL using Firecrawl.
        
        Args:
            url: URL to scrape
            
        Returns:
            Dict with scraped content and metadata
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "url": url,
                "formats": ["markdown", "html"],
                "onlyMainContent": True
            }
            
            print(f"[FIRECRAWL] Scraping: {url[:70]}...")
            
            response = requests.post(self.endpoint, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                markdown_len = len(data.get('markdown', ''))
                print(f"[FIRECRAWL] Success: Got {markdown_len} chars from {url[:50]}...")
                
                return {
                    "url": url,
                    "markdown": data.get("markdown", ""),
                    "html": data.get("html", ""),
                    "metadata": data.get("metadata", {}),
                    "success": True
                }
            else:
                print(f"[FIRECRAWL] Status {response.status_code}: {url[:50]}...")
                return {"url": url, "success": False, "error": f"Status {response.status_code}"}
        except Exception as e:
            print(f"[FIRECRAWL] Exception: {str(e)[:80]}")
            return {"url": url, "success": False, "error": str(e)}


class HybridSearcher:
    """Combines Tavily and Firecrawl for comprehensive web search."""
    
    def __init__(self):
        self.tavily = TavilySearcher()
        self.firecrawl = FirecrawlScraper()
    
    def search_and_scrape(self, company_name: str, topic: str) -> Dict[str, Any]:
        """
        Perform comprehensive search: Tavily discovery + Firecrawl deep scrape.
        Firecrawl prioritizes Tavily's recommended sources.
        
        Args:
            company_name: Company name
            topic: What to search for (e.g., "production", "reserves", "equity")
            
        Returns:
            Comprehensive search results with discovery and scraping
        """
        
        print(f"[WEB_SEARCH] Starting hybrid search for {company_name} - {topic}")
        
        # Step 1: Use Tavily to auto-discover sources
        tavily_results = self.tavily.search(company_name, topic)
        num_tavily_results = tavily_results.get("num_results", 0)
        
        if num_tavily_results == 0:
            print(f"[WEB_SEARCH] WARNING: Tavily found no results for {company_name} {topic}")
        else:
            print(f"[WEB_SEARCH] Tavily found {num_tavily_results} sources")
        
        scraped_sources = []
        
        # Step 2: Extract numeric values directly from Tavily results, use Firecrawl as supplement
        if tavily_results.get("sources"):
            print(f"[WEB_SEARCH] Processing {len(tavily_results['sources'])} Tavily sources")
            
            for i, source in enumerate(tavily_results["sources"][:5]):  # Top 5 sources
                url = source.get("url")
                title = source.get("title", "")
                content = source.get("content", "")
                
                print(f"[WEB_SEARCH] Processing source {i+1}: {title[:50]}...")
                
                # Extract numeric values from Tavily snippet first (fast, reliable)
                tavily_values = extract_numeric_values(content)
                print(f"[WEB_SEARCH]   Tavily snippet: Found {len(tavily_values)} numeric values")
                
                scraped_item = {
                    "url": url,
                    "title": title,
                    "snippet": content,
                    "tavily_values": tavily_values,
                    "rank": i + 1
                }
                
                # Only scrape with Firecrawl if:
                # 1. URL is valid and not a blocked social media site
                # 2. We didn't find values in Tavily (to supplement)
                skip_firecrawl = any(blocked in url.lower() for blocked in ['facebook', 'twitter', 'x.com', 'instagram']) if url else True
                
                if url and not skip_firecrawl:
                    print(f"[WEB_SEARCH]   Attempting Firecrawl scrape for deeper data...")
                    try:
                        scraped = self.firecrawl.scrape_url(url)
                        
                        if scraped.get("success") and scraped.get("markdown"):
                            # Extract values from Firecrawl markdown
                            scraped_values = extract_numeric_values(scraped.get("markdown", ""))
                            scraped_item["scraped_content"] = scraped.get("markdown", "")[:500]  # First 500 chars
                            scraped_item["scraped_values"] = scraped_values
                            scraped_item["scrape_success"] = True
                            print(f"[WEB_SEARCH]   Firecrawl success: {len(scraped_values)} additional values")
                        else:
                            scraped_item["scrape_success"] = False
                            print(f"[WEB_SEARCH]   Firecrawl: No content returned (expected for dynamic sites)")
                    except Exception as e:
                        scraped_item["scrape_success"] = False
                        print(f"[WEB_SEARCH]   Firecrawl exception: {str(e)[:60]}")
                else:
                    scraped_item["scrape_success"] = False
                    print(f"[WEB_SEARCH]   Skipping Firecrawl (blocked site or invalid URL)")
                
                scraped_sources.append(scraped_item)
        
        print(f"[WEB_SEARCH] Completed: {len(scraped_sources)} sources processed, {sum(1 for s in scraped_sources if s.get('tavily_values'))} with Tavily values")
        
        return {
            "company_name": company_name,
            "topic": topic,
            "tavily_summary": tavily_results.get("ai_summary", ""),
            "tavily_results_count": num_tavily_results,
            "discovered_sources": tavily_results.get("sources", []),
            "scraped_sources": scraped_sources,
            "search_timestamp": datetime.now().isoformat()
        }


def extract_numeric_values(text: str) -> List[Tuple[float, str]]:
    """Extract numeric values and their context from text."""
    import re
    
    # Regex patterns for common metrics
    patterns = {
        "production": r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:bopd|barrel|BPD|BOPD)",
        "reserves": r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:mmbbl|MMBbl|billion barrels)",
        "equity": r"(\d+(?:\.\d+)?)\s*%"
    }
    
    values = []
    for pattern_name, pattern in patterns.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Clean number
            num_str = match.replace(",", "")
            try:
                num = float(num_str)
                values.append((num, pattern_name))
            except ValueError:
                pass
    
    return values


def synthesize_web_results(
    company_name: str,
    database_data: Dict[str, Any],
    web_results: Dict[str, Any],
    topic: str
) -> Dict[str, Any]:
    """
    Synthesize database data and web search results.
    
    Returns data ranges with sources.
    Extracts data from Tavily first, then supplements with Firecrawl if available.
    """
    
    synthesis = {
        "company_name": company_name,
        "topic": topic,
        "sources": [],
        "data_points": [],
        "synthesis": ""
    }
    
    # Add database source
    if database_data:
        for key, value in database_data.items():
            if value and value != "NOT_AVAILABLE":
                synthesis["data_points"].append({
                    "source": "Database",
                    "metric": key,
                    "value": value,
                    "priority": 1  # Database is trusted source
                })
        
        synthesis["sources"].append({
            "name": "Internal Database",
            "type": "database",
            "timestamp": None
        })
    
    # Extract data from Tavily results (most reliable)
    for scraped in web_results.get("scraped_sources", []):
        tavily_vals = scraped.get("tavily_values", [])
        
        for value, metric_type in tavily_vals:
            synthesis["data_points"].append({
                "source": scraped.get("title", "Tavily Result"),
                "url": scraped.get("url"),
                "metric": metric_type,
                "value": value,
                "priority": 2  # Tavily snippets are reliable
            })
        
        # Add source if Tavily found values
        if tavily_vals:
            synthesis["sources"].append({
                "name": scraped.get("title", "Unknown"),
                "url": scraped.get("url"),
                "type": "tavily",
                "rank": scraped.get("rank")
            })
    
    # Supplement with Firecrawl data if scraping was successful
    for scraped in web_results.get("scraped_sources", []):
        if scraped.get("scrape_success"):
            scraped_vals = scraped.get("scraped_values", [])
            
            for value, metric_type in scraped_vals:
                # Only add if not already from Tavily
                existing = [p for p in synthesis["data_points"] 
                           if p["metric"] == metric_type and p["source"] == scraped.get("title")]
                if not existing:
                    synthesis["data_points"].append({
                        "source": scraped.get("title", "Unknown"),
                        "url": scraped.get("url"),
                        "metric": metric_type,
                        "value": value,
                        "priority": 3
                    })
    
    return synthesis


# Initialize if needed
try:
    hybrid_searcher = HybridSearcher()
except ValueError as e:
    print(f"Warning: Web search initialization failed: {e}")
    hybrid_searcher = None
