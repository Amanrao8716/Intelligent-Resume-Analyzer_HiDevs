"""Tests for resume reading and parsing."""

from datetime import date

import pytest

from models import Candidate
from resume_parser import (
    extract_email,
    extract_name,
    extract_phone,
    parse_resume_bytes,
    parse_resume_file,
    parse_resume_text,
    read_resume_file,
)
from utils import FileOperationError, ParseError, SkillDictionary
from conftest import SAMPLE_RESUMES, build_pdf

TODAY = date(2026, 10, 4)


def test_valid_resume_parsing(priya_text):
    candidate = parse_resume_text(priya_text, today=TODAY)
    assert candidate.name == "Priya Sharma"
    assert candidate.email == "priya.sharma@example.com"
    assert candidate.phone == "+91 98450 12345"
    assert {"python", "django", "sql", "aws", "docker"} <= set(candidate.skills)
    assert {"communication", "teamwork"} <= set(candidate.soft_skills)
    assert candidate.experience == 5.0
    assert any("Computer Science" in line for line in candidate.education)
    assert candidate.certifications == ["AWS Certified Cloud Practitioner"]
    assert candidate.projects == ["Inventory Tracker API", "Expense Analyzer"]


def test_missing_email_returns_none():
    text = "Jane Doe\nSKILLS\nPython, SQL and Git for backend work and testing."
    candidate = parse_resume_text(text)
    assert candidate.email is None
    assert candidate.name == "Jane Doe"


def test_missing_experience_is_none_not_invented():
    candidate = parse_resume_file(SAMPLE_RESUMES / "rahul_verma.txt", today=TODAY)
    assert candidate.experience is None


def test_duplicate_skills_removed():
    text = (
        "John Smith\nSKILLS\nPython, python, PYTHON, py, SQL, sql, Python3 programming"
    )
    candidate = parse_resume_text(text)
    assert candidate.skills.count("python") == 1
    assert candidate.skills.count("sql") == 1
    assert len(candidate.skills) == len(set(candidate.skills))


def test_skill_aliases_are_normalized():
    text = "Skills\nJS, ReactJS, Node.js, K8s, Postgres, Amazon Web Services, sklearn"
    skills = set(parse_resume_text(text).skills)
    assert {"javascript", "react", "node.js", "kubernetes"} <= skills
    assert {"postgresql", "aws", "scikit-learn"} <= skills


def test_java_is_not_confused_with_javascript():
    skills = parse_resume_text("Skills\nI know JavaScript and nothing else here").skills
    assert "javascript" in skills
    assert "java" not in skills


def test_bare_c_detected_only_in_skills_list():
    assert "c" in parse_resume_file(SAMPLE_RESUMES / "rahul_verma.txt").skills
    prose = "Alex Kim\nI scored grade C in art class and also learned Python."
    assert "c" not in parse_resume_text(prose).skills


def test_empty_resume_raises():
    with pytest.raises(ParseError):
        parse_resume_text("")
    with pytest.raises(ParseError):
        parse_resume_text("   \n\n  ")


def test_invalid_file_type(tmp_path):
    path = tmp_path / "resume.docx"
    path.write_text("some resume text that is long enough", encoding="utf-8")
    with pytest.raises(ParseError, match="Unsupported file type"):
        read_resume_file(path)


def test_missing_file(tmp_path):
    with pytest.raises(FileOperationError, match="not found"):
        read_resume_file(tmp_path / "missing.txt")


def test_empty_file_bytes():
    with pytest.raises(ParseError, match="empty"):
        parse_resume_bytes(b"", "empty.txt")


def test_corrupted_pdf():
    with pytest.raises(ParseError, match="corrupted|No readable text"):
        parse_resume_bytes(b"%PDF-1.4 this is not really a pdf", "bad.pdf")


def test_pdf_without_text_is_rejected():
    with pytest.raises(ParseError):
        parse_resume_bytes(build_pdf([""]), "blank.pdf")


def test_valid_pdf_matches_txt(priya_text):
    pdf_candidate = parse_resume_bytes(build_pdf(priya_text.splitlines()), "p.pdf")
    txt_candidate = parse_resume_text(priya_text)
    assert pdf_candidate.email == txt_candidate.email
    assert pdf_candidate.skills == txt_candidate.skills
    assert pdf_candidate.source_file == "p.pdf"


def test_sample_pdf_file_parses():
    candidate = parse_resume_file(SAMPLE_RESUMES / "priya_sharma.pdf")
    assert candidate.name == "Priya Sharma"


def test_non_utf8_text_file(tmp_path):
    path = tmp_path / "latin.txt"
    path.write_bytes(
        "Jos\xe9 Garc\xeda\nSkills\nPython and SQL developer".encode("cp1252")
    )
    candidate = parse_resume_file(path)
    assert "python" in candidate.skills


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Contact: Mary.Jane+jobs@Example.CO.in", "mary.jane+jobs@example.co.in"),
        ("no email here", None),
    ],
)
def test_email_extraction(text, expected):
    assert extract_email(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Call +91 98765 43210 today", "+91 98765 43210"),
        ("Phone: (415) 555-2671", "(415) 555-2671"),
        ("Worked 2019 - 2021 at X", None),
        ("2020 2021 2022 2023", None),
    ],
)
def test_phone_extraction(text, expected):
    assert extract_phone(text) == expected


def test_name_extraction_variants():
    assert extract_name("JOHN DOE\njohn@example.com") == "John Doe"
    assert extract_name("Name: Asha Rao\nEmail: a@b.co") == "Asha Rao"
    assert extract_name("Resume\nSoftware Engineer\nSkills") is None


def test_experience_from_overlapping_date_ranges():
    text = (
        "Pat Lee\nEXPERIENCE\nDev A\nJan 2020 - Dec 2021\nDev B\nJun 2021 - Jun 2022\n"
        "EDUCATION\nB.Sc. Physics 2015 - 2018"
    )
    candidate = parse_resume_text(text, today=TODAY)
    # Jan 2020 -> Jun 2022 merged = 29 months = 2.4 years (education dates ignored)
    assert candidate.experience == 2.4


def test_experience_stated_beats_dates():
    text = "Lee Pat\nSummary\n8+ years of professional experience in QA testing work."
    assert parse_resume_text(text).experience == 8.0


def test_present_uses_given_date():
    text = "Sam Ray\nEXPERIENCE\nEngineer\nJan 2025 - Present\n"
    assert parse_resume_text(text, today=date(2026, 1, 1)).experience == 1.0


def test_custom_skill_dictionary_extension():
    technical = SkillDictionary.technical()
    technical.add_skill("cobol", ["cobol-85"])
    candidate = parse_resume_text(
        "Old Timer\nSKILLS\nCOBOL-85, Python, mainframe batch jobs",
        technical_skills=technical,
    )
    assert "cobol" in candidate.skills


def test_parser_output_is_consistent_type():
    candidate = parse_resume_text(
        "Zed Abc\nSkills\nsome words only, nothing special here"
    )
    assert isinstance(candidate, Candidate)
    assert candidate.skills == []
    assert candidate.education == []
    assert candidate.projects == []
    candidate.validate()


def test_all_samples_parse():
    for path in sorted(SAMPLE_RESUMES.glob("*")):
        candidate = parse_resume_file(path, today=TODAY)
        assert candidate.email and candidate.skills, path.name
