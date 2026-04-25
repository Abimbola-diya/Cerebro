"""LangChain tool adapters for Cerebro research agents."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from cerebro.research.contracts.enums import DimensionKey
from cerebro.research.errors import PlannerError

from .tools import CrawlbaseTool, FirecrawlTool, SerperTool, TavilyTool


@tool("tavily_search")
async def tavily_search_tool(query: str, topic: str = "general", include_domains: list[str] | None = None) -> str:
    """Search the web through Tavily and return raw JSON as a string."""
    result = await TavilyTool().search(query=query, topic=topic, include_domains=include_domains)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool("serper_search")
async def serper_search_tool(query: str, gl: str = "ng", hl: str = "en") -> str:
    """Search the web through Serper and return raw JSON as a string."""
    result = await SerperTool().search(query=query, gl=gl, hl=hl)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool("firecrawl_scrape")
async def firecrawl_scrape_tool(url: str, **payload: Any) -> str:
    """Scrape a URL through Firecrawl and return raw JSON as a string."""
    result = await FirecrawlTool().scrape(url=url, **payload)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool("crawlbase_scrape")
async def crawlbase_scrape_tool(url: str, javascript: bool = False, **payload: Any) -> str:
    """Scrape a URL through Crawlbase and return raw JSON as a string."""
    result = await CrawlbaseTool().scrape(url=url, javascript=javascript, **payload)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool("firecrawl_search")
async def firecrawl_search_tool(query: str, limit: int = 5, **payload: Any) -> str:
    """Search through Firecrawl and return raw JSON as a string."""
    result = await FirecrawlTool().search(query=query, limit=limit, **payload)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool("firecrawl_interact")
async def firecrawl_interact_tool(url: str, prompt: str, **payload: Any) -> str:
    """Interact with a webpage through Firecrawl and return raw JSON as a string."""
    result = await FirecrawlTool().interact(url=url, prompt=prompt, **payload)
    return json.dumps(result, ensure_ascii=False, default=str)


def build_tools_for_dimension(dimension: DimensionKey) -> list[Any]:
    if dimension in {DimensionKey.FINANCIAL, DimensionKey.EXPERT, DimensionKey.NEWS, DimensionKey.ASSOCIATIONS}:
        return [tavily_search_tool, crawlbase_scrape_tool, firecrawl_interact_tool]
    if dimension in {DimensionKey.REGULATORY, DimensionKey.MARKET, DimensionKey.INTERNATIONAL}:
        return [serper_search_tool, crawlbase_scrape_tool, firecrawl_interact_tool]
    raise PlannerError(f"Unsupported dimension for tools: {dimension.value}")
