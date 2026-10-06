"""Deterministic, explainable candidate-to-job matching.

Scoring model (100 points):

    Required skills   50   share of required skills the candidate has
    Preferred skills  15   share of preferred skills the candidate has
    Experience        25   min(candidate years / required years, 1)
    Education         10   candidate level / required level (capped at 1)

If a job does not specify a component (no preferred skills, no minimum
experience, no education requirement ...) that component is skipped and the
remaining weights are scaled up so the total is still 100. This avoids both
division by zero and giving "free" points for requirements that do not exist.

No randomness and no AI are involved: identical inputs always give identical
scores.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from models import Candidate, Job, MatchResult
from utils import (
    EDUCATION_LABELS,
    SkillDictionary,
    ValidationError,
    education_rank,
    get_logger,
    unique_preserve_order,
)

logger = get_logger("matcher")

WEIGHTS: Dict[str, float] = {
    "required_skills": 50.0,
    "preferred_skills": 15.0,
    "experience": 25.0,
    "education": 10.0,
}
RECOMMENDATION_BANDS: Tuple[Tuple[float, str], ...] = (
    (80.0, "Strongly Recommend"),
    (60.0, "Recommend"),
    (40.0, "Consider"),
    (0.0, "Not Recommended"),
)
COMPONENT_LABELS = {
    "required_skills": "Required skills",
    "preferred_skills": "Preferred skills",
    "experience": "Experience",
    "education": "Education",
}


def get_recommendation(score: float) -> str:
    """Map a 0-100 score to a recommendation label.

    Raises:
        ValidationError: if the score is not a number between 0 and 100.
    """
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValidationError("Score must be a number.")
    if math.isnan(score) or not 0 <= score <= 100:
        raise ValidationError("Score must be between 0 and 100.")
    for threshold, label in RECOMMENDATION_BANDS:
        if score >= threshold:
            return label
    return RECOMMENDATION_BANDS[-1][1]  # pragma: no cover - 0 always matches


def _normalize_unique(skills: List[str], dictionary: SkillDictionary) -> List[str]:
    """Normalize skill names and drop duplicates (and empty entries)."""
    normalized = (dictionary.normalize(skill) for skill in skills)
    return unique_preserve_order(skill for skill in normalized if skill)


def _skill_ratio(required: List[str], owned: set) -> Tuple[float, List[str], List[str]]:
    """Return (coverage ratio, matched, missing); ratio is 0 for no requirements."""
    matched = [skill for skill in required if skill in owned]
    missing = [skill for skill in required if skill not in owned]
    ratio = len(matched) / len(required) if required else 0.0
    return ratio, matched, missing


def score_education(
    candidate_education: List[str], required_education: Optional[str]
) -> Tuple[float, int, int]:
    """Score education 0-1 and return (ratio, candidate_rank, required_rank).

    Rules: levels are Diploma=1, Bachelor's=2, Master's=3, PhD=4. Meeting or
    exceeding the required level gives 1.0; otherwise the ratio is
    candidate level / required level (0 when no degree was found).
    """
    required_rank = education_rank(required_education)
    candidate_rank = max(
        (education_rank(line) for line in candidate_education), default=0
    )
    if required_rank == 0:
        return 0.0, candidate_rank, 0
    return min(candidate_rank / required_rank, 1.0), candidate_rank, required_rank


def score_experience(
    candidate_years: Optional[float], minimum_years: float
) -> Tuple[float, float]:
    """Score experience 0-1 and return (ratio, years_used).

    Unknown experience (None) is treated as 0 years; it is never guessed.
    """
    years = candidate_years or 0.0
    if minimum_years <= 0:
        return 0.0, years
    return min(years / minimum_years, 1.0), years


def score_candidate(
    candidate: Candidate,
    job: Job,
    skill_dictionary: Optional[SkillDictionary] = None,
) -> MatchResult:
    """Compare a candidate with a job and return a detailed MatchResult.

    Raises:
        ValidationError: if the candidate or job data is invalid.
    """
    candidate.validate()
    job.validate()
    dictionary = skill_dictionary or SkillDictionary.combined()

    owned = {
        dictionary.normalize(skill)
        for skill in [*candidate.skills, *candidate.soft_skills]
        if skill.strip()
    }
    required = _normalize_unique(job.required_skills, dictionary)
    required_set = set(required)
    # A skill listed as both required and preferred is only counted once.
    preferred = [
        skill
        for skill in _normalize_unique(job.preferred_skills, dictionary)
        if skill not in required_set
    ]

    req_ratio, matched_req, missing_req = _skill_ratio(required, owned)
    pref_ratio, matched_pref, missing_pref = _skill_ratio(preferred, owned)
    exp_ratio, years_used = score_experience(candidate.experience, job.min_experience)
    edu_ratio, candidate_rank, required_rank = score_education(
        candidate.education, job.required_education
    )

    components = {
        "required_skills": (bool(required), req_ratio),
        "preferred_skills": (bool(preferred), pref_ratio),
        "experience": (job.min_experience > 0, exp_ratio),
        "education": (required_rank > 0, edu_ratio),
    }
    active_weight = sum(WEIGHTS[name] for name, (on, _) in components.items() if on)
    scale = 100.0 / active_weight if active_weight else 0.0

    breakdown: Dict[str, Dict[str, object]] = {}
    total = 0.0
    for name, (applicable, ratio) in components.items():
        max_points = WEIGHTS[name] * scale if applicable else 0.0
        points = ratio * max_points
        total += points
        breakdown[name] = {
            "label": COMPONENT_LABELS[name],
            "applicable": applicable,
            "base_weight": WEIGHTS[name],
            "max_points": round(max_points, 2),
            "points": round(points, 2),
            "coverage": round(ratio, 4),
            "detail": "",
        }

    breakdown["required_skills"]["detail"] = (
        f"{len(matched_req)} of {len(required)} required skills matched"
        if required
        else "No required skills specified (component skipped)"
    )
    breakdown["preferred_skills"]["detail"] = (
        f"{len(matched_pref)} of {len(preferred)} preferred skills matched"
        if preferred
        else "No preferred skills specified (component skipped)"
    )
    if job.min_experience > 0:
        known = "" if candidate.experience is not None else " (not stated in resume)"
        breakdown["experience"][
            "detail"
        ] = f"{years_used:g} years{known} vs {job.min_experience:g} required"
    else:
        breakdown["experience"][
            "detail"
        ] = "No minimum experience specified (component skipped)"
    if required_rank:
        breakdown["education"]["detail"] = (
            f"Candidate: {EDUCATION_LABELS[candidate_rank]}; "
            f"required: {EDUCATION_LABELS[required_rank]}"
        )
    else:
        breakdown["education"][
            "detail"
        ] = "No education requirement specified (component skipped)"

    score = round(min(max(total, 0.0), 100.0), 2)
    recommendation = get_recommendation(score)
    strengths, improvements = _build_insights(
        matched_req,
        missing_req,
        matched_pref,
        missing_pref,
        candidate,
        job,
        (exp_ratio, years_used),
        (edu_ratio, candidate_rank, required_rank),
    )
    result = MatchResult(
        score=score,
        recommendation=recommendation,
        breakdown=breakdown,
        matched_required=matched_req,
        missing_required=missing_req,
        matched_preferred=matched_pref,
        missing_preferred=missing_pref,
        strengths=strengths,
        improvements=improvements,
    )
    result.explanation = build_explanation(result, job)
    logger.info("Scored candidate: %.2f (%s)", score, recommendation)
    return result


def _build_insights(
    matched_req: List[str],
    missing_req: List[str],
    matched_pref: List[str],
    missing_pref: List[str],
    candidate: Candidate,
    job: Job,
    experience: Tuple[float, float],
    education: Tuple[float, int, int],
) -> Tuple[List[str], List[str]]:
    """Create strengths and improvement areas from the scoring facts."""
    exp_ratio, years = experience
    edu_ratio, candidate_rank, required_rank = education
    strengths: List[str] = []
    improvements: List[str] = []

    total_required = len(matched_req) + len(missing_req)
    if matched_req:
        strengths.append(
            f"Matches {len(matched_req)} of {total_required} required skills: "
            f"{', '.join(matched_req)}."
        )
    if missing_req:
        improvements.append(f"Missing required skills: {', '.join(missing_req)}.")
    if matched_pref:
        strengths.append(f"Has preferred skills: {', '.join(matched_pref)}.")
    if missing_pref:
        improvements.append(
            f"Could strengthen the profile with: {', '.join(missing_pref)}."
        )
    if job.min_experience > 0:
        if exp_ratio >= 1.0:
            strengths.append(
                f"Meets the experience requirement ({years:g} years vs "
                f"{job.min_experience:g} required)."
            )
        elif candidate.experience is None:
            improvements.append(
                "Years of experience were not found in the resume; "
                f"{job.min_experience:g} years are required."
            )
        else:
            improvements.append(
                f"Has {years:g} years of experience; the role asks for "
                f"{job.min_experience:g}."
            )
    if required_rank:
        if edu_ratio >= 1.0:
            strengths.append(
                f"Education meets the requirement ({EDUCATION_LABELS[candidate_rank]})."
            )
        else:
            improvements.append(
                f"Education requirement is {EDUCATION_LABELS[required_rank]}; "
                f"found: {EDUCATION_LABELS[candidate_rank]}."
            )
    if candidate.certifications:
        strengths.append(f"Lists {len(candidate.certifications)} certification(s).")
    if candidate.projects:
        strengths.append(f"Lists {len(candidate.projects)} project(s).")
    return strengths, improvements


def build_explanation(result: MatchResult, job: Job) -> str:
    """Write a plain-English explanation of how the score was reached."""
    parts = []
    for name, data in result.breakdown.items():
        if data["applicable"]:
            parts.append(
                f"{data['label']}: {data['points']:g}/{data['max_points']:g} "
                f"({data['detail']})"
            )
    skipped = [d["label"] for d in result.breakdown.values() if not d["applicable"]]
    text = (
        f"The candidate scored {result.score:g}/100 for '{job.title}'. "
        + "; ".join(parts)
        + "."
    )
    if skipped:
        text += (
            f" Skipped (not specified by the job): {', '.join(skipped)}; "
            "the remaining weights were scaled to total 100."
        )
    text += (
        f" A score of {result.score:g} falls in the '{result.recommendation}' band "
        "(80-100 Strongly Recommend, 60-79 Recommend, 40-59 Consider, "
        "0-39 Not Recommended). This is decision support for a recruiter, "
        "not a final hiring decision."
    )
    return text
