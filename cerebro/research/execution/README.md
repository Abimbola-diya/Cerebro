Step 2 bridge

This module converts Step 1 planner output into retrieval tasks.
It is intentionally a bridge, not the full crawler or temp-db layer.

Planned next layers:
- Execute search tasks against Tavily/Serper
- Execute scrape tasks against Firecrawl
- Stage normalized documents into a temporary store
- Feed grouped evidence to the synthesis LLM