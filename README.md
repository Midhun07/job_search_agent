# Job Search AI Agent

An autonomous AI-powered job search agent that parses resumes, scrapes LinkedIn jobs via MCP, ranks matches, and prepares tailored applications — all orchestrated through LLM-driven workflows.

## Architecture

```
┌──────────────────┐     ┌───────────────────┐     ┌──────────────────┐
│   Resume Parser  │────▶│  Structured Profile │────▶│  Cross Matcher   │
│  (Gemini LLM)    │     │   (JSON/TypedDict)  │     │  (LLM + Embed)   │
└──────────────────┘     └───────────────────┘     └────────┬─────────┘
                                                            │
┌──────────────────┐     ┌───────────────────┐              │
│  LinkedIn MCP    │────▶│    Job Fetcher     │──────────────┘
│  Server          │     │  (MCP over HTTP)   │
└──────────────────┘     └───────────────────┘
         │                        │
         ▼                        ▼
┌──────────────────────────────────────────────────────┐
│                 LLM Ranking & Filtering               │
└──────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────┐     ┌──────────────────────────────┐
│  Cover Letter    │     │    Auto-Apply / Human Loop    │
│  + Resume Tailor │────▶│    (Playwright + LLM)         │
└──────────────────┘     └──────────────────────────────┘
```

## Components

### Implemented

| Component | File | Description |
|-----------|------|-------------|
| **Resume Parser** | `src/components/resume_parser.py` | Gemini-powered PDF/DOCX/TXT → structured `ResumeProfile` (JSON) |
| **Job Fetcher** | `src/components/job_fetcher.py` | LinkedIn MCP client over HTTP — keyword search, recommended jobs, feed scraping, job details |
| **LinkedIn MCP Server** | `linkedin-mcp-server/` | Full FastMCP server for LinkedIn scraping (profiles, jobs, companies, messaging) |

### Planned

| Component | Plan Reference |
|-----------|---------------|
| Cross Matcher | Stage 2 Phase 2 — LLM + embedding-based job↔resume scoring |
| Resume Tailor | Stage 2 Phase 3 — Dynamic resume optimization per job |
| Cover Letter Generator | Stage 2 Phase 3 — Personalized cover letters |
| Auto-Apply Engine | Stage 2 Phase 4 — Playwright + LLM form filling |
| LangGraph Workflow | Master Plan Phase 4 / Stage 2 Phase 5 — Stateful agent orchestration |
| Application Tracker | Stage 2 Phase 6 — Status tracking (saved/applied/interview/rejected) |
| Multi-Agent System | Stage 2 Phase 9 — Planner + Worker agents |
| Backend API | Master Plan Phase 7 — FastAPI with LangGraph integration |

## Quick Start

### Prerequisites

- Python 3.10+
- Google Gemini API key
- LinkedIn account (for MCP server authentication)
- `uv` (for running the LinkedIn MCP server)

### Setup

```bash
# 1. Clone and set up environment
cd ~/work/my_ai_agents
python3 -m venv ~/work/envs/agentic_ai
source ~/work/envs/agentic_ai/bin/activate
pip install google-genai python-dotenv pypdf python-docx httpx pytest pytest-asyncio

# 2. Configure API keys
cp .env.example .env   # or create .env with:
echo 'GEMINI_API_KEY=your_key_here' > .env

# 3. Verify Gemini connectivity
pytest tests/gemini_api_test.py -v

# 4. Set up LinkedIn MCP server
cd linkedin-mcp-server
uv sync
uv run patchright install chromium
uv run -m linkedin_mcp_server --login    # Interactive LinkedIn login
```

### Running the LinkedIn MCP Server

```bash
# Terminal 1: Start the server
cd linkedin-mcp-server
uv run -m linkedin_mcp_server --transport streamable-http --log-level DEBUG
# Server runs at http://127.0.0.1:8000/mcp
```

### Using the Components

