"""Reusable helpers: custom exceptions, logging, text cleaning, skill dictionary.

Nothing in this module depends on the other project modules, so every other
module can safely import from it.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Pattern, Tuple

# --------------------------------------------------------------------------
# Custom exceptions
# --------------------------------------------------------------------------


class ResumeAnalyzerError(Exception):
    """Base class for every error raised on purpose by this project."""


class ParseError(ResumeAnalyzerError):
    """A resume could not be read or understood (empty, corrupted, unsupported)."""


class ValidationError(ResumeAnalyzerError):
    """Input data (candidate, job, scores) failed validation."""


class FileOperationError(ResumeAnalyzerError):
    """Reading or writing a file failed (missing, permissions, invalid JSON)."""


class AIServiceError(ResumeAnalyzerError):
    """The optional AI service is unavailable or returned unusable output."""


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

LOGGER_NAMESPACE = "resume_analyzer"
_CONSOLE_HANDLER_NAME = "resume_analyzer_console"
_FILE_HANDLER_NAME = "resume_analyzer_file"
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a logger inside the project's logging namespace."""
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")


def setup_logging(
    log_file: Optional[Path | str] = None, level: int = logging.INFO
) -> None:
    """Configure console (and optional file) logging exactly once.

    Safe to call repeatedly, which matters because Streamlit re-runs the
    script on every interaction. Log messages never contain resume content or
    personal details.
    """
    project_logger = logging.getLogger(LOGGER_NAMESPACE)
    project_logger.setLevel(level)
    project_logger.propagate = False
    existing = {handler.name for handler in project_logger.handlers}
    formatter = logging.Formatter(_LOG_FORMAT)

    if _CONSOLE_HANDLER_NAME not in existing:
        console = logging.StreamHandler()
        console.set_name(_CONSOLE_HANDLER_NAME)
        console.setFormatter(formatter)
        project_logger.addHandler(console)

    if log_file and _FILE_HANDLER_NAME not in existing:
        try:
            path = Path(log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(path, encoding="utf-8")
        except OSError as exc:
            project_logger.warning(
                "File logging disabled (%s).", exc.__class__.__name__
            )
            return
        file_handler.set_name(_FILE_HANDLER_NAME)
        file_handler.setFormatter(formatter)
        project_logger.addHandler(file_handler)


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 10-13 digits with optional +, spaces, dots, dashes and brackets.
PHONE_RE = re.compile(r"(?<![\w.])[+(]?\d[\d ().\-]{7,18}\d(?!\w)")
_YEAR_PAIR_RE = re.compile(r"^(?:19|20)\d{2}[ .\-]+(?:19|20)\d{2}")
_INVISIBLE_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\x00-\x08\x0b\x0e-\x1f]")


def clean_text(text: str) -> str:
    """Normalize resume text: unicode, line endings, spaces and blank lines."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n")
    text = _INVISIBLE_RE.sub("", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    cleaned = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    """Remove case-insensitive duplicates while keeping the first spelling."""
    seen = set()
    result: List[str] = []
    for item in items:
        key = str(item).strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(str(item).strip())
    return result


def split_items(text: str) -> List[str]:
    """Split user-typed text on commas, semicolons, pipes, bullets or newlines."""
    if not text:
        return []
    return unique_preserve_order(re.split(r"[,;\n|\u2022]+", text))


def find_phone_numbers(text: str) -> Iterator[str]:
    """Yield phone-number-like strings (10-13 digits), skipping year ranges."""
    for match in PHONE_RE.finditer(text):
        candidate = match.group().strip()
        digits = re.sub(r"\D", "", candidate)
        if 10 <= len(digits) <= 13 and not _YEAR_PAIR_RE.match(candidate):
            yield re.sub(r"\s+", " ", candidate)


def redact_pii(text: str) -> str:
    """Replace e-mails and phone numbers before text is sent to an AI service."""
    text = EMAIL_RE.sub("[EMAIL]", text)
    for phone in sorted(set(find_phone_numbers(text)), key=len, reverse=True):
        text = text.replace(phone, "[PHONE]")
    return text


def safe_slug(text: str, max_length: int = 40, default: str = "item") -> str:
    """Turn arbitrary text into a filename-safe slug."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", text or "").strip("-")
    return slug[:max_length].strip("-") or default


# --------------------------------------------------------------------------
# Education levels
# --------------------------------------------------------------------------

EDUCATION_LABELS = {
    0: "Not specified",
    1: "Diploma",
    2: "Bachelor's degree",
    3: "Master's degree",
    4: "PhD / Doctorate",
}

