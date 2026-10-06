"""Tests for report generation."""

from datetime import datetime

from matcher import score_candidate
from models import Candidate
from report_generator import generate_html_report, generate_text_report

WHEN = datetime(2026, 10, 4, 12, 0)


def _report(candidate, job, **kwargs):
    result = score_candidate(candidate, job)
    return result, generate_text_report(
        candidate, job, result, generated_at=WHEN, **kwargs
    )


def test_text_report_contains_required_sections(strong_candidate, backend_job):
    result, report = _report(strong_candidate, backend_job, interview_questions=["Q1?"])
    for heading in (
        "INTELLIGENT RESUME ANALYSIS REPORT",
        "CANDIDATE INFORMATION",
        "JOB INFORMATION",
        "ANALYSIS",
        "RECOMMENDATION",
        "ADDITIONAL INSIGHTS",
        "Candidate strengths",
        "Skill gaps",
        "Suggested interview questions",
        "Explanation of the recommendation",
    ):
        assert heading in report
    assert "Generated: 2026-10-04 12:00" in report


def test_report_has_correct_candidate_and_job_data(strong_candidate, backend_job):
    result, report = _report(strong_candidate, backend_job)
    assert "Test Person" in report
    assert "test@example.com" in report
    assert "5 years" in report
    assert "Python Backend Developer" in report
    assert "Python, Django, SQL, REST API, Git" in report
    assert "Minimum experience: 3 years" in report
    assert f"{result.score:g} / 100" in report
    assert result.recommendation in report
    assert "postgresql, ci/cd" in report  # missing preferred skills


def test_report_handles_missing_fields(backend_job):
    result, report = _report(Candidate(), backend_job)
    assert report.count("Not found in resume") >= 4
    assert "Phone:      Not found in resume" in report
    assert "0 / 100" in report


def test_report_marks_ai_content(strong_candidate, backend_job):
    _, report = _report(
        strong_candidate,
        backend_job,
        questions_source="AI-generated suggestion",
        ai_explanation="A fine candidate overall.",
    )
    assert "AI-generated suggestion" in report
    assert "not extracted fact" in report


def test_report_includes_disclaimer(strong_candidate, backend_job):
    _, report = _report(strong_candidate, backend_job)
    assert "not a final hiring decision" in report


def test_html_report_escapes_content(backend_job):
    candidate = Candidate(name="<script>alert(1)</script>", skills=["python"])
    result = score_candidate(candidate, backend_job)
    html_report = generate_html_report(
        candidate, backend_job, result, generated_at=WHEN
    )
    assert "<script>alert(1)</script>" not in html_report
    assert "&lt;script&gt;" in html_report
    assert html_report.startswith("<!DOCTYPE html>")
    assert "INTELLIGENT RESUME ANALYSIS REPORT" in html_report


def test_html_report_contains_score_and_recommendation(strong_candidate, backend_job):
    result = score_candidate(strong_candidate, backend_job)
    html_report = generate_html_report(
        strong_candidate, backend_job, result, ["Why Python?"], generated_at=WHEN
    )
    assert "92.5 / 100" in html_report
    assert "Strongly Recommend" in html_report
    assert "Why Python?" in html_report


def test_report_is_deterministic_for_fixed_time(strong_candidate, backend_job):
    _, first = _report(strong_candidate, backend_job)
    _, second = _report(strong_candidate, backend_job)
    assert first == second
