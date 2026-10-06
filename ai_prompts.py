"""Optional AI layer: structured prompts, a small API client and validators.

The AI never replaces the deterministic parser or scorer. It only adds
*suggestions* (extra skills found in the text, skill categories, a written
explanation and interview questions). Every AI response is validated, and a
rule-based fallback is used when the AI is unavailable or returns bad output.

API keys are read from environment variables only:

* ``ANTHROPIC_API_KEY`` (optional ``ANTHROPIC_MODEL``)
* ``OPENAI_API_KEY`` (optional ``OPENAI_MODEL``)
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from string import Template
from typing import Any, Dict, List, Optional, Tuple

from models import Candidate, Job, MatchResult
from utils import AIServiceError, get_logger, redact_pii, unique_preserve_order

logger = get_logger("ai")

SOURCE_AI = "AI-generated suggestion"
SOURCE_RULES = "rule-based"
MAX_RESUME_CHARS = 8000
MAX_QUESTIONS = 6

SYSTEM_PROMPT = (
    "You are an assistant for recruiters. Use ONLY the information provided. "
    "Never invent facts, employers, dates, skills or qualifications. Never use or "
    "mention protected characteristics (age, gender, race, religion, nationality, "
    "marital status, disability). Reply with a single JSON object and nothing else."
)

EXTRACTION_PROMPT = Template("""Extract information from the resume text below.
Return JSON exactly like:
{"skills": ["..."], "soft_skills": ["..."], "certifications": ["..."],
 "projects": ["..."]}
Rules: copy items exactly as written in the resume; use [] when nothing is found;
do not guess; do not add anything that is not in the text.

RESUME TEXT:
$resume_text""")

CATEGORIZATION_PROMPT = Template(
    """Group these skills into categories. Use every skill at most once and only
skills from the list.
Return JSON exactly like:
{"programming_languages": [], "frameworks_and_libraries": [], "databases": [],
 "cloud_and_devops": [], "data_and_ai": [], "tools_and_other": []}

SKILLS: $skills"""
)

EXPLANATION_PROMPT = Template(
    """Explain in 3-4 sentences why this candidate received the match score below.
The score and recommendation are FIXED and were calculated by a program; do not
change, question or recalculate them. Mention concrete matched and missing skills.
Return JSON exactly like: {"explanation": "..."}

JOB TITLE: $title
SCORE: $score / 100
RECOMMENDATION: $recommendation
MATCHED REQUIRED SKILLS: $matched
MISSING REQUIRED SKILLS: $missing
EXPERIENCE: $experience
STRENGTHS: $strengths
GAPS: $gaps"""
)

QUESTIONS_PROMPT = Template(
    """Write $count interview questions tailored to this candidate and job.
Base them only on the facts below. Include questions about missing skills and
about the candidate's listed projects or strengths. Avoid personal or
discriminatory topics.
Return JSON exactly like: {"questions": ["...", "..."]}

