'''
File: /home/mvayyat/work/my_ai_agents/src/components/job_fetcher.py
Project: /home/mvayyat/work/my_ai_agents/src/components
Created Date: Friday, June 19th, 2026
Author: mvayyat
-----
Last Modified: Friday, June 19th, 2026, 12:31:59 pm
Modified By: mvayyat at midhun.v@iiits.in
-----
Copyright (c) midhun.v@iiits.in

Job Fetcher — searches and retrieves job listings from LinkedIn
via the LinkedIn MCP Server (FastMCP streamable-http transport).

Protocol: JSON-RPC 2.0 over HTTP. The MCP server must be running
separately (e.g., `uv run -m linkedin_mcp_server --transport streamable-http`).

Usage:
    import asyncio
    from src.components.job_fetcher import JobFetcher

    async def main():
        async with JobFetcher() as fetcher:
            results = await fetcher.search_jobs(
                keywords="Software Engineer",
                location="Remote",
                max_pages=2,
            )
            print(results)

    asyncio.run(main())
'''

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MCP_HOST = os.getenv("LINKEDIN_MCP_HOST", "127.0.0.1")
DEFAULT_MCP_PORT = int(os.getenv("LINKEDIN_MCP_PORT", "8000"))
DEFAULT_MCP_PATH = os.getenv("LINKEDIN_MCP_PATH", "/mcp")
DEFAULT_REQUEST_TIMEOUT = float(os.getenv("LINKEDIN_MCP_TIMEOUT", "120.0"))


@dataclass
class JobListing:
    """A lightweight job listing returned from search results."""
    job_id: str
    title: str = ""
    company: str = ""
    location: str = ""
    url: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
        }


@dataclass
class JobSearchResult:
    """Container for job search results."""
    query_keywords: str
    query_location: Optional[str]
    total_results_estimate: int
    job_ids: List[str] = field(default_factory=list)
    listings: List[JobListing] = field(default_factory=list)
    raw_sections: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_keywords": self.query_keywords,
            "query_location": self.query_location,
            "total_results_estimate": self.total_results_estimate,
            "job_ids": self.job_ids,
            "listings": [j.to_dict() for j in self.listings],
        }


# ---------------------------------------------------------------------------
# MCP JSON-RPC Client
# ---------------------------------------------------------------------------

