"""Headless smoke tests of the Streamlit interface (uses sample data only)."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from conftest import PROJECT_ROOT  # noqa: E402


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_ANALYZER_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    test = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=60)
    test.run()
    return test


def _click(app, label):
    button = next(b for b in app.button if b.label == label)
    button.click().run()


def _select_job_and_resumes(app, job_file, resumes):
    app.selectbox(key="sample_job").select(job_file).run()
    app.multiselect(key="sample_resumes").set_value(resumes).run()


def test_app_starts_without_errors(app):
    assert not app.exception
    assert app.title[0].value == "Intelligent Resume Analyzer"


def test_analyze_without_resume_shows_error(app):
    _click(app, "Analyze resumes")
    assert any("at least one resume" in e.value for e in app.error)


def test_job_is_prefilled_on_first_visit(app):
    assert app.text_input(key="job_title").value == "Python Backend Developer"
    assert app.text_area(key="job_required").value


def test_empty_job_requirements_show_error(app):
    app.text_input(key="job_title").set_value("").run()
    app.text_area(key="job_required").set_value("").run()
    app.text_area(key="job_preferred").set_value("").run()
    app.number_input(key="job_min_exp").set_value(0.0).run()
    app.selectbox(key="job_education").select("Not required").run()
    app.multiselect(key="sample_resumes").set_value(["priya_sharma.txt"]).run()
    _click(app, "Analyze resumes")
    assert any("Job requirements problem" in e.value for e in app.error)


def test_single_resume_analysis_and_saved_files(app, tmp_path):
    _select_job_and_resumes(app, "python_backend_developer.json", ["priya_sharma.txt"])
    assert app.text_input(key="job_title").value == "Python Backend Developer"
    _click(app, "Analyze resumes")
    assert not app.exception
    assert not app.error
    assert app.metric[0].value == "100 / 100"
    assert any("Strongly Recommend" in s.value for s in app.success)
    saved = {p.suffix for p in tmp_path.iterdir()}
    assert {".json", ".txt", ".html"} <= saved


def test_multiple_resumes_show_comparison_and_bad_input_is_isolated(app):
    _select_job_and_resumes(
        app,
        "data_analyst.json",
        ["anita_desai.txt", "rahul_verma.txt", "priya_sharma.pdf"],
    )
    _click(app, "Analyze resumes")
    assert not app.exception
    assert len(app.expander) >= 3
    assert any(sub.value == "Candidate comparison" for sub in app.subheader)


def test_reset_clears_everything(app):
    _select_job_and_resumes(app, "data_analyst.json", ["anita_desai.txt"])
    _click(app, "Analyze resumes")
    assert app.session_state["results"]
    _click(app, "Reset everything")
    assert app.session_state["results"] == []
    assert app.text_input(key="job_title").value == ""
    assert app.multiselect(key="sample_resumes").value == []


def test_ai_checkbox_without_key_falls_back(app):
    _select_job_and_resumes(app, "data_analyst.json", ["anita_desai.txt"])
    next(c for c in app.checkbox if c.label.startswith("Use optional AI")).check().run()
    _click(app, "Analyze resumes")
    assert not app.exception
    assert any("No AI API key" in i.value for i in app.info)
    assert app.session_state["results"][0]["questions_source"] == "rule-based"