_EDUCATION_PATTERNS: Tuple[Tuple[int, Pattern[str]], ...] = (
    (
        4,
        re.compile(r"\bph\.?\s?d\b|\bdoctorate\b|\bdoctor of philosophy\b", re.I),
    ),
    (
        3,
        re.compile(
            r"\bmaster'?s\b|\bmasters\b|\bmaster\s+(?:of|in|degree)\b"
            r"|\bm\.?\s?tech\b|\bm\.?\s?sc\b|\bmba\b|\bmca\b|\bm\.e\b"
            r"|\bms\s+in\b|\bm\.s\b",
            re.I,
        ),
    ),
    (
        2,
        re.compile(
            r"\bbachelor'?s?\b|\bb\.?\s?tech\b|\bb\.?\s?sc\b|\bbca\b"
            r"|\bb\.?\s?com\b|\bb\.e\b|\bbs\s+in\b|\bb\.s\b"
            r"|\bundergraduate\b|\bdegree\b",
            re.I,
        ),
    ),
    (1, re.compile(r"\bdiploma\b", re.I)),
)
_BARE_EDUCATION_WORDS = {
    "diploma": 1,
    "bachelor": 2,
    "bachelors": 2,
    "master": 3,
    "masters": 3,
    "phd": 4,
    "doctorate": 4,
}


def education_rank(text: Optional[str]) -> int:
    """Return 0-4 for the highest education level mentioned in ``text``."""
    if not text or not str(text).strip():
        return 0
    cleaned = str(text).strip().lower()
    if cleaned in _BARE_EDUCATION_WORDS:
        return _BARE_EDUCATION_WORDS[cleaned]
    for rank, pattern in _EDUCATION_PATTERNS:
        if pattern.search(cleaned):
            return rank
    return 0


# --------------------------------------------------------------------------
# Skill dictionary
# --------------------------------------------------------------------------


_SEARCH_EXCLUDED_NAMES = frozenset({"go"})


def clean_skill_name(name: object) -> str:
    """Lower-case a skill name, collapse spaces and trim stray punctuation."""
    cleaned = re.sub(r"\s+", " ", str(name).strip().lower())
    return cleaned.strip(" ,;:()[]{}'\"\u2022*-\u2013\u2014\u00b7").rstrip(".")


class SkillDictionary:
    """Maps skill aliases to canonical names and finds skills inside text.

    The dictionary can be extended at runtime with :meth:`add_skill`.
    """

    def __init__(self, skills: Optional[Mapping[str, Iterable[str]]] = None) -> None:
        self._aliases: Dict[str, List[str]] = {}
        self._lookup: Dict[str, str] = {}
        self._patterns: Optional[List[Tuple[str, Pattern[str]]]] = None
        for canonical, aliases in (skills or {}).items():
            self.add_skill(canonical, aliases)

    # -- factories ---------------------------------------------------------
    @classmethod
    def technical(cls) -> "SkillDictionary":
        """Dictionary of technical skills."""
        return cls(TECHNICAL_SKILLS)

    @classmethod
    def soft(cls) -> "SkillDictionary":
        """Dictionary of soft skills."""
        return cls(SOFT_SKILLS)

    @classmethod
    def combined(cls) -> "SkillDictionary":
        """Technical and soft skills together (used for normalization)."""
        return cls({**TECHNICAL_SKILLS, **SOFT_SKILLS})

    # -- editing -----------------------------------------------------------
    def add_skill(self, canonical: str, aliases: Iterable[str] = ()) -> None:
        """Add a skill (or extend an existing one) with extra aliases."""
        key = clean_skill_name(canonical)
        if not key:
            raise ValidationError("A skill name cannot be empty.")
        names = self._aliases.setdefault(key, [])
        for name in (key, *aliases):
            cleaned = clean_skill_name(name)
            if cleaned and cleaned not in names:
                names.append(cleaned)
            if cleaned:
                self._lookup[cleaned] = key
        self._patterns = None

    # -- lookups -----------------------------------------------------------
    def normalize(self, name: object) -> str:
        """Return the canonical form of a skill name (unknown names are cleaned)."""
        cleaned = clean_skill_name(name)
        return self._lookup.get(cleaned, cleaned)

    def canonical_skills(self) -> List[str]:
        """List all canonical skill names."""
        return list(self._aliases)

    def _build_patterns(self) -> List[Tuple[str, Pattern[str]]]:
        patterns: List[Tuple[str, Pattern[str]]] = []
        for canonical, names in self._aliases.items():
            # Ambiguous names (e.g. "c", "go") would match ordinary words, so
            # they are only used for normalization; the parser handles "c".
            usable = [
                name
                for name in names
                if len(name) > 1 and name not in _SEARCH_EXCLUDED_NAMES
            ]
            if not usable:
                continue
            alternatives = "|".join(
                re.escape(name).replace(r"\ ", r"[\s\-]+")
                for name in sorted(usable, key=len, reverse=True)
            )
            regex = re.compile(
                rf"(?<![\w+#.\-])(?:{alternatives})(?![\w+#])", re.IGNORECASE
            )
            patterns.append((canonical, regex))
        return patterns

    def find_in_text(self, text: str) -> List[str]:
        """Return canonical skills mentioned in ``text`` (no duplicates)."""
        if not text:
            return []
        if self._patterns is None:
            self._patterns = self._build_patterns()
        return [name for name, regex in self._patterns if regex.search(text)]


