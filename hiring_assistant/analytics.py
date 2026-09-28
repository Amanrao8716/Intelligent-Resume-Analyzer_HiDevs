"""
analytics.py — Aggregate analytics across a candidate pool.
"""

from __future__ import annotations
from collections import Counter
from typing import List

from .models import MatchResult, AnalyticsReport, RecommendationTier


class AnalyticsEngine:
    """Computes batch statistics for recruiter dashboards."""

    def analyze(self, results: List[MatchResult], job_title: str) -> AnalyticsReport:
        """
        Generate an analytics summary for a set of match results.

        Args:
            results: List of MatchResult objects (same job).
            job_title: The job being analyzed.

        Returns:
            AnalyticsReport with aggregated stats.
        """
        if not results:
            raise ValueError("Cannot analyze an empty result set.")

        scores = [r.overall_score for r in results]
        avg_score = round(sum(scores) / len(scores), 2)

        recommended = [r for r in results if r.is_recommended]
        top = max(results, key=lambda r: r.overall_score)

        # Score distribution by tier
        distribution: dict[str, int] = {tier.name: 0 for tier in RecommendationTier}
        for r in results:
            distribution[r.recommendation.name] += 1

        # Most common matched skills
        all_matched = [s for r in results for s in r.matched_required_skills]
        top_skills = [skill for skill, _ in Counter(all_matched).most_common(10)]

        # Most frequently missing skills
        all_missing = [s for r in results for s in r.missing_required_skills]
        top_missing = [skill for skill, _ in Counter(all_missing).most_common(10)]

        return AnalyticsReport(
            job_title=job_title,
            total_candidates=len(results),
            recommended_count=len(recommended),
            avg_score=avg_score,
            score_distribution=distribution,
            top_candidate=top.candidate_name,
            most_common_skills=top_skills,
            most_missing_skills=top_missing,
        )
