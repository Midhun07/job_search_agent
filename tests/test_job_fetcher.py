'''
File: /home/mvayyat/work/my_ai_agents/tests/test_job_fetcher.py
Project: /home/mvayyat/work/my_ai_agents/tests
Created Date: Friday, June 19th, 2026
Author: mvayyat
-----
Last Modified: Friday, June 19th, 2026, 12:32:38 pm
Modified By: mvayyat at midhun.v@iiits.in
-----
Copyright (c) midhun.v@iiits.in
-----

Tests for the LinkedIn MCP-based Job Fetcher.

Requires the LinkedIn MCP server to be running:
    cd linkedin-mcp-server
    uv run -m linkedin_mcp_server --transport streamable-http

Tests marked with 'integration' require a live MCP server.
'''

import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.components.job_fetcher import (
    JobFetcher,
    JobListing,
    JobSearchResult,
    LinkedInMCPClient,
    SyncJobFetcher,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MCP_HOST = os.getenv("LINKEDIN_MCP_HOST", "127.0.0.1")
MCP_PORT = os.getenv("LINKEDIN_MCP_PORT", "8000")

pytestmark_integration = pytest.mark.skip(reason="needs live MCP server")

def _pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: test requires live LinkedIn MCP server")


def _skip_if_server_down() -> bool:
    """Quick check if the MCP server is reachable."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((MCP_HOST, int(MCP_PORT)))
        s.close()
        return True
    except Exception:
        return False


need_server = pytest.mark.skipif(
    not _skip_if_server_down(),
    reason=f"LinkedIn MCP server not running at {MCP_HOST}:{MCP_PORT}",
)


# ---------------------------------------------------------------------------
# Unit tests (no server required)
# ---------------------------------------------------------------------------

class TestJobListing:
    def test_creation_with_defaults(self):
        listing = JobListing(job_id="123")
        assert listing.job_id == "123"
        assert listing.title == ""
        assert listing.company == ""

    def test_to_dict(self):
        listing = JobListing(
            job_id="abc",
            title="Data Scientist",
            company="Acme Corp",
            location="Remote",
            url="https://linkedin.com/jobs/view/abc",
        )
        d = listing.to_dict()
        assert d["job_id"] == "abc"
        assert d["title"] == "Data Scientist"
        assert d["company"] == "Acme Corp"


class TestJobSearchResult:
    def test_empty_result(self):
        result = JobSearchResult(
            query_keywords="test",
            query_location=None,
            total_results_estimate=0,
        )
        assert result.total_results_estimate == 0
        assert result.job_ids == []
        assert result.listings == []

    def test_to_dict(self):
        result = JobSearchResult(
            query_keywords="ML Engineer",
            query_location="Remote",
            total_results_estimate=5,
            job_ids=["1", "2"],
            listings=[
                JobListing(job_id="1", title="MLE"),
                JobListing(job_id="2", title="Senior MLE"),
            ],
        )
        d = result.to_dict()
        assert d["query_keywords"] == "ML Engineer"
        assert len(d["listings"]) == 2


class TestLinkedInMCPClientInit:
    def test_default_base_url(self):
        client = LinkedInMCPClient()
        assert "127.0.0.1" in client._base_url

    def test_custom_base_url(self):
        client = LinkedInMCPClient(base_url="http://localhost:9999")
        assert client._base_url == "http://localhost:9999"

    def test_not_connected_initially(self):
        client = LinkedInMCPClient()
        assert not client.connected


# ---------------------------------------------------------------------------
# Integration tests (require live MCP server)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@need_server
class TestJobFetcherIntegration:
    async def test_initialize_mcp_client(self):
        """MCP client can connect and initialize a session."""
        client = LinkedInMCPClient()
        try:
            await client.__aenter__()
            assert client.connected
        finally:
            await client.__aexit__()

    async def test_search_returns_job_ids(self):
        """search_jobs returns at least job_ids."""
        async with JobFetcher() as fetcher:
            result = await fetcher.search(
                keywords="software engineer",
                location="Remote",
                max_pages=1,
            )
        assert isinstance(result, JobSearchResult)
        assert result.query_keywords == "software engineer"
        # Even with no results, the structure should be valid
        assert isinstance(result.job_ids, list)

    async def test_search_with_filters(self):
        """search with date_posted and work_type filters."""
        async with JobFetcher() as fetcher:
            result = await fetcher.search(
                keywords="data analyst",
                location="San Francisco",
                max_pages=1,
                date_posted="past_week",
                work_type="remote",
                sort_by="date",
            )
        assert result.query_keywords == "data analyst"
        assert result.query_location == "San Francisco"

    async def test_get_job_details(self):
        """get_job_details returns structured data for a valid job ID."""
        async with JobFetcher() as fetcher:
            # First search to get a job ID
            search_result = await fetcher.search(
                keywords="engineer",
                max_pages=1,
            )
            if search_result.job_ids:
                job_id = search_result.job_ids[0]
                details = await fetcher.get_details(job_id)
                assert "url" in details or "sections" in details
            else:
                pytest.skip("No job IDs returned from search")


@need_server
def test_sync_job_fetcher():
    """SyncJobFetcher works end-to-end."""
    fetcher = SyncJobFetcher()
    result = fetcher.search(keywords="developer", max_pages=1)
    assert isinstance(result, JobSearchResult)
    assert isinstance(result.job_ids, list)


# ---------------------------------------------------------------------------
# Integration tests for new recommended / feed methods
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@need_server
class TestJobFetcherRecommended:
    async def test_scrape_recommended(self):
        """scrape_recommended returns jobs without keywords."""
        async with JobFetcher() as fetcher:
            result = await fetcher.scrape_recommended(max_pages=1)
        assert isinstance(result, JobSearchResult)
        assert result.query_keywords == ""

    async def test_scrape_feed(self):
        """scrape_feed returns feed data with sections."""
        async with JobFetcher() as fetcher:
            result = await fetcher.scrape_feed(num_posts=10)
        assert "sections" in result or "section_errors" in result
        assert isinstance(result.get("sections", {}), dict)


@need_server
def test_sync_scrape_recommended():
    """SyncJobFetcher.scrape_recommended works."""
    fetcher = SyncJobFetcher()
    result = fetcher.scrape_recommended(max_pages=1)
    assert isinstance(result, JobSearchResult)
    assert result.query_keywords == ""


@need_server
def test_sync_scrape_feed():
    """SyncJobFetcher.scrape_feed works."""
    fetcher = SyncJobFetcher()
    result = fetcher.scrape_feed(num_posts=10)
    assert "sections" in result or "section_errors" in result
