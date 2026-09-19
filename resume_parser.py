"""Utilities for extracting structured information from resume text."""

import re
from typing import Iterable, List, Optional


DEFAULT_SKILLS = {
    "agile", "aws", "azure", "c", "c++", "css", "docker", "excel",
    "flask", "git", "html", "java", "javascript", "linux", "mongodb",
    "node.js", "pandas", "php", "postgresql", "python", "react", "rest",
    "sql", "tableau", "tensorflow", "typescript", "word",
}


def _normalise_skill(skill: str) -> str:
    """Return a consistent representation for skill comparisons."""
    return re.sub(r"\s+", " ", skill.strip().lower())


def extract_name(resume_text: str) -> Optional[str]:
    """Extract the candidate name from the first non-empty resume line."""
    ignored_labels = {
        "resume", "curriculum vitae", "cv", "profile", "missing email",
        "missing name", "missing skills",
    }
    for line_number, line in enumerate(resume_text.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.lower() in ignored_labels:
            continue

        header_match = re.match(
            r"^(?:candidate\s+)?name\s*:\s*(.+)$", candidate, re.I
        )
        if header_match:
            candidate = header_match.group(1).strip()
        elif "@" in candidate:
            email_match = re.search(
                r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", candidate, re.I
            )
            if email_match:
                candidate = candidate[:email_match.start()].strip(" ,;|-\t")
            else:
                candidate = re.split(
                    r"\s*(?:\||,|;)\s*|\s+-\s+", candidate, maxsplit=1
                )[0]
        elif ":" in candidate:
            if line_number == 0:
                return None
            continue

        is_name = re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", candidate)
        if is_name and len(candidate.split()) <= 5 and not re.search(r"\d", candidate):
            return candidate

        # On a single-line resume, stop the name before a known skill or
        # the first explicit years-of-experience phrase.
        name_end_positions = []
        for skill in DEFAULT_SKILLS:
            skill_match = re.search(
                r"(?<![a-z0-9+#])" + re.escape(skill) + r"(?![a-z0-9+#])",
                candidate,
                re.I,
            )
            if skill_match:
                name_end_positions.append(skill_match.start())
        experience_match = re.search(
            r"\b\d+(?:\.\d+)?\s*\+?\s*years?\b", candidate, re.I
        )
        if experience_match:
            name_end_positions.append(experience_match.start())
        if name_end_positions:
            name_prefix = candidate[:min(name_end_positions)].strip(" ,;|-\t")
            is_name_prefix = re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", name_prefix)
            if (
                is_name_prefix
                and len(name_prefix.split()) <= 5
                and not re.search(r"\d", name_prefix)
            ):
                return name_prefix
        if line_number == 0:
            return None
    return None


def extract_email(resume_text: str) -> Optional[str]:
    """Extract the first email address, if one is present."""
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", resume_text, re.I)
    return match.group(0) if match else None


def extract_skills(
    resume_text: str, known_skills: Optional[Iterable[str]] = None
) -> List[str]:
    """Extract skills from a skills section and from a small common vocabulary."""
    if not resume_text:
        return []

    vocabulary = {_normalise_skill(skill) for skill in (known_skills or [])}
    vocabulary.update(DEFAULT_SKILLS)
    found = set()
    lowered_text = resume_text.lower()

    for skill in vocabulary:
        pattern = r"(?<![a-z0-9+#])" + re.escape(skill) + r"(?![a-z0-9+#])"
        if re.search(pattern, lowered_text):
            found.add(skill)

    for line in resume_text.splitlines():
        if re.match(r"^\s*(skills?|technologies|technical skills?)\s*:", line, re.I):
            values = line.split(":", 1)[1]
            for value in re.split(r"[,;|]", values):
                value = _normalise_skill(value.strip(" -*"))
                if value:
                    found.add(value)

    return sorted(found)


def extract_years_experience(resume_text: str) -> float:
    """Extract years of experience, returning zero for missing or invalid data."""
    patterns = (
        r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s*(?:of\s+)?experience",
        r"experience\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*\+?\s*years?",
    )
    for pattern in patterns:
        match = re.search(pattern, resume_text, re.I)
        if match:
            try:
                return max(0.0, float(match.group(1)))
            except ValueError:
                return 0.0
    return 0.0


def parse_resume(
    resume_text: str, known_skills: Optional[Iterable[str]] = None
) -> dict:
    """Parse resume text into JSON-friendly data without raising on bad input."""
    text = resume_text or ""
    return {
        "name": extract_name(text),
        "email": extract_email(text),
        "skills": extract_skills(text, known_skills),
        "years_experience": extract_years_experience(text),
    }
