"""
matcher.py — Advanced matching engine with configurable weights,
             skill-taxonomy-aware scoring, and gap analysis.
"""

from __future__ import annotations
import logging
from typing import List, Tuple, Dict
from dataclasses import dataclass

from .models import (
    Candidate, JobRequirement, MatchResult,
    ScoreBreakdown, RecommendationTier, EducationLevel
)
from .parser import SKILL_TAXONOMY

logger = logging.getLogger(__name__)


@dataclass
class MatchWeights:
    """Configurable weight distribution for the composite score."""
    skills: float = 0.55
    experience: float = 0.30
    education: float = 0.15

    def __post_init__(self):
        total = self.skills + self.experience + self.education
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total:.2f}")


class MatchingEngine:
    """
    Advanced candidate-job matching engine.

    Scoring model:
      • Required skills   → 70% of skills score
      • Preferred skills  → 30% of skills score
      • Certification bonus → up to +5 bonus points
      • Experience score  → tiered, with overqualification awareness
      • Education score   → level comparison with partial credit
    """

    DEFAULT_WEIGHTS = MatchWeights()

    def __init__(self, weights: MatchWeights = None):
        self.weights = weights or self.DEFAULT_WEIGHTS

    # ──────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────

    def match(self, candidate: Candidate, job: JobRequirement) -> MatchResult:
        """
        Calculate a comprehensive match result.

        Args:
            candidate: Parsed candidate profile.
            job: Job requirements.

        Returns:
            MatchResult with full score breakdown and narrative.
        """
        breakdown = ScoreBreakdown()

        # 1. Skills scoring
        (
            breakdown.skills_required_score,
            breakdown.skills_preferred_score,
            matched_req,
            matched_pref,
            missing_req,
        ) = self._score_skills(candidate, job)

        breakdown.certifications_bonus = self._certification_bonus(candidate, job)

        skills_raw = (
            breakdown.skills_required_score * 0.70
            + breakdown.skills_preferred_score * 0.30
        )
        breakdown.skills_total = min(100.0, skills_raw + breakdown.certifications_bonus)

        # 2. Experience scoring
        breakdown.experience_score = self._score_experience(candidate, job)
        breakdown.experience_total = breakdown.experience_score

        # 3. Education scoring
        breakdown.education_score = self._score_education(candidate, job)
        breakdown.education_total = breakdown.education_score

        # 4. Composite
        breakdown.overall = round(
            breakdown.skills_total     * self.weights.skills
            + breakdown.experience_total * self.weights.experience
            + breakdown.education_total  * self.weights.education,
            2,
        )

        recommendation = RecommendationTier.from_score(breakdown.overall)

        strengths = self._build_strengths(candidate, job, breakdown, matched_req)
        gaps = self._build_gaps(candidate, job, breakdown, missing_req)

        logger.debug(
            "Match: %s → %s = %.1f",
            candidate.name, job.title, breakdown.overall
        )

        return MatchResult(
            candidate_name=candidate.name,
            job_title=job.title,
            overall_score=breakdown.overall,
            breakdown=breakdown,
            matched_required_skills=matched_req,
            matched_preferred_skills=matched_pref,
            missing_required_skills=missing_req,
            recommendation=recommendation,
            strengths=strengths,
            gaps=gaps,
        )

    def batch_match(
        self, candidates: List[Candidate], job: JobRequirement
    ) -> List[MatchResult]:
        """Match multiple candidates to a job and return ranked results."""
        results = [self.match(c, job) for c in candidates]
        results.sort(key=lambda r: r.overall_score, reverse=True)
        return results

    # ──────────────────────────────────────────────────
    #  SCORING HELPERS
    # ──────────────────────────────────────────────────

    def _score_skills(
        self, candidate: Candidate, job: JobRequirement
    ) -> Tuple[float, float, List[str], List[str], List[str]]:
        """
        Returns:
            (required_score, preferred_score, matched_req, matched_pref, missing_req)
        """
        cand_skills = set(candidate.skills)
        required = set(job.required_skills)
        preferred = set(job.preferred_skills)

        # Direct matches
        matched_req = sorted(cand_skills & required)
        matched_pref = sorted(cand_skills & preferred)
        missing_req = sorted(required - cand_skills)

        # Fuzzy taxonomy expansion: skill aliases & related terms
        for skill in list(missing_req):
            domain = self._get_skill_domain(skill)
            if domain:
                domain_skills = set(SKILL_TAXONOMY.get(domain, []))
                if cand_skills & domain_skills:
                    # Candidate has adjacent skills — partial credit
                    matched_req.append(f"{skill} (adjacent)")
                    missing_req.remove(skill)

        req_score = (len(matched_req) / max(len(required), 1)) * 100
        pref_score = (len(matched_pref) / max(len(preferred), 1)) * 100 if preferred else 100.0

        return (
            round(min(req_score, 100), 2),
            round(min(pref_score, 100), 2),
            matched_req, matched_pref, missing_req
        )

    def _certification_bonus(self, candidate: Candidate, job: JobRequirement) -> float:
        """Award bonus points for relevant certifications (max 5)."""
        if not candidate.certifications:
            return 0.0
        cert_text = " ".join(c.lower() for c in candidate.certifications)
        bonus = 0.0
        for skill in job.required_skills + job.preferred_skills:
            if skill.lower() in cert_text:
                bonus += 1.0
        return min(bonus, 5.0)

    def _score_experience(self, candidate: Candidate, job: JobRequirement) -> float:
        """
        Tiered experience scoring with overqualification handling.
        """
        years = candidate.experience_years
        required = job.min_experience

        if required == 0:
            return 100.0

        ratio = years / required

        if job.max_experience and years > job.max_experience:
            # Overqualified — slight penalty
            return 75.0

        if ratio >= 2.0:   return 100.0
        if ratio >= 1.5:   return 97.0
        if ratio >= 1.0:   return 90.0
        if ratio >= 0.80:  return 75.0
        if ratio >= 0.60:  return 58.0
        if ratio >= 0.40:  return 40.0
        return 20.0

    def _score_education(self, candidate: Candidate, job: JobRequirement) -> float:
        """Compare education levels with graceful partial credit."""
        cand_level = candidate.education.value
        req_level = job.education_required.value

        if req_level == 0:
            return 100.0

        gap = cand_level - req_level
        if gap >= 0:    return 100.0
        if gap == -1:   return 65.0
        if gap == -2:   return 40.0
        return 15.0

    def _get_skill_domain(self, skill: str) -> str:
        """Return the taxonomy domain a skill belongs to, or empty string."""
        for domain, skills in SKILL_TAXONOMY.items():
            if skill in skills:
                return domain
        return ""

    def _build_strengths(
        self,
        candidate: Candidate,
        job: JobRequirement,
        breakdown: ScoreBreakdown,
        matched_req: List[str],
    ) -> List[str]:
        """Generate narrative strength bullets."""
        strengths = []
        if breakdown.skills_required_score >= 90:
            strengths.append(f"Covers all required technical skills for {job.title}.")
        if matched_req:
            core = [s for s in matched_req if "adjacent" not in s][:4]
            if core:
                strengths.append(f"Strong alignment in: {', '.join(core)}.")
        if candidate.experience_years >= job.min_experience * 1.5:
            strengths.append(
                f"Significantly exceeds experience requirement "
                f"({candidate.experience_years:.0f}y vs {job.min_experience}y required)."
            )
        if candidate.education.value > job.education_required.value:
            strengths.append(
                f"Education level exceeds requirement "
                f"({candidate.education.label()} vs {job.education_required.label()} required)."
            )
        if candidate.certifications:
            strengths.append(f"Holds {len(candidate.certifications)} relevant certification(s).")
        return strengths[:5]

    def _build_gaps(
        self,
        candidate: Candidate,
        job: JobRequirement,
        breakdown: ScoreBreakdown,
        missing_req: List[str],
    ) -> List[str]:
        """Generate narrative gap bullets."""
        gaps = []
        if missing_req:
            gaps.append(f"Missing required skills: {', '.join(missing_req[:5])}.")
        if candidate.experience_years < job.min_experience:
            diff = job.min_experience - candidate.experience_years
            gaps.append(f"Under-experienced by ~{diff:.0f} year(s).")
        if candidate.education.value < job.education_required.value:
            gaps.append(
                f"Education gap: has {candidate.education.label()}, "
                f"requires {job.education_required.label()}."
            )
        return gaps[:4]