```python
import asyncio
from src.components.job_fetcher import JobFetcher
from src.components.resume_parser import parse_resume

# Parse a resume
profile = parse_resume("data/resumes/my_resume.pdf")

# Scrape recommended jobs from LinkedIn (personalized, no keywords needed)
async def main():
    async with JobFetcher() as fetcher:
        # Get ~50 personalized job recommendations
        jobs = await fetcher.scrape_recommended(
            work_type="remote",
            max_pages=2,
        )
        print(f"Found {jobs.total_results_estimate} recommended jobs")

        # Get details for a specific job
        if jobs.job_ids:
            details = await fetcher.get_details(jobs.job_ids[0])
            print(details["sections"]["job_posting"][:500])

asyncio.run(main())
```

## Testing

```bash
# Unit tests (no server required)
pytest tests/ -v -m "not integration"

# Integration tests (require LinkedIn MCP server running)
pytest tests/test_job_fetcher.py -v -m "integration"

# All tests
pytest tests/ -v
```

### Test Results (2026-06-19)

```
tests/test_job_fetcher.py ........ ........ 16/16 passed
tests/test_resume_parser.py ........        8/8  (2 passed, 6 skipped - needs API key)
tests/gemini_api_test.py .....              5/5  (needs API key)
```

## Project Structure

```
my_ai_agents/
├── .github/
│   ├── agents/job-search-architect.agent.md   # Custom VS Code agent
│   └── skills/caveman/SKILL.md                # Terse communication mode
├── data/resumes/                              # Sample resumes for testing
├── linkedin-mcp-server/                       # LinkedIn MCP server (FastMCP)
│   ├── linkedin_mcp_server/
│   │   ├── tools/          # MCP tools (job, person, company, feed, messaging)
│   │   ├── scraping/       # Core extraction engine (Playwright)
│   │   └── server.py       # FastMCP server setup
│   └── pyproject.toml
├── model_config/
│   └── google.yaml         # Google Gemini model config
├── notebooks/              # Jupyter notebooks for exploration
├── plan_designed_by_ai/    # Architecture and roadmap documents
│   ├── master_plan_job_search_agent.md
│   └── stage_2_resume_parser_and_auto_apply.md
├── src/components/
│   ├── resume_parser.py    # Gemini-powered resume parser
│   ├── job_fetcher.py      # LinkedIn MCP-based job scraper
│   └── cross_matcher.py    # Job↔Resume matching engine (next)
├── tests/
│   ├── gemini_api_test.py
│   ├── test_resume_parser.py
│   └── test_job_fetcher.py
├── .env                    # API keys (gitignored)
├── .gitignore
├── pytest.ini
└── README.md
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini (via `google-genai`) |
| Job Scraping | LinkedIn MCP Server (FastMCP + Playwright/`patchright`) |
| MCP Transport | JSON-RPC 2.0 over SSE (Server-Sent Events) |
| HTTP Client | `httpx` (async) |
| Resume Parsing | `pypdf`, `python-docx` + Gemini structured extraction |
| Orchestration | LangGraph (planned) |
| Backend | FastAPI (planned) |
| Vector DB | ChromaDB / FAISS (planned) |
| Testing | `pytest` + `pytest-asyncio` |

## Roadmap

Based on the [master plan](plan_designed_by_ai/master_plan_job_search_agent.md) and [stage 2 plan](plan_designed_by_ai/stage_2_resume_parser_and_auto_apply.md):

| Stage | Component | Status |
|-------|-----------|--------|
| 1 | Resume Parsing Engine | ✅ Done |
| 2 | Job Fetcher (LinkedIn MCP) | ✅ Done |
| 3 | Cross Matcher (Job ↔ Resume) | 🔨 Next |
| 4 | Resume Tailor + Cover Letter | ⬚ Planned |
| 5 | LangGraph Integration | ⬚ Planned |
| 6 | Auto-Apply (Human-in-loop) | ⬚ Planned |
| 7 | Application Tracker | ⬚ Planned |
| 8 | Backend API (FastAPI) | ⬚ Planned |
| 9 | Multi-Agent System | ⬚ Planned |

## License

MIT
