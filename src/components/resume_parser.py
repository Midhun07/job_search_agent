'''
File: /home/mvayyat/work/my_ai_agents/src/components/resume_parser.py
Project: /home/mvayyat/work/my_ai_agents/src/components
Created Date: Friday, June 19th, 2026
Author: mvayyat
-----
Last Modified: Friday, June 19th, 2026, 12:31:35 pm
Modified By: mvayyat at midhun.v@iiits.in
-----
Copyright (c) midhun.v@iiits.in
-----
'''

import json
import os
from pathlib import Path
from typing import List, Optional, TypedDict

import yaml

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = yaml.safe_load(open("/home/mvayyat/work/my_ai_agents/model_config/google.yaml"))["GOOGLE_MODEL"]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class ExperienceEntry(TypedDict):
    company: str
    title: str
    duration: str
    bullets: List[str]


class EducationEntry(TypedDict):
    institution: str
    degree: str
    year: str


class ResumeProfile(TypedDict):
    name: str
    email: str
    phone: Optional[str]
    location: Optional[str]
    summary: Optional[str]
    skills: List[str]
    experience: List[ExperienceEntry]
    education: List[EducationEntry]
    certifications: List[str]
    linkedin_url: Optional[str]


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_from_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_text_from_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text(resume_path: str) -> str:
    """Return raw text from a PDF, DOCX, or plain-text resume file."""
    p = Path(resume_path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _extract_text_from_pdf(p)
    elif suffix in (".docx", ".doc"):
        return _extract_text_from_docx(p)
    elif suffix in (".txt", ".md", ""):
        return p.read_text(encoding="utf-8")
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


# ---------------------------------------------------------------------------
# LLM parsing
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an expert resume parser.
Extract structured information from the resume text and return ONLY a valid JSON
object matching this exact schema (no markdown fences, no extra keys):

{
  "name": "string",
  "email": "string",
  "phone": "string or null",
  "location": "string or null",
  "summary": "string or null",
  "skills": ["string"],
  "experience": [
    {
      "company": "string",
      "title": "string",
      "duration": "string",
      "bullets": ["string"]
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string",
      "year": "string"
    }
  ],
  "certifications": ["string"],
  "linkedin_url": "string or null"
}"""


def parse_resume(resume_path: str, api_key: Optional[str] = None) -> ResumeProfile:
    """
    Parse a resume file (PDF, DOCX, or TXT) into a ResumeProfile dict
    using Gemini as the LLM backend.

    Args:
        resume_path: Path to the resume file.
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.

    Returns:
        A ResumeProfile TypedDict with structured resume data.
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise EnvironmentError("GEMINI_API_KEY is not set.")

    raw_text = extract_text(resume_path)
    if not raw_text.strip():
        raise ValueError(f"No text could be extracted from: {resume_path}")

    client = genai.Client(api_key=key)

    response = client.models.generate_content(
        model=MODEL,
        contents=f"Parse this resume:\n\n{raw_text}",
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            temperature=0.0,
        ),
    )

    raw_json = response.text.strip()
    # Strip accidental markdown fences if the model adds them
    if raw_json.startswith("```"):
        raw_json = raw_json.split("```")[1]
        if raw_json.startswith("json"):
            raw_json = raw_json[4:]

    profile: ResumeProfile = json.loads(raw_json)
    return profile


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python resume_parser.py <path/to/resume.pdf>")
        sys.exit(1)

    result = parse_resume(sys.argv[1])
    print(json.dumps(result, indent=2))

