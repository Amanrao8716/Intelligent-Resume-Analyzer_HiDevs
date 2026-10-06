"""Data models: Candidate, Job and MatchResult.

Defaults for missing information are documented on each field:
``None`` means "not found in the resume"; an empty list means "nothing found".
Nothing is ever invented.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from utils import ValidationError, education_rank

MAX_EXPERIENCE_YEARS = 60.0


def _require_string_list(value: Any, field_name: str) -> List[str]:
    """Return ``value`` if it is a list of strings, else raise ValidationError."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationError(f"'{field_name}' must be a list of text values.")
    return list(value)


def _validate_years(value: Any, field_name: str) -> Optional[float]:
    """Validate a years-of-experience value (None is allowed)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"'{field_name}' must be a number of years.")
    if math.isnan(value) or value < 0 or value > MAX_EXPERIENCE_YEARS:
        raise ValidationError(
            f"'{field_name}' must be between 0 and {MAX_EXPERIENCE_YEARS:g} years."
        )
    return float(value)


@dataclass
class Candidate:
    """Information extracted from one resume.

    Attributes:
        name: Candidate name, or None if it could not be found.
        email: E-mail address, or None.
        phone: Phone number, or None.
        skills: Canonical technical skills found (no duplicates).
        soft_skills: Canonical soft skills found (no duplicates).
        experience: Total years of experience, or None if not stated/derivable.
        education: Education lines found (degree, institution).
        certifications: Certifications found.
        projects: Project titles found.
        source_file: Original file name (not the path), if known.
    """

    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    soft_skills: List[str] = field(default_factory=list)
    experience: Optional[float] = None
    education: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    projects: List[str] = field(default_factory=list)
    source_file: Optional[str] = None

    def validate(self) -> None:
        """Raise ValidationError if any field has an unusable type or value."""
        for field_name in (
            "skills",
            "soft_skills",
            "education",
            "certifications",
            "projects",
        ):
            _require_string_list(getattr(self, field_name), field_name)
        _validate_years(self.experience, "experience")
        for field_name in ("name", "email", "phone", "source_file"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise ValidationError(f"'{field_name}' must be text or None.")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Candidate":
        """Build a validated Candidate from a dictionary (e.g. loaded JSON)."""
        if not isinstance(data, Mapping):
            raise ValidationError("Candidate data must be a JSON object.")
        known = {name for name in cls.__dataclass_fields__}
        candidate = cls(**{k: v for k, v in data.items() if k in known})
        candidate.validate()
        return candidate


@dataclass
class Job:
    """Job requirements used for matching.

    Attributes:
        title: Position title (required).
        required_skills: Must-have skills.
        preferred_skills: Nice-to-have skills.
        min_experience: Minimum years of experience (0 = no requirement).
        required_education: e.g. "Bachelor's", "Master's" or None.
        job_description: Free-text description (optional).
    """

    title: str = ""
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    min_experience: float = 0.0
    required_education: Optional[str] = None
    job_description: str = ""

    def validate(self) -> None:
        """Raise ValidationError if the job cannot be used for matching."""
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError("The job title is required.")
        required = _require_string_list(self.required_skills, "required_skills")
        preferred = _require_string_list(self.preferred_skills, "preferred_skills")
        minimum = _validate_years(self.min_experience, "min_experience") or 0.0
        if self.required_education is not None and not isinstance(
            self.required_education, str
        ):
            raise ValidationError("'required_education' must be text or None.")
        if not isinstance(self.job_description, str):
            raise ValidationError("'job_description' must be text.")
        education = (self.required_education or "").strip()
        if education and education_rank(education) == 0:
            raise ValidationError(
                f"Unrecognized education requirement '{education}'. "
                "Use Diploma, Bachelor's, Master's or PhD."
            )
        has_requirement = any(
            (
                [s for s in required if s.strip()],
                [s for s in preferred if s.strip()],
                minimum > 0,
                education,
            )
        )
        if not has_requirement:
            raise ValidationError(
                "The job has no requirements. Add at least one required skill, "
                "preferred skill, minimum experience or education requirement."
            )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Job":
        """Build a validated Job from a dictionary (e.g. loaded JSON)."""
        if not isinstance(data, Mapping):
            raise ValidationError("Job data must be a JSON object.")
        known = {name for name in cls.__dataclass_fields__}
        job = cls(**{k: v for k, v in data.items() if k in known})
        job.validate()
        return job


@dataclass
class MatchResult:
    """Outcome of matching one candidate against one job.

    ``breakdown`` has one entry per scoring component (required_skills,
    preferred_skills, experience, education) with its weight, points and detail.
    """

    score: float
    recommendation: str
    breakdown: Dict[str, Dict[str, Any]]
    matched_required: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    matched_preferred: List[str] = field(default_factory=list)
    missing_preferred: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MatchResult":
        """Rebuild a MatchResult from saved JSON."""
        if not isinstance(data, Mapping):
            raise ValidationError("Match result data must be a JSON object.")
        try:
            known = {name for name in cls.__dataclass_fields__}
            return cls(**{k: v for k, v in data.items() if k in known})
        except TypeError as exc:
            raise ValidationError("Saved match result is missing fields.") from exc
