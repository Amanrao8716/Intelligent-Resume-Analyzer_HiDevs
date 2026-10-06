"""Tests for JSON saving/loading and safe file handling."""

import json

import pytest

import file_manager
from file_manager import (
    load_candidate_profile,
    load_job,
    load_json,
    load_match_result,
    save_candidate_profile,
    save_json,
    save_match_result,
    save_text,
)
from matcher import score_candidate
from models import Candidate, Job
from utils import FileOperationError, ValidationError
from conftest import SAMPLE_JOBS


def test_save_and_load_candidate_roundtrip(tmp_path, strong_candidate):
    path = save_candidate_profile(strong_candidate, tmp_path)
    assert path.suffix == ".json"
    assert load_candidate_profile(path) == strong_candidate


def test_json_is_valid_readable_utf8(tmp_path):
    candidate = Candidate(name="Jos\u00e9 \u00c5ngstr\u00f6m", skills=["python"])
    path = save_candidate_profile(candidate, tmp_path)
    raw = path.read_text(encoding="utf-8")
    assert "Jos\u00e9" in raw  # not escaped to \u00e9
    assert "\n  " in raw  # indented
    assert json.loads(raw)["skills"] == ["python"]


def test_output_directory_created_automatically(tmp_path, strong_candidate):
    target = tmp_path / "a" / "b" / "outputs"
    path = save_candidate_profile(strong_candidate, target)
    assert path.parent == target and path.exists()


def test_existing_files_never_overwritten(tmp_path):
    paths = {save_json({"n": i}, tmp_path, "same") for i in range(5)}
    assert len(paths) == 5
    contents = sorted(json.loads(p.read_text())["n"] for p in paths)
    assert contents == [0, 1, 2, 3, 4]


def test_save_and_load_match_result(tmp_path, strong_candidate, backend_job):
    result = score_candidate(strong_candidate, backend_job)
    path = save_match_result(strong_candidate, backend_job, result, tmp_path)
    assert load_match_result(path) == result
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["job"]["title"] == backend_job.title
    assert payload["result"]["score"] == result.score


def test_load_missing_file(tmp_path):
    with pytest.raises(FileOperationError, match="not found"):
        load_json(tmp_path / "nope.json")


def test_load_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json,,", encoding="utf-8")
    with pytest.raises(FileOperationError, match="not valid JSON"):
        load_json(bad)
    with pytest.raises(FileOperationError):
        load_candidate_profile(bad)


def test_load_json_that_is_not_an_object(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(FileOperationError, match="JSON object"):
        load_candidate_profile(path)


def test_load_wrong_types_fail_validation(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"skills": "python"}), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_candidate_profile(path)


def test_load_binary_garbage(tmp_path):
    path = tmp_path / "garbage.json"
    path.write_bytes(b"\xff\xfe\x00\x81\x82")
    with pytest.raises(FileOperationError):
        load_json(path)


def test_permission_error_is_reported(tmp_path, monkeypatch):
    def deny(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("builtins.open", deny)
    with pytest.raises(FileOperationError, match="Permission denied"):
        save_json({"a": 1}, tmp_path, "x")


def test_unwritable_directory(tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(FileOperationError):
        save_text("report", blocker / "sub", "r")


def test_unserializable_data(tmp_path):
    with pytest.raises(FileOperationError, match="JSON"):
        save_json({"bad": object()}, tmp_path, "x")


def test_save_text_report_extensions(tmp_path):
    txt = save_text("hello", tmp_path, "report", "txt")
    html = save_text("<p>hi</p>", tmp_path, "report", ".html")
    assert txt.suffix == ".txt" and html.suffix == ".html"


def test_filename_is_sanitized(tmp_path):
    path = save_text("x", tmp_path, "../../evil name?.pdf", "txt")
    assert path.parent == tmp_path


def test_load_sample_jobs():
    for path in SAMPLE_JOBS.glob("*.json"):
        job = load_job(path)
        assert isinstance(job, Job) and job.title


def test_default_output_dir_constant():
    assert str(file_manager.DEFAULT_OUTPUT_DIR) == "outputs"
