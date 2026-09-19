"""Report creation and JSON persistence helpers."""

import json
from pathlib import Path
from typing import Any, Dict, Optional


def save_json(data: Dict[str, Any], file_path: str) -> bool:
    """Save a dictionary as readable JSON and report failures to the caller."""
    try:
        Path(file_path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except (OSError, TypeError, ValueError):
        return False


def load_json(file_path: str) -> Optional[Dict[str, Any]]:
    """Load a JSON object, returning None for missing or invalid files."""
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def create_report(resume_data: Dict[str, Any], match_data: Dict[str, Any]) -> Dict[str, Any]:
    """Combine candidate details and matching results into the final report."""
    return {
        "candidate_name": resume_data.get("name") or "Not provided",
        "email": resume_data.get("email") or "Not provided",
        "experience": resume_data.get("years_experience", 0),
        "match_score": match_data.get("match_score", 0),
        "matched_skills": match_data.get("matched_skills", []),
        "missing_skills": match_data.get("missing_skills", []),
        "hiring_recommendation": match_data.get(
            "hiring_recommendation", "Unable to determine"
        ),
    }


def format_report(report: Dict[str, Any]) -> str:
    """Format the final report for terminal output."""
    matched = ", ".join(report["matched_skills"]) or "None"
    missing = ", ".join(report["missing_skills"]) or "None"
    return (
        "\n" + "=" * 52 + "\n"
        "INTELLIGENT RESUME ANALYZER REPORT\n"
        + "=" * 52 + "\n"
        f"Candidate: {report['candidate_name']}\n"
        f"Email: {report['email']}\n"
        f"Experience: {report['experience']} years\n"
        f"Match score: {report['match_score']}/100\n"
        f"Matched skills: {matched}\n"
        f"Missing skills: {missing}\n"
        f"Recommendation: {report['hiring_recommendation']}\n"
        + "=" * 52
    )
