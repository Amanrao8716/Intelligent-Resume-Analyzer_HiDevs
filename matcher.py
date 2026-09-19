"""Candidate-to-job matching logic."""

import re
from typing import Iterable, List


def normalise_skill(skill: str) -> str:
    """Normalise whitespace and case so skills can be compared reliably."""
    return re.sub(r"\s+", " ", str(skill).strip().lower())


def match_resume(
    candidate_skills: Iterable[str],
    required_skills: Iterable[str],
    candidate_years: float,
    required_years: float,
) -> dict:
    """Calculate a score weighted 70% for skills and 30% for experience."""
    candidate = {normalise_skill(skill) for skill in candidate_skills if str(skill).strip()}
    required = [normalise_skill(skill) for skill in required_skills if str(skill).strip()]
    required = list(dict.fromkeys(required))

    matched = sorted(skill for skill in required if skill in candidate)
    missing = sorted(skill for skill in required if skill not in candidate)
    skill_score = (len(matched) / len(required) * 100) if required else 100.0

    try:
        candidate_years = max(0.0, float(candidate_years))
    except (TypeError, ValueError):
        candidate_years = 0.0
    try:
        required_years = max(0.0, float(required_years))
    except (TypeError, ValueError):
        required_years = 0.0

    experience_score = (
        min(candidate_years / required_years, 1.0) * 100
        if required_years
        else 100.0
    )
    match_score = round(skill_score * 0.7 + experience_score * 0.3)

    if match_score >= 75:
        recommendation = "Strongly recommend"
    elif match_score >= 50:
        recommendation = "Consider for interview"
    else:
        recommendation = "Do not recommend"

    return {
        "match_score": match_score,
        "skill_score": round(skill_score, 2),
        "experience_score": round(experience_score, 2),
        "matched_skills": matched,
        "missing_skills": missing,
        "hiring_recommendation": recommendation,
    }
