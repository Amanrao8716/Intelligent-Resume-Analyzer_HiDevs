"""
parser.py — Advanced resume parser with multi-strategy extraction,
            confidence scoring, and structured work history detection.

FIXES:
  - Bug 1: Education field no longer false-matches skills/words like "Python"
            Now restricted to education section only and uses stricter patterns.
  - Bug 2: Work history company/title extraction was reversed and truncated.
            Now correctly parses "Title – Company (year)" format.
  - Bug 3: Duplicate certifications from overlapping regex patterns.
            Now deduplicates by normalising cert text before adding to set.
"""

from __future__ import annotations
import re
import logging
from typing import List, Tuple, Optional, Dict
from datetime import datetime

from .models import Candidate, WorkExperience, EducationLevel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  SKILL TAXONOMY  (grouped by domain for weighted matching)
# ─────────────────────────────────────────────────────────────

SKILL_TAXONOMY: Dict[str, List[str]] = {
    "languages": [
        "python", "java", "javascript", "typescript", "c++", "c#", "c",
        "ruby", "go", "golang", "rust", "swift", "kotlin", "scala", "r",
        "php", "perl", "matlab", "dart", "elixir", "haskell",
    ],
    "web_frontend": [
        "react", "angular", "vue", "svelte", "next.js", "nuxt.js",
        "html", "css", "sass", "tailwind", "bootstrap", "webpack",
        "redux", "graphql", "rest api", "ui/ux", "figma",
    ],
    "web_backend": [
        "django", "flask", "fastapi", "spring", "node.js", "express",
        "rails", "laravel", "asp.net", "fastify", "gin", "echo",
        "microservices", "grpc", "websockets",
    ],
    "databases": [
        "sql", "mysql", "postgresql", "sqlite", "oracle", "mssql",
        "mongodb", "redis", "cassandra", "dynamodb", "elasticsearch",
        "neo4j", "influxdb", "firebase",
    ],
    "cloud_devops": [
        "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
        "ansible", "jenkins", "github actions", "ci/cd", "linux",
        "bash", "nginx", "apache", "prometheus", "grafana", "helm",
    ],
    "data_ml": [
        "machine learning", "deep learning", "nlp", "computer vision",
        "tensorflow", "pytorch", "scikit-learn", "keras", "pandas",
        "numpy", "matplotlib", "seaborn", "spark", "hadoop",
        "data analysis", "power bi", "tableau", "excel", "airflow",
        "mlflow", "hugging face",
    ],
    "practices": [
        "agile", "scrum", "kanban", "tdd", "bdd", "devops", "git",
        "jira", "confluence", "code review", "system design",
        "object-oriented", "functional programming", "design patterns",
        "api design", "security", "testing", "ci/cd",
    ],
    "soft_skills": [
        "leadership", "communication", "problem solving", "teamwork",
        "mentoring", "project management", "stakeholder management",
    ],
}

# Flattened list for fast lookup
ALL_SKILLS: List[str] = [s for group in SKILL_TAXONOMY.values() for s in group]

