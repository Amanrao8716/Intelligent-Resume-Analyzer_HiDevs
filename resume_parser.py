"""Resume reading, text extraction, cleaning and parsing.

Public entry points:

* :func:`parse_resume_file` - parse a PDF/TXT file on disk.
* :func:`parse_resume_bytes` - parse uploaded bytes (used by the Streamlit app).
* :func:`parse_resume_text` - parse already-extracted text.

All extraction is rule-based (regular expressions + skill dictionary), so it is
deterministic and works without any AI service.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pypdf import PdfReader

from models import Candidate
from utils import (
    EMAIL_RE,
    FileOperationError,
    ParseError,
    SkillDictionary,
    clean_text,
    education_rank,
    find_phone_numbers,
    get_logger,
    unique_preserve_order,
)

logger = get_logger("parser")

SUPPORTED_EXTENSIONS = (".pdf", ".txt")
MAX_FILE_BYTES = 10 * 1024 * 1024
MIN_TEXT_LENGTH = 20
MAX_LIST_ITEMS = 10
MAX_REASONABLE_EXPERIENCE = 50.0

# --------------------------------------------------------------------------
# Reading files
# --------------------------------------------------------------------------


def read_resume_file(path: Path | str) -> str:
    """Read a PDF or TXT resume from disk and return cleaned text.

    Raises:
        ParseError: unsupported type, corrupted/empty file.
        FileOperationError: file missing or not readable.
    """
    file_path = Path(path)
    _check_extension(file_path.name)
    try:
        data = file_path.read_bytes()
    except FileNotFoundError:
        raise FileOperationError(f"Resume file not found: {file_path.name}") from None
    except PermissionError:
        raise FileOperationError(
            f"Permission denied while reading: {file_path.name}"
        ) from None
    except OSError as exc:
        logger.warning("Could not read resume file (%s).", exc.__class__.__name__)
        raise FileOperationError(f"Could not read file: {file_path.name}") from exc
    return extract_text_from_bytes(data, file_path.name)


def extract_text_from_bytes(data: bytes, filename: str) -> str:
    """Extract and clean text from the raw bytes of a PDF or TXT resume."""
    suffix = _check_extension(filename)
    if not data:
        raise ParseError(f"The file '{filename}' is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ParseError(
            f"The file '{filename}' is larger than "
            f"{MAX_FILE_BYTES // (1024 * 1024)} MB."
        )
    raw_text = _extract_pdf_text(data, filename) if suffix == ".pdf" else _decode(data)
    text = clean_text(raw_text)
    if len(text) < MIN_TEXT_LENGTH:
        raise ParseError(
            f"No readable text found in '{filename}'. "
            "Scanned or image-only PDFs are not supported."
        )
    return text


def _check_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        shown = suffix or "no extension"
        raise ParseError(
            f"Unsupported file type ({shown}). Please provide a PDF or TXT resume."
        )
    return suffix


def _decode(data: bytes) -> str:
    """Decode text bytes, trying UTF-8 first and falling back gracefully."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_pdf_text(data: bytes, filename: str) -> str:
    """Extract text from every page of a PDF."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ParseError(f"'{filename}' is password protected.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except ParseError:
        raise
    except Exception as exc:  # pypdf raises many different error types
        logger.warning("PDF could not be read (%s).", exc.__class__.__name__)
        raise ParseError(
            f"'{filename}' could not be read. The PDF may be corrupted."
        ) from exc
    return "\n".join(pages)


# --------------------------------------------------------------------------
# Section detection
# --------------------------------------------------------------------------

_SECTION_ALIASES: Dict[str, Tuple[str, ...]] = {
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "employment",
        "work history",
        "internships",
        "internship experience",
        "professional background",
    ),
    "education": (
        "education",
        "academic background",
        "academic qualifications",
        "educational qualifications",
        "qualifications",
    ),
    "skills": (
        "skills",
        "technical skills",
        "key skills",
        "core competencies",
        "skills summary",
        "technologies",
        "tech stack",
    ),
    "projects": (
        "projects",
        "personal projects",
        "academic projects",
        "key projects",
        "selected projects",
    ),
    "certifications": (
        "certifications",
        "certificates",
        "licenses and certifications",
        "courses and certifications",
        "certifications and courses",
    ),
    "other": (
        "summary",
        "professional summary",
        "objective",
        "career objective",
        "profile",
        "about me",
        "achievements",
        "awards",
        "interests",
        "hobbies",
        "languages",
        "references",
        "publications",
        "extracurricular activities",
        "volunteer experience",
    ),
}
_HEADING_LOOKUP = {
    alias: section for section, aliases in _SECTION_ALIASES.items() for alias in aliases
}
_BULLET_RE = re.compile(r"^\s*[\u2022\u25cf\u25aa\u25e6\u00b7*\-\u2013>]+\s*")


def _heading_key(line: str) -> Optional[str]:
    """Return the section name if ``line`` is a section heading."""
    if not line or len(line) > 45:
        return None
    normalized = re.sub(r"[^a-z& ]", "", line.lower()).replace("&", "and")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return _HEADING_LOOKUP.get(normalized)


def split_sections(text: str) -> Dict[str, str]:
    """Split resume text into known sections keyed by section name."""
    buckets: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in text.split("\n"):
        heading = _heading_key(line.strip())
        if heading:
            current = heading
            buckets.setdefault(current, [])
        elif current:
            buckets[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in buckets.items()}


def _section_lines(section_text: str) -> List[str]:
    """Return non-empty lines of a section with bullet markers removed."""
    lines = [_BULLET_RE.sub("", line).strip() for line in section_text.split("\n")]
    return [line for line in lines if line]


# --------------------------------------------------------------------------
# Field extraction
# --------------------------------------------------------------------------

_NAME_LABEL_RE = re.compile(
    r"^\s*(?:full\s+)?name\s*[:\-]\s*([A-Za-z][A-Za-z .'\-]{1,50})\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_NON_NAME_WORDS = {
    "resume",
    "curriculum",
    "vitae",
    "cv",
    "summary",
    "objective",
    "profile",
    "experience",
    "education",
    "skills",
    "projects",
    "contact",
    "engineer",
    "developer",
    "analyst",
    "manager",
    "designer",
    "intern",
    "student",
    "software",
    "data",
    "full",
    "stack",
    "web",
}


def extract_email(text: str) -> Optional[str]:
    """Return the first e-mail address (lower-cased) or None."""
    match = EMAIL_RE.search(text)
    return match.group().lower() if match else None


def extract_phone(text: str) -> Optional[str]:
    """Return the first phone number or None."""
    return next(find_phone_numbers(text), None)


def extract_name(text: str) -> Optional[str]:
    """Guess the candidate name from a 'Name:' label or the first lines."""
    labelled = _NAME_LABEL_RE.search(text)
    if labelled:
        return _format_name(labelled.group(1).strip())
    for line in text.split("\n")[:8]:
        candidate = line.strip()
        if not candidate or "@" in candidate or re.search(r"\d", candidate):
            continue
        lowered = candidate.lower()
        if "http" in lowered or "linkedin" in lowered or "github" in lowered:
            continue
        words = candidate.replace(",", " ").split()
        if _heading_key(candidate) or any(w.lower() in _NON_NAME_WORDS for w in words):
            continue
        if (
            2 <= len(words) <= 4
            and len(candidate) <= 40
            and all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words)
        ):
            return _format_name(candidate)
    return None


def _format_name(name: str) -> str:
    """Title-case names that were written in ALL CAPS."""
    name = re.sub(r"\s+", " ", name).strip()
    if name.isupper():
        return " ".join(word.capitalize() for word in name.split())
    return name


_BARE_C_RE = re.compile(r"(?:^|[\s,;|/\u2022(])C(?=\s*(?:[,;|/\u2022)]|$))", re.M)


def extract_skills(
    text: str,
    technical: SkillDictionary,
    soft: SkillDictionary,
    sections: Optional[Dict[str, str]] = None,
) -> Tuple[List[str], List[str]]:
    """Return (technical_skills, soft_skills) found in the resume text."""
    sections = sections if sections is not None else split_sections(text)
    technical_found = technical.find_in_text(text)
    # A bare "C" is only trusted inside the skills section (or the whole text
    # when the resume has no skills section) to avoid false positives.
    if "c" in technical.canonical_skills() and "c" not in technical_found:
        if _BARE_C_RE.search(sections.get("skills", text)):
            technical_found.append("c")
    return unique_preserve_order(technical_found), unique_preserve_order(
        soft.find_in_text(text)
    )


def extract_education(text: str, sections: Dict[str, str]) -> List[str]:
    """Return education lines that mention a degree level."""
    source = sections.get("education") or text
    lines = [
        line
        for line in _section_lines(source)
        if len(line) <= 160 and education_rank(line) > 0
    ]
    return unique_preserve_order(lines)[:MAX_LIST_ITEMS]


def extract_certifications(text: str, sections: Dict[str, str]) -> List[str]:
    """Return certification lines."""
    if sections.get("certifications"):
        lines = _section_lines(sections["certifications"])
    else:
        keyword = re.compile(r"\bcertified\b|\bcertification\b|\bcertificate\b", re.I)
        lines = [ln for ln in _section_lines(text) if keyword.search(ln)]
    return unique_preserve_order(ln[:150] for ln in lines)[:MAX_LIST_ITEMS]


def extract_projects(sections: Dict[str, str]) -> List[str]:
    """Return project titles (lines that are not bullet points)."""
    section = sections.get("projects")
    if not section:
        return []
    raw_lines = [line.strip() for line in section.split("\n") if line.strip()]
    titles = [ln for ln in raw_lines if not _BULLET_RE.match(ln)]
    chosen = titles or [_BULLET_RE.sub("", ln) for ln in raw_lines]
    return unique_preserve_order(ln[:120] for ln in chosen)[:MAX_LIST_ITEMS]


_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?"
    r"|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_DATE_RANGE_RE = re.compile(
    rf"(?<!\d)(?:(?P<sm>{_MONTH})\b\.?,?\s+)?(?P<sy>(?:19|20)\d{{2}})"
    rf"\s*(?:-|\u2013|\u2014|to)\s*"
    rf"(?:(?:(?P<em>{_MONTH})\b\.?,?\s+)?(?P<ey>(?:19|20)\d{{2}})(?!\d)"
    rf"|(?P<present>present|current|now|till\s+date|ongoing))",
    re.IGNORECASE,
)
_STATED_EXPERIENCE_RES = (
    re.compile(
        r"(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b[^\n.]{0,40}?\bexperience",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bexperience\b\s*(?:of|:|-)?\s*(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
        re.IGNORECASE,
    ),
)
_MONTH_NUMBERS = {
    name: index
    for index, name in enumerate(
        [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ],
        start=1,
    )
}


def extract_experience_years(
    text: str, sections: Dict[str, str], today: Optional[date] = None
) -> Optional[float]:
    """Estimate total years of experience, or None when it cannot be determined.

    1. An explicit statement such as "3 years of experience" wins.
    2. Otherwise date ranges in the Experience section are merged (so that
       overlapping jobs are not double counted) and summed.
    A date range written with years only ("2019 - 2021") counts from January
    to January, which is a deliberately conservative estimate.
    """
    stated = [
        float(match.group(1))
        for pattern in _STATED_EXPERIENCE_RES
        for match in pattern.finditer(text)
        if float(match.group(1)) <= MAX_REASONABLE_EXPERIENCE
    ]
    if stated:
        return max(stated)
    experience_section = sections.get("experience")
    if not experience_section:
        return None
    return _years_from_date_ranges(experience_section, today or date.today())


def _month_index(year: int, month_name: Optional[str]) -> int:
    month = _MONTH_NUMBERS.get((month_name or "jan")[:3].lower(), 1)
    return year * 12 + month


def _years_from_date_ranges(section_text: str, today: date) -> Optional[float]:
    today_index = today.year * 12 + today.month
    intervals: List[Tuple[int, int]] = []
    for match in _DATE_RANGE_RE.finditer(section_text):
        start = _month_index(int(match.group("sy")), match.group("sm"))
        if match.group("present"):
            end = today_index
        else:
            end = _month_index(int(match.group("ey")), match.group("em"))
        end = min(end, today_index)
        if end > start:
            intervals.append((start, end))
    if not intervals:
        return None
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    total_months = sum(end - start for start, end in merged)
    return round(min(total_months / 12, MAX_REASONABLE_EXPERIENCE), 1)


# --------------------------------------------------------------------------
# Public parsing API
# --------------------------------------------------------------------------


def parse_resume_text(
    text: str,
    source_file: Optional[str] = None,
    today: Optional[date] = None,
    technical_skills: Optional[SkillDictionary] = None,
    soft_skills: Optional[SkillDictionary] = None,
) -> Candidate:
    """Parse resume text into a :class:`Candidate`.

    Missing information is represented as None or an empty list; nothing is
    guessed or invented.

    Raises:
        ParseError: if the text is empty or too short to be a resume.
    """
    text = clean_text(text or "")
    if len(text) < MIN_TEXT_LENGTH:
        raise ParseError("The resume is empty or contains too little text.")
    technical = technical_skills or SkillDictionary.technical()
    soft = soft_skills or SkillDictionary.soft()
    sections = split_sections(text)
    skills, soft_found = extract_skills(text, technical, soft, sections)
    candidate = Candidate(
        name=extract_name(text),
        email=extract_email(text),
        phone=extract_phone(text),
        skills=skills,
        soft_skills=soft_found,
        experience=extract_experience_years(text, sections, today),
        education=extract_education(text, sections),
        certifications=extract_certifications(text, sections),
        projects=extract_projects(sections),
        source_file=source_file,
    )
    candidate.validate()
    logger.info(
        "Parsed resume: %d skills, %d soft skills, experience %s",
        len(skills),
        len(soft_found),
        "unknown" if candidate.experience is None else "found",
    )
    return candidate


def parse_resume_bytes(data: bytes, filename: str, **kwargs) -> Candidate:
    """Parse uploaded resume bytes (PDF or TXT)."""
    text = extract_text_from_bytes(data, filename)
    return parse_resume_text(text, source_file=Path(filename).name, **kwargs)


def parse_resume_file(path: Path | str, **kwargs) -> Candidate:
    """Parse a PDF or TXT resume on disk."""
    text = read_resume_file(path)
    return parse_resume_text(text, source_file=Path(path).name, **kwargs)
