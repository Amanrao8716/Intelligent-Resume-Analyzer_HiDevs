"""
file_manager.py — Robust file I/O: JSON persistence, batch operations, exports.
"""

from __future__ import annotations
import json
import os
import logging
from pathlib import Path
from typing import List, Union

from .models import Candidate, JobRequirement, MatchResult, AnalyticsReport

logger = logging.getLogger(__name__)


class FileManager:
    """
    Handles all persistence:
      - Candidate profiles (JSON)
      - Match results (JSON)
      - Analytics reports (JSON)
      - Text reports (.txt)
      - HTML reports (.html)
      - Batch resume loading
    """

    def __init__(self, base_dir: Union[str, Path] = "output"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────
    #  SAVE
    # ──────────────────────────────────────────────────

    def save_candidate(self, candidate: Candidate, filename: str = "") -> Path:
        if not filename:
            filename = f"{self._safe(candidate.name)}_profile.json"
        path = self._path(filename)
        self._write_json(candidate.to_dict(), path)
        return path

    def save_results(self, results: List[MatchResult], filename: str) -> Path:
        path = self._path(filename)
        self._write_json([r.to_dict() for r in results], path)
        return path

    def save_analytics(self, report: AnalyticsReport, filename: str = "") -> Path:
        if not filename:
            filename = f"{self._safe(report.job_title)}_analytics.json"
        path = self._path(filename)
        self._write_json(report.to_dict(), path)
        return path

    def save_text_report(self, text: str, filename: str) -> Path:
        path = self._path(filename)
        path.write_text(text, encoding="utf-8")
        logger.info("Saved text report → %s", path)
        return path

    def save_html_report(self, html: str, filename: str) -> Path:
        path = self._path(filename)
        path.write_text(html, encoding="utf-8")
        logger.info("Saved HTML report → %s", path)
        return path

    # ──────────────────────────────────────────────────
    #  LOAD
    # ──────────────────────────────────────────────────

    def load_candidate(self, filepath: Union[str, Path]) -> Candidate:
        data = self._read_json(filepath)
        return Candidate.from_dict(data)

    def load_results(self, filepath: Union[str, Path]) -> List[MatchResult]:
        data = self._read_json(filepath)
        loaded = []
        for item in data:
            item["recommendation"] = self._find_tier(item.get("recommendation", ""))
            from .models import ScoreBreakdown, RecommendationTier
            bd = item.pop("breakdown", {})
            item.pop("recommendation_emoji", None)
            item.pop("is_recommended", None)
            breakdown = ScoreBreakdown(**bd)
            loaded.append(MatchResult(breakdown=breakdown, **item))
        return loaded

    def load_resume_text(self, filepath: Union[str, Path]) -> str:
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Resume file not found: {p}")
        return p.read_text(encoding="utf-8")

    def load_all_resumes(self, directory: Union[str, Path]) -> List[str]:
        """Load all .txt files from a directory as resume texts."""
        d = Path(directory)
        texts = []
        for f in sorted(d.glob("*.txt")):
            try:
                texts.append(f.read_text(encoding="utf-8"))
                logger.debug("Loaded resume: %s", f.name)
            except IOError as e:
                logger.warning("Could not read %s: %s", f.name, e)
        return texts

    # ──────────────────────────────────────────────────
    #  INTERNALS
    # ──────────────────────────────────────────────────

    def _path(self, filename: str) -> Path:
        return self.base_dir / filename

    def _safe(self, name: str) -> str:
        import re
        return re.sub(r"\W+", "_", name.lower()).strip("_")

    def _write_json(self, data, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info("Saved JSON → %s", path)

    def _read_json(self, filepath: Union[str, Path]):
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _find_tier(self, value: str):
        from .models import RecommendationTier
        for tier in RecommendationTier:
            if tier.value == value:
                return tier
        return RecommendationTier.POOR
