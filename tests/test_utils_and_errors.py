"""Tests for helpers, models and the custom exception hierarchy."""

import logging

import pytest

from models import Candidate, Job, MatchResult
from utils import (
    AIServiceError,
    FileOperationError,
    ParseError,
    ResumeAnalyzerError,
    SkillDictionary,
    ValidationError,
    clean_text,
    education_rank,
    safe_slug,
    setup_logging,
    split_items,
    unique_preserve_order,
)


@pytest.mark.parametrize(
    "exc", [ParseError, ValidationError, FileOperationError, AIServiceError]
)
def test_exception_hierarchy(exc):
    assert issubclass(exc, ResumeAnalyzerError)
    with pytest.raises(ResumeAnalyzerError):
        raise exc("message")


def test_clean_text_normalizes_whitespace_and_noise():
    raw = "  Hello\t\tWorld \r\n\r\n\r\n\r\n\u200bNext\x0cPage \ufb01nal  "
    cleaned = clean_text(raw)
    assert cleaned == "Hello World\n\nNext\nPage final"
    assert clean_text("") == "" and clean_text(None) == ""


def test_unique_and_split_helpers():
    assert unique_preserve_order(["Python", "python", " SQL ", "", "sql"]) == [
        "Python",
        "SQL",
    ]
    assert split_items("Python, SQL;Git\n- ignored? | Docker \u2022 AWS, python") == [
        "Python",
        "SQL",
        "Git",
        "- ignored?",
        "Docker",
        "AWS",
    ]
    assert split_items("") == []


def test_safe_slug():
    assert safe_slug("../../Hello World!.pdf") == "Hello-World-pdf"
    assert "/" not in safe_slug("a/b\\c") and safe_slug("???") == "item"


@pytest.mark.parametrize(
    "text, rank",
    [
        ("Ph.D. in Physics", 4),
        ("MBA", 3),
        ("M.Tech CSE", 3),
        ("Master of Science", 3),
        ("B.E. Computer Science", 2),
        ("Bachelor of Arts", 2),
        ("BCA", 2),
        ("Diploma in Engineering", 1),
        ("High school", 0),
        ("", 0),
        (None, 0),
        ("Scrum Master", 0),
        ("Master", 3),
        ("Bachelor's", 2),
        ("PhD", 4),
    ],
)
def test_education_rank(text, rank):
    assert education_rank(text) == rank


def test_skill_dictionary_normalize_and_extend():
    skills = SkillDictionary.combined()
    assert skills.normalize(" JS ") == "javascript"
    assert skills.normalize("Unknown Thing.") == "unknown thing"
    skills.add_skill("rust-lang", ["rustlang"])
    assert skills.normalize("RustLang") == "rust-lang"
    with pytest.raises(ValidationError):
        skills.add_skill("   ")


def test_skill_search_boundaries():
    technical = SkillDictionary.technical()
    assert technical.find_in_text("C++, C# and Node.js") == ["c++", "c#", "node.js"]
    assert "go" not in technical.find_in_text("I go to work and let it go")
    assert "go" in technical.find_in_text("Experience with Golang services")
    assert technical.find_in_text("") == []


def test_candidate_from_dict_ignores_unknown_keys_and_validates():
    candidate = Candidate.from_dict({"name": "A", "skills": ["x"], "unknown": 1})
    assert candidate.name == "A"
    with pytest.raises(ValidationError):
        Candidate.from_dict("not a dict")
    with pytest.raises(ValidationError):
        Candidate.from_dict({"experience": -3})


def test_job_from_dict_validation():
    job = Job.from_dict({"title": "Dev", "required_skills": ["python"]})
    assert job.min_experience == 0
    with pytest.raises(ValidationError):
        Job.from_dict({"title": "Dev"})
    with pytest.raises(ValidationError):
        Job.from_dict([])


def test_match_result_from_dict_requires_fields():
    with pytest.raises(ValidationError):
        MatchResult.from_dict({"score": 5})
    with pytest.raises(ValidationError):
        MatchResult.from_dict(None)


def test_setup_logging_is_idempotent(tmp_path):
    log_file = tmp_path / "logs" / "app.log"
    setup_logging(log_file)
    setup_logging(log_file)
    project_logger = logging.getLogger("resume_analyzer")
    names = [h.name for h in project_logger.handlers]
    assert names.count("resume_analyzer_console") == 1
    assert names.count("resume_analyzer_file") == 1
    assert log_file.parent.exists()
