'''
File: /home/mvayyat/work/my_ai_agents/tests/gemini_api_test.py
Project: /home/mvayyat/work/my_ai_agents/tests
Created Date: Friday, June 19th, 2026
Author: mvayyat
-----
Last Modified: Friday, June 19th, 2026, 12:32:26 pm
Modified By: mvayyat at midhun.v@iiits.in
-----
Copyright (c) midhun.v@iiits.in
-----
'''

"""Tests for Gemini API connectivity and basic generation."""

import os
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from google import genai
from google.genai import types
from google.genai.errors import ClientError

import yaml
    

MODEL = yaml.safe_load(open("/home/mvayyat/work/my_ai_agents/model_config/google.yaml"))["GOOGLE_MODEL"]


def _skip_on_quota(exc: ClientError) -> None:
    """Re-raise unless the error is a 429 quota/rate-limit, in which case skip."""
    if exc.code == 429:
        pytest.skip(f"Quota/rate-limit exceeded (429): {exc}")
    raise


@pytest.fixture(scope="module")
def client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set in environment or .env")
    return genai.Client(api_key=api_key)


def test_api_key_is_set():
    """Verify the API key is present in the environment."""
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    assert os.getenv("GEMINI_API_KEY"), "GEMINI_API_KEY must be set in .env"


def test_basic_text_generation(client):
    """Gemini returns a non-empty text response for a simple prompt."""
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents="Reply with exactly the word: PONG",
        )
    except ClientError as exc:
        _skip_on_quota(exc)
    text = response.text.strip()
    assert text, "Response text should not be empty"
    assert "PONG" in text.upper()


def test_response_has_usage_metadata(client):
    """Response includes token usage metadata."""
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents="Say hello.",
        )
    except ClientError as exc:
        _skip_on_quota(exc)
    assert response.usage_metadata is not None
    assert response.usage_metadata.prompt_token_count > 0
    assert response.usage_metadata.candidates_token_count > 0


def test_system_instruction(client):
    """System instruction is respected by the model."""
    try:
        response = client.models.generate_content(
            model=MODEL,
            config=types.GenerateContentConfig(
                system_instruction="You are a pirate. Always reply in pirate speak.",
            ),
            contents="How are you?",
        )
    except ClientError as exc:
        _skip_on_quota(exc)
    text = response.text.strip().lower()
    assert text, "Response should not be empty"
    # Pirate words commonly expected
    pirate_words = {"arr", "ahoy", "matey", "ye", "aye", "sea", "ship", "treasure"}
    assert any(word in text for word in pirate_words), (
        f"Expected pirate speak but got: {text}"
    )


def test_model_list(client):
    """API can list available models and at least one gemini model is present."""
    models = list(client.models.list())
    names = [m.name for m in models]
    assert any("gemini" in n.lower() for n in names), (
        f"No gemini models found in list: {names[:5]}"
    )
