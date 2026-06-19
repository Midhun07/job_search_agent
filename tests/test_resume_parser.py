'''
File: /home/mvayyat/work/my_ai_agents/tests/test_resume_parser.py
Project: /home/mvayyat/work/my_ai_agents/tests
Created Date: Friday, June 19th, 2026
Author: mvayyat
-----
Last Modified: Friday, June 19th, 2026, 12:33:03 pm
Modified By: mvayyat at midhun.v@iiits.in
-----
Copyright (c) midhun.v@iiits.in
-----
'''

import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Allow imports from src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from google.genai.errors import ClientError
from src.components.resume_parser import (
    ResumeProfile,
    extract_text,
    parse_resume,
)

RESUME_PATH = Path(__file__).parent.parent / "data" / "resumes" / "Midhun_V_CV.docx"


def _skip_on_quota(exc: ClientError) -> None:
    if exc.code == 429:
        pytest.skip(f"Quota/rate-limit exceeded (429): {exc}")
    raise exc


# ---------------------------------------------------------------------------
# Text extraction (no API call)
# ---------------------------------------------------------------------------

def test_extract_text_returns_nonempty_string():
    """extract_text() should pull readable text from the DOCX without any API."""
    text = extract_text(str(RESUME_PATH))
    assert isinstance(text, str)
    assert len(text.strip()) > 100, "Expected substantial text from the resume DOCX"


def test_extract_text_contains_expected_content():
    """The extracted text should contain the candidate's name or common resume keywords."""
    text = extract_text(str(RESUME_PATH)).lower()
    keywords = ["experience", "education", "skills"]
    matched = [kw for kw in keywords if kw in text]
    assert matched, f"None of {keywords} found in extracted text"


# ---------------------------------------------------------------------------
# Full parse (Gemini API required)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def profile() -> ResumeProfile:
    """Parse the DOCX once per test session; skip on missing key or quota."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set")
    try:
        return parse_resume(str(RESUME_PATH), api_key=api_key)
    except ClientError as exc:
        _skip_on_quota(exc)


def test_profile_has_required_keys(profile):
    """ResumeProfile must contain all mandatory top-level keys."""
    required = {"name", "email", "skills", "experience", "education", "certifications"}
    missing = required - profile.keys()
    assert not missing, f"Missing keys in ResumeProfile: {missing}"


def test_profile_name_is_nonempty_string(profile):
    assert isinstance(profile["name"], str) and profile["name"].strip()


def test_profile_email_looks_valid(profile):
    email = profile.get("email", "")
    assert "@" in email and "." in email, f"Invalid email: {email!r}"


def test_profile_skills_is_list_of_strings(profile):
    skills = profile.get("skills", [])
    assert isinstance(skills, list) and len(skills) > 0
    assert all(isinstance(s, str) for s in skills), "All skills should be strings"


def test_profile_experience_structure(profile):
    exp = profile.get("experience", [])
    assert isinstance(exp, list) and len(exp) > 0, "Expected at least one experience entry"
    for entry in exp:
        assert "company" in entry and "title" in entry, f"Malformed experience entry: {entry}"
        assert isinstance(entry.get("bullets", []), list)


def test_profile_education_structure(profile):
    edu = profile.get("education", [])
    assert isinstance(edu, list) and len(edu) > 0, "Expected at least one education entry"
    for entry in edu:
        assert "institution" in entry and "degree" in entry, f"Malformed education entry: {entry}"
