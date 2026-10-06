"""Human-readable report generation (plain text and HTML)."""

from __future__ import annotations

import html
from datetime import datetime
from typing import List, Optional

from models import Candidate, Job, MatchResult

RULE = "=" * 64
SUB_RULE = "-" * 64
NOT_FOUND = "Not found in resume"
DISCLAIMER = (
    "This report supports recruiter review. It is not a final hiring decision, "
    "and no protected characteristics were used in the analysis."
)


def _or_default(value: Optional[object], default: str = NOT_FOUND) -> str:
    return str(value) if value not in (None, "", []) else default


def _join(items: List[str], default: str = "None") -> str:
    return ", ".join(items) if items else default


def _experience_text(candidate: Candidate) -> str:
    if candidate.experience is None:
        return NOT_FOUND
    return f"{candidate.experience:g} years"


def _timestamp(generated_at: Optional[datetime]) -> str:
    return (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")


def _bullets(items: List[str], default: str = "None identified") -> List[str]:
    return [f"  - {item}" for item in items] if items else [f"  {default}"]


def generate_text_report(
    candidate: Candidate,
    job: Job,
    result: MatchResult,
    interview_questions: Optional[List[str]] = None,
    questions_source: str = "rule-based",
    ai_explanation: Optional[str] = None,
    generated_at: Optional[datetime] = None,
) -> str:
    """Build the plain-text analysis report."""
    breakdown = result.breakdown
    lines: List[str] = [
        RULE,
        "INTELLIGENT RESUME ANALYSIS REPORT",
        RULE,
        f"Generated: {_timestamp(generated_at)}",
        "",
        "CANDIDATE INFORMATION",
        SUB_RULE,
        f"Name:       {_or_default(candidate.name)}",
        f"Email:      {_or_default(candidate.email)}",
        f"Phone:      {_or_default(candidate.phone)}",
        f"Education:  {_join(candidate.education, NOT_FOUND)}",
        f"Experience: {_experience_text(candidate)}",
        f"Skills:     {_join(candidate.skills)}",
        f"Soft skills: {_join(candidate.soft_skills)}",
        f"Certifications: {_join(candidate.certifications)}",
        f"Projects:   {_join(candidate.projects)}",
        "",
        "JOB INFORMATION",
        SUB_RULE,
        f"Position:           {job.title}",
        f"Required skills:    {_join(job.required_skills)}",
        f"Preferred skills:   {_join(job.preferred_skills)}",
        f"Minimum experience: {job.min_experience:g} years",
        f"Required education: {_or_default(job.required_education, 'Not specified')}",
        "",
        "ANALYSIS",
        SUB_RULE,
        f"Overall match score: {result.score:g} / 100",
    ]
    for key in ("required_skills", "preferred_skills", "experience", "education"):
        item = breakdown[key]
        if item["applicable"]:
            lines.append(
                f"{item['label'] + ':':<18} {item['points']:g} / "
                f"{item['max_points']:g} "
                f"points - {item['detail']}"
            )
        else:
            lines.append(f"{item['label'] + ':':<18} skipped - {item['detail']}")
    lines += [
        f"Matched skills (required):  {_join(result.matched_required)}",
        f"Missing skills (required):  {_join(result.missing_required)}",
        f"Matched skills (preferred): {_join(result.matched_preferred)}",
        f"Missing skills (preferred): {_join(result.missing_preferred)}",
        "",
        "RECOMMENDATION",
        SUB_RULE,
        result.recommendation,
        "",
        "ADDITIONAL INSIGHTS",
        SUB_RULE,
        "Candidate strengths:",
        *_bullets(result.strengths),
        "Skill gaps and areas for improvement:",
        *_bullets(result.improvements),
        f"Suggested interview questions ({questions_source}):",
        *_bullets(interview_questions or [], "No questions generated"),
        "",
        "Explanation of the recommendation:",
        f"  {result.explanation}",
    ]
    if ai_explanation:
        lines += ["", "AI-generated commentary (suggestion, not extracted fact):"]
        lines.append(f"  {ai_explanation}")
    lines += ["", SUB_RULE, DISCLAIMER, RULE, ""]
    return "\n".join(lines)


def _esc(value: object) -> str:
    return html.escape(str(value))


def _html_list(items: List[str], default: str = "None") -> str:
    if not items:
        return f"<p>{_esc(default)}</p>"
    return "<ul>" + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>"


def generate_html_report(
    candidate: Candidate,
    job: Job,
    result: MatchResult,
    interview_questions: Optional[List[str]] = None,
    questions_source: str = "rule-based",
    ai_explanation: Optional[str] = None,
    generated_at: Optional[datetime] = None,
) -> str:
    """Build a self-contained HTML version of the report."""
    rows = "".join(
        f"<tr><td>{_esc(item['label'])}</td>"
        f"<td>{item['points']:g} / {item['max_points']:g}</td>"
        f"<td>{_esc(item['detail'])}</td></tr>"
        for item in result.breakdown.values()
    )
    info_rows = [
        ("Name", _or_default(candidate.name)),
        ("Email", _or_default(candidate.email)),
        ("Phone", _or_default(candidate.phone)),
        ("Education", _join(candidate.education, NOT_FOUND)),
        ("Experience", _experience_text(candidate)),
    ]
    info = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in info_rows
    )
    ai_block = (
        f"<h3>AI-generated commentary</h3><p><em>Suggestion, not extracted fact.</em>"
        f"</p><p>{_esc(ai_explanation)}</p>"
        if ai_explanation
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Intelligent Resume Analysis Report</title>
<style>
body {{ font-family: Arial, sans-serif; max-width: 820px; margin: 2rem auto;
        color: #222; }}
h1 {{ border-bottom: 3px solid #2b6cb0; padding-bottom: .4rem; }}
h2 {{ color: #2b6cb0; margin-top: 1.6rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; }}
.score {{ font-size: 2rem; font-weight: bold; }}
.note {{ color: #666; font-size: .85rem; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>INTELLIGENT RESUME ANALYSIS REPORT</h1>
<p>Generated: {_esc(_timestamp(generated_at))}</p>
<h2>Candidate Information</h2>
<table>{info}</table>
<p><strong>Skills:</strong> {_esc(_join(candidate.skills))}</p>
<h2>Job Information</h2>
<table>
<tr><th>Position</th><td>{_esc(job.title)}</td></tr>
<tr><th>Required skills</th><td>{_esc(_join(job.required_skills))}</td></tr>
<tr><th>Preferred skills</th><td>{_esc(_join(job.preferred_skills))}</td></tr>
<tr><th>Minimum experience</th><td>{job.min_experience:g} years</td></tr>
<tr><th>Required education</th>
<td>{_esc(_or_default(job.required_education, 'Not specified'))}</td></tr>
</table>
<h2>Analysis</h2>
<p class="score">{result.score:g} / 100</p>
<table><tr><th>Component</th><th>Points</th><th>Detail</th></tr>{rows}</table>
<p><strong>Matched (required):</strong> {_esc(_join(result.matched_required))}<br>
<strong>Missing (required):</strong> {_esc(_join(result.missing_required))}<br>
<strong>Matched (preferred):</strong> {_esc(_join(result.matched_preferred))}<br>
<strong>Missing (preferred):</strong> {_esc(_join(result.missing_preferred))}</p>
<h2>Recommendation</h2>
<p class="score">{_esc(result.recommendation)}</p>
<h2>Additional Insights</h2>
<h3>Candidate strengths</h3>{_html_list(result.strengths, "None identified")}
<h3>Skill gaps</h3>{_html_list(result.improvements, "None identified")}
<h3>Suggested interview questions ({_esc(questions_source)})</h3>
{_html_list(interview_questions or [], "No questions generated")}
<h3>Explanation of the recommendation</h3><p>{_esc(result.explanation)}</p>
{ai_block}
<p class="note">{_esc(DISCLAIMER)}</p>
</body>
</html>
"""
