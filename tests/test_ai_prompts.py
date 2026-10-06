"""Tests for the optional AI layer (no network access is ever used)."""

import json
import urllib.error

import pytest

import ai_prompts
from ai_prompts import (
    AIClient,
    SOURCE_AI,
    SOURCE_RULES,
    ai_extract_resume_info,
    categorize_skills,
    explain_match,
    fallback_interview_questions,
    generate_interview_questions,
    parse_ai_json,
    validate_categorization,
    validate_explanation,
    validate_extraction,
    validate_questions,
)
from matcher import score_candidate
from utils import AIServiceError, redact_pii


class FakeClient:
    """Stands in for AIClient; returns canned text or raises."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def complete(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def result(strong_candidate, backend_job):
    return score_candidate(strong_candidate, backend_job)


# -- JSON parsing --------------------------------------------------------


def test_parse_plain_and_fenced_json():
    assert parse_ai_json('{"a": 1}') == {"a": 1}
    assert parse_ai_json('Sure!\n```json\n{"a": [1, 2]}\n```\nDone') == {"a": [1, 2]}


@pytest.mark.parametrize("raw", ["", "   ", "no json at all", '{"a": ', "[1, 2]", None])
def test_malformed_ai_json_raises(raw):
    with pytest.raises(AIServiceError):
        parse_ai_json(raw)


# -- validators ----------------------------------------------------------


def test_extraction_drops_hallucinated_items():
    text = "I know Python and Rust. Certified Kubernetes Administrator."
    data = {
        "skills": ["Python", "rust", "Haskell"],
        "soft_skills": "not a list",
        "certifications": ["Certified Kubernetes Administrator", "Fake Cert"],
        "projects": [42, None],
    }
    cleaned = validate_extraction(data, text)
    assert cleaned["skills"] == ["Python", "rust"]
    assert cleaned["certifications"] == ["Certified Kubernetes Administrator"]
    assert cleaned["soft_skills"] == [] and cleaned["projects"] == []


def test_categorization_only_uses_known_skills_once():
    data = {
        "programming_languages": ["python", "Invented"],
        "databases": ["python", "sql"],
        "cloud_and_devops": "oops",
    }
    cleaned = validate_categorization(data, ["python", "sql", "git"])
    assert cleaned["programming_languages"] == ["python"]
    assert cleaned["databases"] == ["sql"]
    assert cleaned["tools_and_other"] == ["git"]


def test_explanation_validation():
    assert validate_explanation(
        {"explanation": " " + "Good fit overall. " * 3}
    ).startswith("Good")
    for bad in ({}, {"explanation": 5}, {"explanation": "short"}):
        with pytest.raises(AIServiceError):
            validate_explanation(bad)


def test_questions_validation():
    ok = {
        "questions": [
            "Tell me about Python?",
            "Describe Docker usage?",
            "Explain REST design?",
        ]
    }
    assert len(validate_questions(ok)) == 3
    with pytest.raises(AIServiceError):
        validate_questions({"questions": ["Only one question here?"]})
    with pytest.raises(AIServiceError):
        validate_questions({"questions": "nope"})


# -- fallbacks and high-level helpers --------------------------------------


def test_fallback_questions_are_deterministic_and_relevant(
    strong_candidate, backend_job, result
):
    questions = fallback_interview_questions(strong_candidate, backend_job, result)
    assert questions == fallback_interview_questions(
        strong_candidate, backend_job, result
    )
    assert 1 <= len(questions) <= 6
    assert any("Inventory Tracker API" in q for q in questions)


def test_no_client_uses_rule_based_everything(strong_candidate, backend_job, result):
    questions, source = generate_interview_questions(
        strong_candidate, backend_job, result, None
    )
    assert source == SOURCE_RULES and questions
    assert explain_match(strong_candidate, backend_job, result, None) == (
        None,
        SOURCE_RULES,
    )
    categories, cat_source = categorize_skills(["python", "mysql", "docker"], None)
    assert cat_source == SOURCE_RULES
    assert categories["programming_languages"] == ["python"]
    assert categories["databases"] == ["mysql"]
    assert categories["cloud_and_devops"] == ["docker"]
    data, status = ai_extract_resume_info("resume text", None)
    assert data is None and "unavailable" in status


def test_unavailable_api_falls_back(strong_candidate, backend_job, result):
    client = FakeClient(error=AIServiceError("down"))
    questions, source = generate_interview_questions(
        strong_candidate, backend_job, result, client
    )
    assert source == SOURCE_RULES and questions
    assert explain_match(strong_candidate, backend_job, result, client) == (
        None,
        SOURCE_RULES,
    )
    assert categorize_skills(["python"], client)[1] == SOURCE_RULES
    data, status = ai_extract_resume_info("some resume text", client)
    assert data is None and "skipped" in status


def test_malformed_ai_reply_falls_back(strong_candidate, backend_job, result):
    client = FakeClient(reply="I'm sorry, I can't produce JSON")
    questions, source = generate_interview_questions(
        strong_candidate, backend_job, result, client
    )
    assert source == SOURCE_RULES and questions


def test_valid_ai_reply_is_used_and_labelled(strong_candidate, backend_job, result):
    reply = json.dumps(
        {
            "questions": [
                "How do you design Django APIs?",
                "Why use Docker here?",
                "Explain SQL indexing choices?",
            ]
        }
    )
    questions, source = generate_interview_questions(
        strong_candidate, backend_job, result, FakeClient(reply=reply)
    )
    assert source == SOURCE_AI and len(questions) == 3


def test_ai_prompt_never_asks_to_change_score(strong_candidate, backend_job, result):
    client = FakeClient(
        reply=json.dumps({"explanation": "Strong skills match overall, solid."})
    )
    text, source = explain_match(strong_candidate, backend_job, result, client)
    assert source == SOURCE_AI and text.startswith("Strong")
    system, user = client.calls[0]
    assert "FIXED" in user and f"{result.score:g}" in user
    assert "protected characteristics" in system
    assert strong_candidate.email not in user and strong_candidate.name not in user


def test_pii_is_redacted_before_sending():
    client = FakeClient(reply='{"skills": []}')
    resume = "Jane Doe jane@example.com +91 98765 43210 knows Python " * 3
    ai_extract_resume_info(resume, client)
    sent = client.calls[0][1]
    assert "jane@example.com" not in sent and "98765" not in sent
    assert "[EMAIL]" in sent and "[PHONE]" in sent
    assert "jane@example.com" not in redact_pii(resume)


# -- client construction / HTTP errors ------------------------------------


def test_client_from_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert AIClient.from_env() is None
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert AIClient.from_env().provider == "openai"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-test")
    assert AIClient.from_env().provider == "anthropic"


def test_client_rejects_bad_configuration():
    with pytest.raises(AIServiceError):
        AIClient("unknown", "key", "model")
    with pytest.raises(AIServiceError):
        AIClient("openai", "", "model")


def test_http_failures_become_ai_service_errors(monkeypatch):
    client = AIClient("anthropic", "key", "model")

    def unreachable(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(ai_prompts.urllib.request, "urlopen", unreachable)
    with pytest.raises(AIServiceError, match="could not be reached"):
        client.complete("system", "user")

    def http_error(*args, **kwargs):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(ai_prompts.urllib.request, "urlopen", http_error)
    with pytest.raises(AIServiceError, match="401"):
        client.complete("system", "user")


def test_api_key_never_appears_in_errors(monkeypatch):
    client = AIClient("openai", "sk-super-secret", "model")

    def boom(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(ai_prompts.urllib.request, "urlopen", boom)
    with pytest.raises(AIServiceError) as info:
        client.complete("s", "u")
    assert "sk-super-secret" not in str(info.value)
