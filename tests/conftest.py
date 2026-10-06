"""Shared pytest fixtures and helpers."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from models import Candidate, Job

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_RESUMES = PROJECT_ROOT / "sample_data" / "resumes"
SAMPLE_JOBS = PROJECT_ROOT / "sample_data" / "jobs"


def build_pdf(lines: List[str], lines_per_page: int = 45) -> bytes:
    """Create a small text PDF (no extra libraries needed) for tests."""

    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    pages = [
        lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)
    ]
    pages = pages or [[""]]
    objects: List[str] = []
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, page_lines in enumerate(pages):
        content_id = page_ids[index] + 1
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        )
        body = "BT /F1 11 Tf 15 TL 40 760 Td "
        body += " ".join(f"({escape(line)}) Tj T*" for line in page_lines) + " ET"
        objects.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream")
    output = "%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output.encode("latin-1")))
        output += f"{number} 0 obj\n{obj}\nendobj\n"
    xref_at = len(output.encode("latin-1"))
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    output += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    )
    return output.encode("latin-1", errors="replace")


@pytest.fixture
def priya_text() -> str:
    return (SAMPLE_RESUMES / "priya_sharma.txt").read_text(encoding="utf-8")


@pytest.fixture
def backend_job() -> Job:
    return Job(
        title="Python Backend Developer",
        required_skills=["Python", "Django", "SQL", "REST API", "Git"],
        preferred_skills=["AWS", "Docker", "PostgreSQL", "CI/CD"],
        min_experience=3,
        required_education="Bachelor's",
    )


@pytest.fixture
def strong_candidate() -> Candidate:
    return Candidate(
        name="Test Person",
        email="test@example.com",
        skills=["python", "django", "sql", "rest api", "git", "aws", "docker"],
        experience=5.0,
        education=["B.E. in Computer Science"],
        projects=["Inventory Tracker API"],
    )


@pytest.fixture(autouse=True)
def reset_project_logging():
    """Remove log handlers installed by one test so they cannot leak into the next."""
    import logging

    def clear() -> None:
        project_logger = logging.getLogger("resume_analyzer")
        for handler in list(project_logger.handlers):
            project_logger.removeHandler(handler)
            handler.close()

    clear()
    yield
    clear()
