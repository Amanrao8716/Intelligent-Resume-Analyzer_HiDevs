"""Safe JSON and text file operations.

Rules followed everywhere in this module:

* UTF-8 encoding.
* Output directories are created automatically.
* Existing files are never overwritten: every save uses a unique,
  timestamped file name and exclusive creation.
* Low-level errors are converted to :class:`FileOperationError` with a
  readable message (no file contents are ever put in messages or logs).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from models import Candidate, Job, MatchResult
from utils import FileOperationError, get_logger, safe_slug

logger = get_logger("files")

DEFAULT_OUTPUT_DIR = Path("outputs")
MAX_UNIQUE_ATTEMPTS = 1000


def ensure_directory(directory: Path | str) -> Path:
    """Create ``directory`` (and parents) if needed and return it as a Path."""
    path = Path(directory)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise FileOperationError(f"Permission denied creating folder: {path}") from None
    except OSError as exc:
        raise FileOperationError(f"Could not create folder: {path}") from exc
    return path


def _write_unique(
    directory: Path | str, stem: str, extension: str, content: str
) -> Path:
    """Write ``content`` to a new file and return its path.

    The file name is ``<stem>_<YYYYmmdd_HHMMSS>[_n].<extension>``. The file is
    opened in exclusive mode, so an existing file is never overwritten.
    """
    folder = ensure_directory(directory)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{safe_slug(stem, default='file')}_{timestamp}"
    for attempt in range(MAX_UNIQUE_ATTEMPTS):
        suffix = "" if attempt == 0 else f"_{attempt}"
        path = folder / f"{base}{suffix}.{extension.lstrip('.')}"
        try:
            with open(path, "x", encoding="utf-8") as handle:
                handle.write(content)
            logger.info("Saved %s", path.name)
            return path
        except FileExistsError:
            continue
        except PermissionError:
            raise FileOperationError(f"Permission denied writing: {path}") from None
        except OSError as exc:
            raise FileOperationError(f"Could not write file: {path}") from exc
    raise FileOperationError("Could not find an unused file name.")


def save_json(data: Dict[str, Any], directory: Path | str, stem: str) -> Path:
    """Save ``data`` as readable UTF-8 JSON in a new, uniquely named file."""
    try:
        text = json.dumps(data, indent=2, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise FileOperationError("Data could not be converted to JSON.") from exc
    return _write_unique(directory, stem, "json", text + "\n")


def save_text(
    content: str, directory: Path | str, stem: str, extension: str = "txt"
) -> Path:
    """Save a report (TXT or HTML) in a new, uniquely named file."""
    return _write_unique(directory, stem, extension, content)


def load_json(path: Path | str) -> Any:
    """Load a JSON file.

    Raises:
        FileOperationError: missing file, no permission or invalid JSON.
    """
    file_path = Path(path)
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise FileOperationError(f"File not found: {file_path.name}") from None
    except PermissionError:
        raise FileOperationError(
            f"Permission denied reading: {file_path.name}"
        ) from None
    except json.JSONDecodeError as exc:
        raise FileOperationError(
            f"'{file_path.name}' is not valid JSON "
            f"(line {exc.lineno}, column {exc.colno})."
        ) from exc
    except UnicodeDecodeError as exc:
        raise FileOperationError(
            f"'{file_path.name}' is not valid UTF-8 text."
        ) from exc
    except OSError as exc:
        raise FileOperationError(f"Could not read file: {file_path.name}") from exc


def save_candidate_profile(
    candidate: Candidate, directory: Path | str = DEFAULT_OUTPUT_DIR
) -> Path:
    """Save the extracted candidate profile as JSON."""
    stem = f"candidate_{Path(candidate.source_file or 'resume').stem}"
    return save_json(candidate.to_dict(), directory, stem)


def save_match_result(
    candidate: Candidate,
    job: Job,
    result: MatchResult,
    directory: Path | str = DEFAULT_OUTPUT_DIR,
) -> Path:
    """Save the job, score breakdown and recommendation as JSON."""
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_source_file": candidate.source_file,
        "job": job.to_dict(),
        "result": result.to_dict(),
    }
    stem = f"result_{Path(candidate.source_file or 'resume').stem}"
    return save_json(payload, directory, stem)


def load_candidate_profile(path: Path | str) -> Candidate:
    """Load a saved candidate profile (validated)."""
    return Candidate.from_dict(_expect_object(load_json(path), path))


def load_job(path: Path | str) -> Job:
    """Load a job description JSON file (validated)."""
    return Job.from_dict(_expect_object(load_json(path), path))


def load_match_result(path: Path | str) -> Optional[MatchResult]:
    """Load the ``result`` part of a file written by :func:`save_match_result`."""
    payload = _expect_object(load_json(path), path)
    if "result" not in payload:
        raise FileOperationError(f"'{Path(path).name}' has no 'result' section.")
    return MatchResult.from_dict(payload["result"])


def _expect_object(data: Any, path: Path | str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise FileOperationError(f"'{Path(path).name}' must contain a JSON object.")
    return data


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "ensure_directory",
    "load_candidate_profile",
    "load_job",
    "load_json",
    "load_match_result",
    "save_candidate_profile",
    "save_json",
    "save_match_result",
    "save_text",
]