TECHNICAL_SKILLS: Dict[str, List[str]] = {
    "python": ["python3", "python 3"],
    "java": ["core java", "java 8", "java 11", "java 17"],
    "c": ["c programming", "c language"],
    "c++": ["cpp"],
    "c#": ["csharp", "c sharp"],
    ".net": ["dotnet", "asp.net", ".net core"],
    "javascript": ["js", "es6", "ecmascript"],
    "typescript": ["ts"],
    "go": ["golang", "go lang"],
    "rust": [],
    "kotlin": [],
    "swift": [],
    "php": [],
    "ruby": [],
    "bash": ["shell scripting", "shell script"],
    "html": ["html5"],
    "css": ["css3"],
    "tailwind css": ["tailwind"],
    "bootstrap": [],
    "jquery": [],
    "react": ["react.js", "reactjs"],
    "angular": ["angularjs", "angular.js"],
    "vue": ["vue.js", "vuejs"],
    "next.js": ["nextjs"],
    "node.js": ["nodejs", "node"],
    "express": ["express.js", "expressjs"],
    "django": [],
    "flask": [],
    "fastapi": [],
    "spring boot": ["springboot", "spring framework"],
    "streamlit": [],
    "sql": ["structured query language"],
    "mysql": [],
    "postgresql": ["postgres"],
    "mongodb": ["mongo", "mongo db"],
    "sqlite": [],
    "redis": [],
    "oracle": ["oracle db", "pl/sql"],
    "dynamodb": [],
    "aws": ["amazon web services"],
    "azure": ["microsoft azure"],
    "gcp": ["google cloud", "google cloud platform"],
    "docker": [],
    "kubernetes": ["k8s"],
    "terraform": [],
    "jenkins": [],
    "ci/cd": ["cicd", "ci cd", "continuous integration"],
    "git": [],
    "github": [],
    "gitlab": [],
    "linux": ["unix"],
    "rest api": ["rest apis", "restful api", "restful apis", "restful"],
    "graphql": [],
    "microservices": ["microservice"],
    "kafka": ["apache kafka"],
    "spark": ["apache spark", "pyspark"],
    "hadoop": [],
    "machine learning": ["ml"],
    "deep learning": [],
    "nlp": ["natural language processing"],
    "computer vision": [],
    "pandas": [],
    "numpy": [],
    "scikit-learn": ["sklearn", "scikit learn"],
    "tensorflow": [],
    "pytorch": [],
    "matplotlib": [],
    "data analysis": ["data analytics"],
    "data structures": ["dsa", "data structures and algorithms"],
    "algorithms": [],
    "oop": ["object oriented programming", "object-oriented programming"],
    "system design": [],
    "tableau": [],
    "power bi": ["powerbi"],
    "microsoft excel": ["ms excel", "advanced excel", "excel spreadsheets"],
    "pytest": [],
    "junit": [],
    "selenium": [],
    "unit testing": ["unit tests"],
    "agile": [],
    "scrum": [],
    "jira": [],
    "figma": [],
    "android": [],
    "flutter": [],
    "react native": [],
    "firebase": [],
    "lambda": ["aws lambda"],
    "s3": ["amazon s3"],
    "ec2": ["amazon ec2"],
}

SOFT_SKILLS: Dict[str, List[str]] = {
    "communication": [
        "communication skills",
        "verbal communication",
        "written communication",
        "excellent communication",
    ],
    "teamwork": ["team work", "team player", "collaboration", "collaborative"],
    "leadership": ["leadership skills", "team leadership", "team lead"],
    "problem solving": ["problem solver", "analytical skills", "analytical thinking"],
    "critical thinking": [],
    "time management": [],
    "adaptability": ["adaptable", "flexibility"],
    "creativity": ["creative thinking"],
    "attention to detail": ["detail oriented", "detail-oriented"],
    "project management": [],
    "presentation skills": ["public speaking"],
    "decision making": [],
    "negotiation": [],
    "conflict resolution": [],
    "mentoring": ["mentorship"],
}