JOB TITLE: $title
MATCHED SKILLS: $matched
MISSING SKILLS: $missing
PROJECTS: $projects
EXPERIENCE: $experience"""
)


# --------------------------------------------------------------------------
# API client
# --------------------------------------------------------------------------


class AIClient:
    """Minimal HTTP client for the Anthropic or OpenAI chat APIs (stdlib only)."""

    def __init__(
        self, provider: str, api_key: str, model: str, timeout: float = 30.0
    ) -> None:
        if provider not in ("anthropic", "openai"):
            raise AIServiceError(f"Unsupported AI provider: {provider}")
        if not api_key:
            raise AIServiceError("No API key provided.")
        self.provider = provider
        self.model = model
        self.timeout = timeout
        self._api_key = api_key

    @classmethod
    def from_env(cls) -> Optional["AIClient"]:
        """Create a client from environment variables, or None if no key is set."""
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if anthropic_key:
            model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
            return cls("anthropic", anthropic_key, model)
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if openai_key:
            return cls(
                "openai", openai_key, os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            )
        return None

    def complete(self, system: str, user: str) -> str:
        """Send one prompt and return the model's text reply."""
        if self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}
            body: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": 1000,
                "temperature": 0,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
        else:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self._api_key}"}
            body = {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("AI request failed with HTTP %s.", exc.code)
            raise AIServiceError(
                f"The AI service returned an error ({exc.code})."
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("AI service unreachable (%s).", exc.__class__.__name__)
            raise AIServiceError("The AI service could not be reached.") from exc
        except json.JSONDecodeError as exc:
            raise AIServiceError("The AI service sent an unreadable reply.") from exc
        try:
            if self.provider == "anthropic":
                return str(payload["content"][0]["text"])
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("The AI reply had an unexpected format.") from exc


# --------------------------------------------------------------------------
# Parsing and validating AI output
# --------------------------------------------------------------------------


def parse_ai_json(raw: str) -> Dict[str, Any]:
    """Parse a JSON object from a model reply (tolerates ``` fences / chatter)."""
    if not isinstance(raw, str) or not raw.strip():
        raise AIServiceError("The AI returned an empty reply.")
    text = re.sub(r"```(?:json)?", "", raw).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AIServiceError("The AI reply did not contain JSON.")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIServiceError("The AI reply was malformed JSON.") from exc
    if not isinstance(data, dict):
        raise AIServiceError("The AI reply was not a JSON object.")
    return data


def _string_list(value: Any, limit: int = 30, max_len: int = 200) -> List[str]:
    if not isinstance(value, list):
        return []
    items = [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return unique_preserve_order(i[:max_len] for i in items)[:limit]


def validate_extraction(data: Dict[str, Any], resume_text: str) -> Dict[str, List[str]]:
    """Keep only AI-extracted items that literally appear in the resume text.

    This blocks hallucinated skills, certifications and projects.
    """
    haystack = re.sub(r"\s+", " ", resume_text).casefold()
    result: Dict[str, List[str]] = {}
    for key in ("skills", "soft_skills", "certifications", "projects"):
        result[key] = [
            item
            for item in _string_list(data.get(key))
            if re.sub(r"\s+", " ", item).casefold() in haystack
        ]
    return result


CATEGORY_KEYS = (
    "programming_languages",
    "frameworks_and_libraries",
    "databases",
    "cloud_and_devops",
    "data_and_ai",
    "tools_and_other",
)


def validate_categorization(
    data: Dict[str, Any], skills: List[str]
) -> Dict[str, List[str]]:
    """Keep only known skills, each once; unplaced ones go to tools_and_other."""
    allowed = {s.casefold(): s for s in skills}
    placed = set()
    result: Dict[str, List[str]] = {key: [] for key in CATEGORY_KEYS}
    for key in CATEGORY_KEYS:
        for item in _string_list(data.get(key), limit=100):
            original = allowed.get(item.casefold())
            if original and original.casefold() not in placed:
                result[key].append(original)
                placed.add(original.casefold())
    result["tools_and_other"].extend(s for s in skills if s.casefold() not in placed)
    return result


def validate_explanation(data: Dict[str, Any]) -> str:
    """Return the explanation text or raise AIServiceError."""
    text = data.get("explanation")
    if not isinstance(text, str) or len(text.strip()) < 20:
        raise AIServiceError("The AI explanation was missing or too short.")
    return text.strip()[:1500]


def validate_questions(data: Dict[str, Any]) -> List[str]:
    """Return 3+ cleaned interview questions or raise AIServiceError."""
    questions = [
        q
        for q in _string_list(data.get("questions"), MAX_QUESTIONS, 300)
        if len(q) > 10
    ]
    if len(questions) < 3:
        raise AIServiceError("The AI returned too few usable interview questions.")
    return questions


# --------------------------------------------------------------------------
# Rule-based fallbacks
# --------------------------------------------------------------------------

_CATEGORY_HINTS = {
    "programming_languages": {
        "python",
        "java",
        "c",
        "c++",
        "c#",
        "javascript",
        "typescript",
        "go",
        "rust",
        "kotlin",
        "swift",
        "php",
        "ruby",
        "bash",
        "html",
        "css",
        "sql",
    },
    "frameworks_and_libraries": {
        "react",
        "angular",
        "vue",
        "next.js",
        "node.js",
        "express",
        "django",
        "flask",
        "fastapi",
        "spring boot",
        "streamlit",
        "bootstrap",
        "jquery",
        "tailwind css",
        ".net",
        "react native",
        "flutter",
    },
    "databases": {
        "mysql",
        "postgresql",
        "mongodb",
        "sqlite",
        "redis",
        "oracle",
        "dynamodb",
    },
    "cloud_and_devops": {
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "terraform",
        "jenkins",
        "ci/cd",
        "lambda",
        "s3",
        "ec2",
        "linux",
        "firebase",
    },
    "data_and_ai": {
        "machine learning",
        "deep learning",
        "nlp",
        "computer vision",
        "pandas",
        "numpy",
        "scikit-learn",
        "tensorflow",
        "pytorch",
        "matplotlib",
        "data analysis",
        "spark",
        "hadoop",
        "kafka",
        "tableau",
        "power bi",
    },
}


def fallback_categorize_skills(skills: List[str]) -> Dict[str, List[str]]:
    """Categorize skills with a built-in lookup (no AI needed)."""
    result: Dict[str, List[str]] = {key: [] for key in CATEGORY_KEYS}
    for skill in skills:
        for category, members in _CATEGORY_HINTS.items():
            if skill.casefold() in members:
                result[category].append(skill)
                break
        else:
            result["tools_and_other"].append(skill)
    return result


def fallback_interview_questions(
    candidate: Candidate, job: Job, result: MatchResult
) -> List[str]:
    """Create interview questions from the scoring facts (deterministic)."""
    questions: List[str] = []
    for skill in result.missing_required[:2]:
        questions.append(
            f"Your resume does not mention {skill}. Do you have related "
            f"experience, and how would you get up to speed on it?"
        )
    for skill in result.matched_required[:2]:
        questions.append(
            f"Describe a project where you used {skill} and the hardest "
            f"problem you solved with it."
        )
    for project in candidate.projects[:1]:
        questions.append(
            f"Walk us through your project '{project}': your role, the design "
            f"decisions, and what you would improve."
        )
    if job.min_experience > 0 and (candidate.experience or 0) < job.min_experience:
        questions.append(
            f"This {job.title} role expects {job.min_experience:g} years of "
            f"experience. Which of your experiences best prepares you for it?"
        )
    questions.append(
        f"What interests you about the {job.title} position, and how would "
        f"you approach your first 90 days?"
    )
    return unique_preserve_order(questions)[:MAX_QUESTIONS]


# --------------------------------------------------------------------------
# High-level helpers used by the app (always return something usable)
# --------------------------------------------------------------------------


def _ask(client: AIClient, prompt: str) -> Dict[str, Any]:
    return parse_ai_json(client.complete(SYSTEM_PROMPT, prompt))


def _fmt(items: List[str]) -> str:
    return ", ".join(items) if items else "none"


def ai_extract_resume_info(
    resume_text: str, client: Optional[AIClient]
) -> Tuple[Optional[Dict[str, List[str]]], str]:
    """Ask the AI for extra resume details; returns (validated data or None, status)."""
    if client is None:
        return None, "AI unavailable (no API key set)."
    prompt = EXTRACTION_PROMPT.substitute(
        resume_text=redact_pii(resume_text)[:MAX_RESUME_CHARS]
    )
    try:
        return validate_extraction(_ask(client, prompt), resume_text), SOURCE_AI
    except AIServiceError as exc:
        logger.warning("AI extraction skipped: %s", exc)
        return None, f"AI extraction skipped: {exc}"


def categorize_skills(
    skills: List[str], client: Optional[AIClient] = None
) -> Tuple[Dict[str, List[str]], str]:
    """Categorize skills with AI when possible, otherwise with the fallback."""
    if client is not None and skills:
        try:
            data = _ask(client, CATEGORIZATION_PROMPT.substitute(skills=_fmt(skills)))
            return validate_categorization(data, skills), SOURCE_AI
        except AIServiceError as exc:
            logger.warning("AI categorization fell back to rules: %s", exc)
    return fallback_categorize_skills(skills), SOURCE_RULES


def explain_match(
    candidate: Candidate,
    job: Job,
    result: MatchResult,
    client: Optional[AIClient] = None,
) -> Tuple[Optional[str], str]:
    """Return (AI commentary or None, source). The score is never changed."""
    if client is None:
        return None, SOURCE_RULES
    prompt = EXPLANATION_PROMPT.substitute(
        title=job.title,
        score=f"{result.score:g}",
        recommendation=result.recommendation,
        matched=_fmt(result.matched_required),
        missing=_fmt(result.missing_required),
        experience=(
            "not stated"
            if candidate.experience is None
            else f"{candidate.experience:g} years"
        ),
        strengths=" | ".join(result.strengths) or "none",
        gaps=" | ".join(result.improvements) or "none",
    )
    try:
        return validate_explanation(_ask(client, prompt)), SOURCE_AI
    except AIServiceError as exc:
        logger.warning("AI explanation fell back to rules: %s", exc)
        return None, SOURCE_RULES


def generate_interview_questions(
    candidate: Candidate,
    job: Job,
    result: MatchResult,
    client: Optional[AIClient] = None,
) -> Tuple[List[str], str]:
    """Return (questions, source); falls back to rule-based questions."""
    if client is not None:
        prompt = QUESTIONS_PROMPT.substitute(
            count=5,
            title=job.title,
            matched=_fmt(result.matched_required + result.matched_preferred),
            missing=_fmt(result.missing_required),
            projects=_fmt(candidate.projects[:5]),
            experience=(
                "not stated"
                if candidate.experience is None
                else f"{candidate.experience:g} years"
            ),
        )
        try:
            return validate_questions(_ask(client, prompt)), SOURCE_AI
        except AIServiceError as exc:
            logger.warning("AI questions fell back to rules: %s", exc)
    return fallback_interview_questions(candidate, job, result), SOURCE_RULES
