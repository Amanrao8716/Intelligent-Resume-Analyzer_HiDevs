"""
models.py — Advanced data models with validation, serialization, and type safety.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


class EducationLevel(Enum):
    """Ordered education levels for comparison."""
    UNKNOWN = 0
    HIGH_SCHOOL = 1
    DIPLOMA = 2
    ASSOCIATE = 3
    BACHELOR = 4
    MASTER = 5
    PHD = 6

    @classmethod
    def from_string(cls, s: str) -> "EducationLevel":
        mapping = [
            (r"\bphd\b|\bdoctorate\b",                 cls.PHD),
            (r"\bmaster|\bmsc\b|\bmba\b|\bm\.tech\b",  cls.MASTER),
            (r"\bbachelor|\bbsc\b|\bb\.tech\b|\bb\.e\b|\bb\.eng\b", cls.BACHELOR),
            (r"\bassociate\b",                          cls.ASSOCIATE),
            (r"\bdiploma\b",                            cls.DIPLOMA),
            (r"high school",                            cls.HIGH_SCHOOL),
        ]
        s_lower = s.lower()
        for pattern, level in mapping:
            if re.search(pattern, s_lower):
                return level
        return cls.UNKNOWN

    def label(self) -> str:
        labels = {
            self.UNKNOWN: "Not Specified",
            self.HIGH_SCHOOL: "High School",
            self.DIPLOMA: "Diploma",
            self.ASSOCIATE: "Associate's",
            self.BACHELOR: "Bachelor's",
            self.MASTER: "Master's",
            self.PHD: "PhD",
        }
        return labels[self]


class RecommendationTier(Enum):
    STRONG = "Strong Match — Recommended for Interview"
    GOOD = "Good Match — Consider for Interview"
    PARTIAL = "Partial Match — Review Manually"
    WEAK = "Weak Match — Not Recommended"
    POOR = "Poor Match — Does Not Meet Requirements"

    @classmethod
    def from_score(cls, score: float) -> "RecommendationTier":
        if score >= 80:   return cls.STRONG
        if score >= 65:   return cls.GOOD
        if score >= 50:   return cls.PARTIAL
        if score >= 35:   return cls.WEAK
        return cls.POOR

    @property
    def emoji(self) -> str:
        return {
            self.STRONG:  "🟢",
            self.GOOD:    "🔵",
            self.PARTIAL: "🟡",
            self.WEAK:    "🟠",
            self.POOR:    "🔴",
        }[self]


@dataclass
class WorkExperience:
    """A single work experience entry."""
    company: str = ""
    title: str = ""
    start_year: int = 0
    end_year: Optional[int] = None   # None = present
    description: str = ""

    @property
    def duration_years(self) -> float:
        end = self.end_year or datetime.now().year
        return max(0.0, end - self.start_year)

    def to_dict(self) -> Dict:
        return {
            "company": self.company,
            "title": self.title,
            "start_year": self.start_year,
            "end_year": self.end_year,
            "description": self.description,
            "duration_years": self.duration_years,
        }


@dataclass
class Candidate:
    """Full candidate profile with validation."""
    name: str = "Unknown"
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    location: str = ""
    skills: List[str] = field(default_factory=list)
    experience_years: float = 0.0
    work_history: List[WorkExperience] = field(default_factory=list)
    education: EducationLevel = EducationLevel.UNKNOWN
    education_field: str = ""
    certifications: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    summary: str = ""
    parse_confidence: float = 0.0   # 0–1, how confident the parser is
    raw_text: str = ""

    def __post_init__(self):
        self.skills = [s.lower().strip() for s in self.skills if s.strip()]
        self.skills = sorted(set(self.skills))

    @property
    def skill_count(self) -> int:
        return len(self.skills)

    @property
    def most_recent_title(self) -> str:
        if not self.work_history:
            return "N/A"
        return self.work_history[0].title

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["education"] = self.education.label()
        d["education_value"] = self.education.value
        d["work_history"] = [w.to_dict() for w in self.work_history]
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> "Candidate":
        edu_str = data.pop("education", "Not Specified")
        data.pop("education_value", None)
        wh_raw = data.pop("work_history", [])
        data.pop("skill_count", None)
        data.pop("most_recent_title", None)
        work_history = [WorkExperience(**w) for w in wh_raw]
        edu = EducationLevel.from_string(edu_str)
        return cls(education=edu, work_history=work_history, **data)


@dataclass
class JobRequirement:
    """Job posting with rich requirement fields."""
    title: str
    required_skills: List[str]
    preferred_skills: List[str] = field(default_factory=list)
    min_experience: float = 0.0
    max_experience: Optional[float] = None
    education_required: EducationLevel = EducationLevel.BACHELOR
    department: str = ""
    location: str = ""
    remote: bool = False
    description: str = ""
    salary_range: str = ""

    def __post_init__(self):
        self.required_skills = [s.lower().strip() for s in self.required_skills]
        self.preferred_skills = [s.lower().strip() for s in self.preferred_skills]

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["education_required"] = self.education_required.label()
        return d


@dataclass
class ScoreBreakdown:
    """Granular score breakdown for transparency."""
    skills_required_score: float = 0.0
    skills_preferred_score: float = 0.0
    experience_score: float = 0.0
    education_score: float = 0.0
    certifications_bonus: float = 0.0
    # Weighted composite
    skills_total: float = 0.0
    experience_total: float = 0.0
    education_total: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MatchResult:
    """Complete match result with breakdown and metadata."""
    candidate_name: str
    job_title: str
    overall_score: float
    breakdown: ScoreBreakdown
    matched_required_skills: List[str]
    matched_preferred_skills: List[str]
    missing_required_skills: List[str]
    recommendation: RecommendationTier
    strengths: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["recommendation"] = self.recommendation.value
        d["recommendation_emoji"] = self.recommendation.emoji
        d["breakdown"] = self.breakdown.to_dict()
        return d

    @property
    def is_recommended(self) -> bool:
        return self.recommendation in (RecommendationTier.STRONG, RecommendationTier.GOOD)


@dataclass
class AnalyticsReport:
    """Aggregate analytics across a batch of candidates."""
    job_title: str
    total_candidates: int
    recommended_count: int
    avg_score: float
    score_distribution: Dict[str, int]   # tier → count
    top_candidate: str
    most_common_skills: List[str]
    most_missing_skills: List[str]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)
