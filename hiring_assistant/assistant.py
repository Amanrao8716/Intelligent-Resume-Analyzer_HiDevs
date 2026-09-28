"""
assistant.py — HiringAssistant: the top-level orchestrator.
               Ties parser, matcher, reporter, analytics, and file_manager together.
"""

from __future__ import annotations
import logging
from typing import List, Tuple, Optional
from pathlib import Path

from .models import Candidate, JobRequirement, MatchResult, AnalyticsReport
from .parser import ResumeParser
from .matcher import MatchingEngine, MatchWeights
from .reporter import ReportGenerator
from .analytics import AnalyticsEngine
from .file_manager import FileManager

logger = logging.getLogger(__name__)


class HiringAssistant:
    """
    High-level API for the Smart Hiring Assistant.

    Usage:
        assistant = HiringAssistant(output_dir="my_output")
        candidate, results = assistant.process_resume(resume_text, [job1, job2])
        ranked = assistant.rank_candidates([r1, r2, r3], job)
    """

    def __init__(
        self,
        output_dir: str = "output",
        weights: Optional[MatchWeights] = None,
        custom_skills: Optional[List[str]] = None,
        log_level: int = logging.INFO,
    ):
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
        self.parser   = ResumeParser(custom_skills=custom_skills)
        self.engine   = MatchingEngine(weights=weights)
        self.reporter = ReportGenerator()
        self.analytics = AnalyticsEngine()
        self.fm       = FileManager(base_dir=output_dir)
        self.output_dir = Path(output_dir)

    # ──────────────────────────────────────────────────
    #  SINGLE CANDIDATE PIPELINE
    # ──────────────────────────────────────────────────

    def process_resume(
        self,
        resume_text: str,
        jobs: List[JobRequirement],
        save: bool = True,
        generate_html: bool = True,
    ) -> Tuple[Candidate, List[MatchResult]]:
        """
        Full pipeline for one candidate: parse → match → report → save.

        Returns:
            (Candidate, list of MatchResult sorted by score descending)
        """
        candidate = self.parser.parse(resume_text)
        results = sorted(
            [self.engine.match(candidate, job) for job in jobs],
            key=lambda r: r.overall_score, reverse=True
        )

        txt_report = self.reporter.candidate_report_text(candidate, results)
        print(txt_report)

        if save:
            safe = self._safe_name(candidate.name)
            self.fm.save_candidate(candidate, f"{safe}_profile.json")
            self.fm.save_results(results, f"{safe}_results.json")
            self.fm.save_text_report(txt_report, f"{safe}_report.txt")
            if generate_html:
                html = self.reporter.candidate_report_html(candidate, results)
                self.fm.save_html_report(html, f"{safe}_report.html")

        return candidate, results

    def process_resume_file(
        self, filepath: str, jobs: List[JobRequirement], **kwargs
    ) -> Tuple[Candidate, List[MatchResult]]:
        """Load resume from file and run the full pipeline."""
        text = self.fm.load_resume_text(filepath)
        return self.process_resume(text, jobs, **kwargs)

    # ──────────────────────────────────────────────────
    #  BATCH / RANKING PIPELINE
    # ──────────────────────────────────────────────────

    def rank_candidates(
        self,
        resumes: List[str],
        job: JobRequirement,
        save: bool = True,
    ) -> List[Tuple[Candidate, MatchResult]]:
        """
        Rank multiple candidates for one job.

        Returns:
            List of (Candidate, MatchResult) sorted best → worst.
        """
        pairs: List[Tuple[Candidate, MatchResult]] = []
        for i, text in enumerate(resumes):
            try:
                c = self.parser.parse(text)
                r = self.engine.match(c, job)
                pairs.append((c, r))
            except ValueError as e:
                logger.warning("Skipping resume #%d: %s", i + 1, e)

        pairs.sort(key=lambda p: p[1].overall_score, reverse=True)
        all_results = [r for _, r in pairs]

        analytics = self.analytics.analyze(all_results, job.title)
        txt_report = self.reporter.ranking_report_text(all_results, analytics)
        print(txt_report)

        if save:
            safe = self._safe_name(job.title)
            self.fm.save_results(all_results, f"{safe}_ranking.json")
            self.fm.save_analytics(analytics, f"{safe}_analytics.json")
            self.fm.save_text_report(txt_report, f"{safe}_ranking.txt")

        return pairs

    def rank_from_directory(
        self, resume_dir: str, job: JobRequirement, **kwargs
    ) -> List[Tuple[Candidate, MatchResult]]:
        """Load all .txt resumes from a folder and rank them."""
        resumes = self.fm.load_all_resumes(resume_dir)
        if not resumes:
            logger.warning("No .txt resumes found in %s", resume_dir)
            return []
        return self.rank_candidates(resumes, job, **kwargs)

    # ──────────────────────────────────────────────────
    #  UTILITY
    # ──────────────────────────────────────────────────

    def _safe_name(self, name: str) -> str:
        import re
        return re.sub(r"\W+", "_", name.lower()).strip("_")