class LinkedInMCPClient:
    """Lightweight async JSON-RPC 2.0 client for the LinkedIn MCP Server.

    Connects to a running LinkedIn MCP Server via streamable-http transport.
    Implements the MCP handshake (initialize → session ID) and tool invocation
    (tools/call).

    The server must be started separately, e.g.:
        cd linkedin-mcp-server
        uv run -m linkedin_mcp_server --transport streamable-http
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
        protocol_version: str = "2025-03-26",
    ) -> None:
        self._base_url = (base_url or f"http://{DEFAULT_MCP_HOST}:{DEFAULT_MCP_PORT}").rstrip("/")
        self._timeout = timeout
        self._protocol_version = protocol_version
        self._session_id: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._next_id: int = 0

    async def __aenter__(self) -> "LinkedInMCPClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self) -> Dict[str, Any]:
        """Perform MCP initialize handshake and store the session ID."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)

        response = await self._client.post(
            self._endpoint(),
            json={
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": self._protocol_version,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "job-search-ai-agent",
                        "version": "0.1.0",
                    },
                },
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )

        self._next_id += 1

        # FastMCP returns SSE (text/event-stream), not raw JSON
        if "Mcp-Session-Id" in response.headers:
            self._session_id = response.headers["Mcp-Session-Id"]
            logger.info("MCP session established: %s", self._session_id)
        elif "mcp-session-id" in response.headers:
            self._session_id = response.headers["mcp-session-id"]
            logger.info("MCP session established: %s", self._session_id)
        else:
            logger.warning("No Mcp-Session-Id header in initialize response")

        return self._parse_sse_response(response.text)

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke an MCP tool by name with the given arguments.

        Args:
            tool_name: The registered MCP tool name (e.g., "search_jobs").
            arguments: Keyword arguments for the tool.

        Returns:
            Parsed JSON result from the tool.

        Raises:
            RuntimeError: If the client is not connected or the server returns an error.
        """
        if self._client is None:
            raise RuntimeError("MCP client not connected. Use as async context manager or call initialize().")

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        self._next_id += 1

        logger.debug("Calling tool '%s' with args: %s", tool_name, arguments)

        response = await self._client.post(
            self._endpoint(),
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

        # FastMCP returns SSE (text/event-stream), parse accordingly
        data = self._parse_sse_response(response.text)

        if "error" in data:
            error = data["error"]
            raise RuntimeError(
                f"MCP tool '{tool_name}' error [{error.get('code')}]: {error.get('message')}"
            )

        result = data.get("result", data)

        # FastMCP wraps tool results in MCP content format:
        #   {"content": [{"type": "text", "text": "{...json...}"}]}
        # Unwrap the inner JSON string if present.
        result = self._unwrap_mcp_content(result)

        return result

    # ------------------------------------------------------------------
    # SSE / MCP content helpers
    # ------------------------------------------------------------------

    _SSE_DATA_RE = re.compile(r"^data:\s*(.+)$", re.MULTILINE)

    @classmethod
    def _parse_sse_response(cls, text: str) -> Dict[str, Any]:
        """Parse a Server-Sent Events response from FastMCP into a JSON dict.

        FastMCP's streamable-http transport returns SSE format:
            event: message
            data: {"jsonrpc":"2.0","id":1,"result":{...}}

        Returns the parsed JSON object from the ``data:`` line.
        """
        match = cls._SSE_DATA_RE.search(text)
        if match:
            return json.loads(match.group(1))
        # Fallback: try raw JSON (some transports may return plain JSON)
        return json.loads(text)

    @staticmethod
    def _unwrap_mcp_content(result: Dict[str, Any]) -> Dict[str, Any]:
        """Unwrap FastMCP's content-wrapped tool results.

        FastMCP tool results arrive as:
            {"content": [{"type": "text", "text": '{"url":"...","sections":{...}}'}]}

        If the result has a ``content`` key with a list containing a ``text``
        field that is valid JSON, that inner JSON is returned.
        Otherwise the original result is returned unchanged.
        """
        content = result.get("content")
        if isinstance(content, list) and len(content) > 0:
            first = content[0]
            if isinstance(first, dict) and "text" in first:
                try:
                    inner = json.loads(first["text"])
                    if isinstance(inner, dict):
                        return inner
                except (json.JSONDecodeError, TypeError):
                    pass
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _endpoint(self) -> str:
        return urljoin(self._base_url, DEFAULT_MCP_PATH)

    @property
    def connected(self) -> bool:
        return self._session_id is not None


# ---------------------------------------------------------------------------
# Job Fetcher
# ---------------------------------------------------------------------------

class JobFetcher:
    """High-level async job fetching interface over LinkedIn MCP.

    Wraps LinkedInMCPClient with convenience methods for searching jobs,
    fetching details, and normalizing results into typed dataclasses.

    Usage::

        async with JobFetcher() as fetcher:
            result = await fetcher.search(
                keywords="Data Scientist",
                location="San Francisco",
                date_posted="past_week",
                work_type="remote",
                max_pages=2,
            )
            for job in result.listings:
                print(job.title, job.company)
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._client: LinkedInMCPClient | None = None

    async def __aenter__(self) -> "JobFetcher":
        self._client = LinkedInMCPClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.__aexit__(*args)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        keywords: str,
        location: str | None = None,
        max_pages: int = 3,
        date_posted: str | None = None,
        job_type: str | None = None,
        experience_level: str | None = None,
        work_type: str | None = None,
        easy_apply: bool = False,
        sort_by: str | None = None,
    ) -> JobSearchResult:
        """Search LinkedIn jobs and return structured results.

        Args:
            keywords: Search keywords (e.g., "software engineer").
            location: Location filter (e.g., "Remote", "San Francisco").
            max_pages: Max result pages (1-10, default 3).
            date_posted: Filter by date — past_hour, past_24_hours, past_week, past_month.
            job_type: Comma-separated — full_time, part_time, contract, temporary, volunteer, internship, other.
            experience_level: Comma-separated — internship, entry, associate, mid_senior, director, executive.
            work_type: Comma-separated — on_site, remote, hybrid.
            easy_apply: Only Easy Apply jobs.
            sort_by: "date" or "relevance".

        Returns:
            JobSearchResult with job_ids and parsed listings.
        """
        if self._client is None:
            raise RuntimeError("JobFetcher not connected. Use as async context manager.")

        args: Dict[str, Any] = {
            "keywords": keywords,
            "max_pages": max_pages,
        }
        if location:
            args["location"] = location
        if date_posted:
            args["date_posted"] = date_posted
        if job_type:
            args["job_type"] = job_type
        if experience_level:
            args["experience_level"] = experience_level
        if work_type:
            args["work_type"] = work_type
        if easy_apply:
            args["easy_apply"] = easy_apply
        if sort_by:
            args["sort_by"] = sort_by

        logger.info("Searching jobs: keywords='%s', location='%s'", keywords, location)

        raw_result = await self._client.call_tool("search_jobs", args)

        return self._parse_search_result(raw_result, keywords, location)

    async def get_details(self, job_id: str) -> Dict[str, Any]:
        """Fetch full details for a specific job posting.

        Args:
            job_id: LinkedIn job ID (e.g., "4252026496").

        Returns:
            Dict with url, sections (name → raw text), and optional references.
        """
        if self._client is None:
            raise RuntimeError("JobFetcher not connected.")

        logger.info("Fetching job details for: %s", job_id)

        return await self._client.call_tool("get_job_details", {"job_id": job_id})

    # ------------------------------------------------------------------
    # Recommended / Feed-based jobs (personalized, no keyword required)
    # ------------------------------------------------------------------

    async def scrape_recommended(
        self,
        location: str | None = None,
        max_pages: int = 2,
        date_posted: str | None = None,
        job_type: str | None = None,
        experience_level: str | None = None,
        work_type: str | None = None,
        easy_apply: bool = False,
        sort_by: str | None = None,
    ) -> JobSearchResult:
        """Scrape LinkedIn's personalized job recommendations (no keywords).

        Calls ``search_jobs`` with an empty keyword string, which LinkedIn
        interprets as "show curated/recommended jobs based on my profile."
        This returns the same jobs that appear in the "Jobs" tab and feed.

        Args:
            location: Optional location filter (e.g., "Remote", "San Francisco").
            max_pages: Max result pages to load (1-10, default 2).
            date_posted: Filter by date — past_hour, past_24_hours, past_week, past_month.
            job_type: Comma-separated — full_time, part_time, contract, temporary, etc.
            experience_level: Comma-separated — internship, entry, associate, mid_senior, etc.
            work_type: Comma-separated — on_site, remote, hybrid.
            easy_apply: Only Easy Apply jobs.
            sort_by: "date" or "relevance".

        Returns:
            JobSearchResult with recommended job listings.
        """
        return await self.search(
            keywords="",  # Empty keywords = recommended/curated view
            location=location,
            max_pages=max_pages,
            date_posted=date_posted,
            job_type=job_type,
            experience_level=experience_level,
            work_type=work_type,
            easy_apply=easy_apply,
            sort_by=sort_by,
        )

    async def scrape_feed(
        self,
        num_posts: int = 50,
    ) -> Dict[str, Any]:
        """Scrape the authenticated user's LinkedIn home feed.

        Uses the MCP ``get_feed`` tool to scrape the home feed, which
        includes job recommendation posts mixed with general content.
        Returns raw feed data — downstream components can filter for
        job-related posts.

        Args:
            num_posts: Number of feed posts to fetch (1-50, default 50).

        Returns:
            Dict with url, sections (feed raw text), and optional references.
        """
        if self._client is None:
            raise RuntimeError("JobFetcher not connected.")

        logger.info("Scraping LinkedIn feed (num_posts=%d)", num_posts)

        return await self._client.call_tool("get_feed", {"num_posts": num_posts})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_search_result(
        raw: Dict[str, Any],
        keywords: str,
        location: str | None,
    ) -> JobSearchResult:
        """Parse raw MCP search_jobs response into a JobSearchResult."""
        job_ids: List[str] = raw.get("job_ids", [])
        sections: Dict[str, str] = raw.get("sections", {})
        references = raw.get("references", {})
        url = raw.get("url", "")

        # Estimate total results from section text or job_id count
        total_estimate = len(job_ids)

        # Build listings from references when available
        listings: List[JobListing] = []
        if references:
            for section_name, refs in references.items():
                for ref in refs:
                    if ref.get("kind") == "job":
                        listings.append(JobListing(
                            job_id=str(ref.get("value", ref.get("url", ""))),
                            title=ref.get("text", ""),
                            url=ref.get("url", ""),
                        ))

        # Fallback: build listings from job_ids if references not populated
        if not listings and job_ids:
            for jid in job_ids:
                listings.append(JobListing(job_id=jid))

        # Try to extract company/location from section text
        if sections and listings:
            raw_text = " ".join(sections.values())
            # Simple heuristic: reconstruct from raw text if needed
            # The LLM/structured parser should handle this downstream

        return JobSearchResult(
            query_keywords=keywords,
            query_location=location,
            total_results_estimate=total_estimate,
            job_ids=job_ids,
            listings=listings,
            raw_sections=sections,
        )