# Section header patterns
SECTION_PATTERNS = {
    "summary": re.compile(
        r"^(?:summary|profile|about|objective|overview|professional\s+summary)[:\s]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "skills": re.compile(
        r"^(?:skills?|technical\s+skills?|core\s+competencies|technologies)[:\s]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "experience": re.compile(
        r"^(?:experience|work\s+experience|employment|work\s+history|professional\s+experience)[:\s]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "education": re.compile(
        r"^(?:education|academic|qualifications)[:\s]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "certifications": re.compile(
        r"^(?:certifications?|certificates?|licenses?|courses?)[:\s]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
}

# ── FIX BUG 3: Known cert prefixes for deduplication ──────────────
# Maps a normalised key → canonical full name so overlapping patterns
# (e.g. "AWS Certified Solutions Architect" and "Certified Solutions Architect")
# collapse into one entry.
def _cert_key(cert: str) -> str:
    """Normalise a cert string to a deduplication key."""
    return re.sub(r"\s+", " ", cert.lower().strip())


class ResumeParser:
    """
    Advanced resume parser using multi-strategy NLP-style extraction.

    Strategies (priority order):
      1. Section-aware parsing  — locate named sections first
      2. Pattern matching       — regex for emails, phones, dates, URLs
      3. Heuristic scoring      — estimate parse confidence
    """

    def __init__(self, custom_skills: Optional[List[str]] = None):
        self._skills = ALL_SKILLS.copy()
        if custom_skills:
            self._skills.extend([s.lower().strip() for s in custom_skills])

    # ──────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────

    def parse(self, text: str) -> Candidate:
        """
        Parse raw resume text into a structured Candidate.

        Raises:
            ValueError: If text is empty or too short to parse.
        """
        if not text or len(text.strip()) < 20:
            raise ValueError("Resume text is too short or empty to parse.")

        text = self._normalize(text)
        sections = self._split_sections(text)

        candidate = Candidate()
        candidate.raw_text = text

        candidate.name             = self._extract_name(text)
        candidate.email            = self._extract_email(text)
        candidate.phone            = self._extract_phone(text)
        candidate.linkedin         = self._extract_linkedin(text)
        candidate.github           = self._extract_github(text)
        candidate.location         = self._extract_location(text)
        candidate.skills           = self._extract_skills(text, sections)
        candidate.work_history     = self._extract_work_history(
                                         sections.get("experience", text)
                                     )
        candidate.experience_years = self._calculate_total_experience(
                                         candidate.work_history, text
                                     )
        candidate.education        = self._extract_education_level(text)
        # BUG 1 FIX: pass education section only, not full text
        candidate.education_field  = self._extract_education_field(
                                         sections.get("education", "")
                                     )
        candidate.certifications   = self._extract_certifications(text, sections)
        candidate.languages        = self._extract_languages(text)
        candidate.summary          = self._extract_summary(text, sections)
        candidate.parse_confidence = self._calculate_confidence(candidate)

        logger.info(
            "Parsed candidate '%s' — confidence %.0f%%",
            candidate.name, candidate.parse_confidence * 100,
        )
        return candidate

    def parse_from_file(self, filepath: str) -> Candidate:
        """Parse a resume from a .txt file."""
        try:
            with open(filepath, encoding="utf-8") as f:
                return self.parse(f.read())
        except FileNotFoundError:
            raise FileNotFoundError(f"Resume file not found: {filepath}")

    # ──────────────────────────────────────────────────
    #  PRIVATE HELPERS
    # ──────────────────────────────────────────────────

    def _normalize(self, text: str) -> str:
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"\t", "  ", text)
        text = re.sub(r" {3,}", "  ", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        return text.strip()

    def _split_sections(self, text: str) -> Dict[str, str]:
        """Split resume into named sections."""
        sections: Dict[str, str] = {}
        lines = text.splitlines()
        current_section = "header"
        current_lines: List[str] = []

        for line in lines:
            matched_section = None
            for name, pattern in SECTION_PATTERNS.items():
                if pattern.match(line.strip()):
                    matched_section = name
                    break
            if matched_section:
                sections[current_section] = "\n".join(current_lines)
                current_section = matched_section
                current_lines = []
            else:
                current_lines.append(line)

        sections[current_section] = "\n".join(current_lines)
        return sections

    def _extract_name(self, text: str) -> str:
        lines = [l.strip() for l in text.splitlines()[:8] if l.strip()]
        for line in lines:
            if re.search(r"[@|•\d()\[\]/\\]", line):
                continue
            words = line.split()
            if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
                if not re.match(r"(?:resume|curriculum|vitae|cv|profile)", line, re.IGNORECASE):
                    return line
        return "Unknown"

    def _extract_email(self, text: str) -> str:
        m = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
        return m.group(0).lower() if m else ""

    def _extract_phone(self, text: str) -> str:
        patterns = [
            r"\+\d{1,3}[\s\-]?\d{3,4}[\s\-]?\d{4}",
            r"\+?1?[\s\-.]?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}",
            r"\b\d{3}[\s\-]\d{3}[\s\-]\d{4}\b",
            r"\b\d{10}\b",
        ]
        for p in patterns:
            for m in re.finditer(p, text):
                digits = re.sub(r"\D", "", m.group(0))
                if 7 <= len(digits) <= 15:
                    return re.sub(r"\s+", " ", m.group(0).strip())
        return ""

    def _extract_linkedin(self, text: str) -> str:
        m = re.search(r"linkedin\.com/in/[\w\-]+", text, re.IGNORECASE)
        return f"https://www.{m.group(0)}" if m else ""

    def _extract_github(self, text: str) -> str:
        m = re.search(r"github\.com/[\w\-]+", text, re.IGNORECASE)
        return f"https://www.{m.group(0)}" if m else ""

    def _extract_location(self, text: str) -> str:
        lines = [l.strip() for l in text.splitlines()[:10] if l.strip()]
        for line in lines:
            if re.match(r"^[A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+$", line):
                return line
        return ""

    def _extract_skills(self, text: str, sections: Dict[str, str]) -> List[str]:
        text_lower = text.lower()
        section_text = sections.get("skills", "").lower()
        found = set()

        for skill in self._skills:
            pattern = r"\b" + re.escape(skill) + r"\b"
            if re.search(pattern, text_lower):
                found.add(skill)

        if section_text:
            tokens = re.split(r"[,•\|\n/]+", section_text)
            for token in tokens:
                token = token.strip()
                if 2 <= len(token) <= 30:
                    for skill in self._skills:
                        if skill in token:
                            found.add(skill)

        return sorted(found)

    # ── BUG 2 FIX: Work history extraction ────────────────────────────
    def _extract_work_history(self, experience_text: str) -> List[WorkExperience]:
        """
        Parse individual work entries from experience section.

        Handles the common resume format:
            Job Title – Company Name (YYYY – YYYY/Present)
              Description bullet...
        """
        entries: List[WorkExperience] = []

        # Split on lines that look like a new job entry header:
        # capital-letter line that contains a year pattern
        blocks = re.split(r"\n(?=[A-Z][^\n]{5,80}(?:\(|\d{4}))", experience_text)

        for block in blocks:
            if not block.strip():
                continue

            # Extract year range
            year_match = re.search(
                r"(\d{4})\s*[-–—]\s*(\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow)",
                block,
            )
            if not year_match:
                continue

            start_year = int(year_match.group(1))
            end_raw = year_match.group(2).lower()
            end_year = None if end_raw in ("present", "current", "now") else int(end_raw)

            # ── Extract title and company from the first line ──────────
            # Common pattern: "Job Title – Company Name (2020 – Present)"
            #                 "Job Title at Company Name (2020 – Present)"
            first_line = block.splitlines()[0].strip()

            # Remove the date part from the first line for cleaner parsing
            header = re.sub(r"\s*\(?\d{4}\s*[-–—].*", "", first_line).strip()

            title = ""
            company = ""

            # Try "Title – Company" or "Title — Company" separator
            sep_match = re.split(r"\s+[-–—]\s+", header, maxsplit=1)
            if len(sep_match) == 2:
                title   = sep_match[0].strip()
                company = sep_match[1].strip()
            else:
                # Try "Title at Company"
                at_match = re.split(r"\s+at\s+", header, maxsplit=1, flags=re.IGNORECASE)
                if len(at_match) == 2:
                    title   = at_match[0].strip()
                    company = at_match[1].strip()
                else:
                    # Fallback: whole header is the title
                    title = header

            # Description = remaining lines (skip header line)
            desc_lines = [l.strip() for l in block.splitlines()[1:] if l.strip()]
            description = " ".join(desc_lines[:4])[:300]

            if start_year >= 1970:
                entries.append(WorkExperience(
                    title=title,
                    company=company,
                    start_year=start_year,
                    end_year=end_year,
                    description=description,
                ))

        entries.sort(key=lambda e: e.start_year, reverse=True)
        return entries

    def _calculate_total_experience(
        self, work_history: List[WorkExperience], text: str
    ) -> float:
        if work_history:
            years = [w.start_year for w in work_history]
            if years:
                earliest = min(years)
                return round(min(datetime.now().year - earliest, 40), 1)

        direct = re.findall(
            r"(\d+)\+?\s*years?\s*(?:of\s*)?(?:experience|exp)", text, re.IGNORECASE
        )
        if direct:
            return float(max(int(y) for y in direct))

        return 0.0

    def _extract_education_level(self, text: str) -> EducationLevel:
        return EducationLevel.from_string(text)

    # ── BUG 1 FIX: Education field extraction ─────────────────────────
    def _extract_education_field(self, education_section: str) -> str:
        """
        Extract field of study from the education section only.
        Previously received the full resume text, causing false matches
        like 'Python' (from the skills section) being returned.

        Restricted patterns only match degree-like phrases:
            'Bachelor of Science in Computer Science'
            'M.Sc in Software Engineering'
        """
        if not education_section.strip():
            return ""

        # Only look at the education section, not the full resume
        patterns = [
            # "Bachelor/Master of X in Y" → capture Y
            r"(?:Bachelor|Master|B\.?Sc|M\.?Sc|B\.?Tech|M\.?Tech|B\.?E|M\.?E)"
            r"[^\n]{0,30}\bin\s+([A-Z][a-zA-Z\s]{3,40}?)(?:\s*[-–,]|\s*\d{4}|\s*$)",
            # "Degree in Y from/at University"
            r"\bin\s+([A-Z][a-zA-Z\s]{3,40}?)(?:\s+(?:from|at|–|-)\s+[A-Z])",
        ]

        for p in patterns:
            m = re.search(p, education_section)
            if m:
                field = m.group(1).strip()
                # Sanity-check: reject if it looks like a skill or university name
                skip_words = {
                    "python", "java", "state", "tech", "university",
                    "college", "institute", "the", "and", "of",
                }
                if field.lower() not in skip_words and len(field) > 3:
                    return field
        return ""

    # ── BUG 3 FIX: Certification deduplication ────────────────────────
    def _extract_certifications(self, text: str, sections: Dict[str, str]) -> List[str]:
        """
        Extract certification names, deduplicating overlapping matches.

        Root cause of duplicates: overlapping patterns like 'Certified ...'
        matching a sub-string already captured by 'AWS Certified ...'.
        Fix: normalise each match to a dedup key and prefer longer matches.
        Also uses [a-zA-Z ] (no newline) in trailing captures to prevent
        cross-line matching that appended the next line's first word.
        """
        cert_text = sections.get("certifications", "")
        combined = cert_text + "\n" + text

        # Use [a-zA-Z ] (no newline) in trailing captures to prevent
        # the regex engine from matching across line boundaries.
        patterns = [
            r"AWS\s+Certified\s+[A-Z][a-zA-Z ]{3,40}",
            r"Google\s+(?:Cloud\s+)?(?:Certified\s+)?[A-Z][a-zA-Z ]{3,30}",
            r"Microsoft\s+(?:Certified\s+)?[A-Z][a-zA-Z: ]{3,40}",
            r"(?:PMP|CISSP|CPA|CISA|CEH|OSCP|CCNA|CCNP|CKA|GCP|Azure)\b",
            r"Certified\s+[A-Z][a-zA-Z ]{3,30}",
        ]

        # key → longest match seen so far
        seen: Dict[str, str] = {}

        for p in patterns:
            for m in re.finditer(p, combined):
                cert = re.sub(r"\s+", " ", m.group(0).strip())
                if len(cert) <= 3:
                    continue

                key = _cert_key(cert)

                # Check if this key is a sub-string of an already-seen key
                # (i.e. a more-specific match is already stored)
                already_covered = any(key in existing_key for existing_key in seen)
                if already_covered:
                    continue

                # Check if this new match covers a previously stored shorter key
                for existing_key in list(seen.keys()):
                    if existing_key in key:
                        del seen[existing_key]

                seen[key] = cert

        return sorted(seen.values())[:10]

    def _extract_languages(self, text: str) -> List[str]:
        human_langs = [
            "english", "spanish", "french", "german", "mandarin", "chinese",
            "japanese", "arabic", "hindi", "portuguese", "russian", "korean",
            "italian", "dutch", "tamil", "telugu", "kannada",
        ]
        lang_section = re.search(
            r"(?:languages?|linguistic)[:\s]+(.{0,200})", text, re.IGNORECASE
        )
        search_text = (
            lang_section.group(1).lower() if lang_section else text.lower()
        )
        found = []
        for lang in human_langs:
            if re.search(r"\b" + lang + r"\b", search_text):
                found.append(lang.title())
        return found

    def _extract_summary(self, text: str, sections: Dict[str, str]) -> str:
        if "summary" in sections and sections["summary"].strip():
            return " ".join(sections["summary"].strip().split())[:400]
        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if len(p.strip()) > 80]
        if paragraphs:
            return " ".join(paragraphs[0].split())[:400]
        return ""

    def _calculate_confidence(self, c: Candidate) -> float:
        checks = [
            (c.name != "Unknown",                  0.20),
            (bool(c.email),                        0.20),
            (bool(c.skills),                       0.20),
            (c.experience_years > 0,               0.15),
            (c.education != EducationLevel.UNKNOWN, 0.15),
            (bool(c.summary),                      0.10),
        ]
        return round(sum(w for cond, w in checks if cond), 2)