# ---------------------------------------------------------------------------
# Synchronous convenience wrapper
# ---------------------------------------------------------------------------

class SyncJobFetcher:
    """Synchronous wrapper around JobFetcher for non-async contexts.

    Usage::

        fetcher = SyncJobFetcher()
        result = fetcher.search("Software Engineer", location="Remote")
        for job in result.listings:
            print(job.title)
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        import asyncio
        self._base_url = base_url
        self._timeout = timeout

    def search(
        self,
        keywords: str,
        location: str | None = None,
        max_pages: int = 3,
        date_posted: str | None = None,
        job_type: str | None = None,
        experience_level: str | None = None,
        work_type: str | None = None,
        easy_apply: bool = False,
        sort_by: str | None = None,
    ) -> JobSearchResult:
        """Synchronous job search. See JobFetcher.search for parameter docs."""
        import asyncio

        async def _run():
            async with JobFetcher(
                base_url=self._base_url,
                timeout=self._timeout,
            ) as fetcher:
                return await fetcher.search(
                    keywords=keywords,
                    location=location,
                    max_pages=max_pages,
                    date_posted=date_posted,
                    job_type=job_type,
                    experience_level=experience_level,
                    work_type=work_type,
                    easy_apply=easy_apply,
                    sort_by=sort_by,
                )

        return asyncio.run(_run())

    def get_details(self, job_id: str) -> Dict[str, Any]:
        """Synchronous job detail fetch. See JobFetcher.get_details for docs."""
        import asyncio

        async def _run():
            async with JobFetcher(
                base_url=self._base_url,
                timeout=self._timeout,
            ) as fetcher:
                return await fetcher.get_details(job_id)

        return asyncio.run(_run())

    # Use this to get pure job postings
    def scrape_recommended(
        self,
        location: str | None = None,
        max_pages: int = 2,
        date_posted: str | None = None,
        job_type: str | None = None,
        experience_level: str | None = None,
        work_type: str | None = None,
        easy_apply: bool = False,
        sort_by: str | None = None,
    ) -> JobSearchResult:
        """Synchronous recommended jobs scrape. See JobFetcher.scrape_recommended."""
        import asyncio

        async def _run():
            async with JobFetcher(
                base_url=self._base_url,
                timeout=self._timeout,
            ) as fetcher:
                return await fetcher.scrape_recommended(
                    location=location,
                    max_pages=max_pages,
                    date_posted=date_posted,
                    job_type=job_type,
                    experience_level=experience_level,
                    work_type=work_type,
                    easy_apply=easy_apply,
                    sort_by=sort_by,
                )

        return asyncio.run(_run())

    def scrape_feed(self, num_posts: int = 50) -> Dict[str, Any]:
        """Synchronous feed scrape. See JobFetcher.scrape_feed for docs."""
        import asyncio

        async def _run():
            async with JobFetcher(
                base_url=self._base_url,
                timeout=self._timeout,
            ) as fetcher:
                return await fetcher.scrape_feed(num_posts=num_posts)

        return asyncio.run(_run())
