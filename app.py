"""Streamlit interface for the Intelligent Resume Analyzer.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from ai_prompts import (
    AIClient,
    ai_extract_resume_info,
    categorize_skills,
    explain_match,
    generate_interview_questions,
)
from file_manager import (
    load_job,
    save_candidate_profile,
    save_match_result,
    save_text,
)
from matcher import score_candidate
from models import Job
from report_generator import generate_html_report, generate_text_report
from resume_parser import extract_text_from_bytes, parse_resume_text
from utils import (
    FileOperationError,
    ResumeAnalyzerError,
    SkillDictionary,
    ValidationError,
    get_logger,
    setup_logging,
    split_items,
)

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_RESUME_DIR = BASE_DIR / "sample_data" / "resumes"
SAMPLE_JOB_DIR = BASE_DIR / "sample_data" / "jobs"
OUTPUT_DIR = Path(os.environ.get("RESUME_ANALYZER_OUTPUT_DIR", BASE_DIR / "outputs"))
EDUCATION_OPTIONS = ["Not required", "Diploma", "Bachelor's", "Master's", "PhD"]
CUSTOM_JOB = "Custom job"
DEFAULT_SAMPLE_JOB = "python_backend_developer.json"

logger = get_logger("app")

JOB_DEFAULTS: Dict[str, Any] = {
    "job_title": "",
    "job_required": "",
    "job_preferred": "",
    "job_min_exp": 0.0,
    "job_education": EDUCATION_OPTIONS[0],
    "job_description": "",
    "job_auto_detect": False,
}


# --------------------------------------------------------------------------
# State handling
# --------------------------------------------------------------------------


def init_state() -> None:
    """Create session-state defaults on the first run."""
    st.session_state.setdefault("results", [])
    st.session_state.setdefault("uploader_key", 0)
    st.session_state.setdefault("sample_job", CUSTOM_JOB)
    st.session_state.setdefault("sample_resumes", [])
    for key, value in JOB_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    if not st.session_state.get("job_initialized"):
        # First visit: pre-fill a sample job so the app is usable immediately.
        st.session_state["job_initialized"] = True
        if (SAMPLE_JOB_DIR / DEFAULT_SAMPLE_JOB).exists():
            st.session_state["sample_job"] = DEFAULT_SAMPLE_JOB
            load_sample_job_into_form()


def reset_app() -> None:
    """Clear results, uploads and the job form (used as a button callback)."""
    st.session_state["results"] = []
    st.session_state["uploader_key"] += 1
    st.session_state["sample_job"] = CUSTOM_JOB
    st.session_state["sample_resumes"] = []
    for key, value in JOB_DEFAULTS.items():
        st.session_state[key] = value


def load_sample_job_into_form() -> None:
    """Fill the job form from the selected sample job (selectbox callback)."""
    choice = st.session_state.get("sample_job", CUSTOM_JOB)
    if choice == CUSTOM_JOB:
        return
    try:
        job = load_job(SAMPLE_JOB_DIR / choice)
    except ResumeAnalyzerError as exc:
        st.session_state["job_load_error"] = str(exc)
        return
    st.session_state.pop("job_load_error", None)
    st.session_state["job_title"] = job.title
    st.session_state["job_required"] = ", ".join(job.required_skills)
    st.session_state["job_preferred"] = ", ".join(job.preferred_skills)
    st.session_state["job_min_exp"] = float(job.min_experience)
    education = job.required_education or ""
    matches = [
        o for o in EDUCATION_OPTIONS[1:] if o.lower().startswith(education[:4].lower())
    ]
    st.session_state["job_education"] = (
        matches[0] if (education and matches) else EDUCATION_OPTIONS[0]
    )
    st.session_state["job_description"] = job.job_description


# --------------------------------------------------------------------------
# Job form and analysis
# --------------------------------------------------------------------------


def build_job_from_form() -> Job:
    """Create a Job from the sidebar form values."""
    required = split_items(st.session_state["job_required"])
    description = st.session_state["job_description"].strip()
    if not required and st.session_state["job_auto_detect"] and description:
        required = SkillDictionary.technical().find_in_text(description)
    education = st.session_state["job_education"]
    return Job(
        title=st.session_state["job_title"].strip(),
        required_skills=required,
        preferred_skills=split_items(st.session_state["job_preferred"]),
        min_experience=float(st.session_state["job_min_exp"]),
        required_education=None if education == EDUCATION_OPTIONS[0] else education,
        job_description=description,
    )


def analyze_one(
    filename: str, data: bytes, job: Job, client: Optional[AIClient]
) -> Dict[str, Any]:
    """Analyze a single resume and return a result entry for the UI."""
    entry: Dict[str, Any] = {"filename": filename, "warnings": []}
    try:
        text = extract_text_from_bytes(data, filename)
        candidate = parse_resume_text(text, source_file=filename)
        result = score_candidate(candidate, job)
        questions, questions_source = generate_interview_questions(
            candidate, job, result, client
        )
        ai_commentary, _ = explain_match(candidate, job, result, client)
        categories, categories_source = categorize_skills(candidate.skills, client)
        ai_extra, ai_status = (None, "")
        if client is not None:
            ai_extra, ai_status = ai_extract_resume_info(text, client)
        text_report = generate_text_report(
            candidate, job, result, questions, questions_source, ai_commentary
        )
        html_report = generate_html_report(
            candidate, job, result, questions, questions_source, ai_commentary
        )
        saved: List[str] = []
        try:
            saved.append(save_candidate_profile(candidate, OUTPUT_DIR).name)
            saved.append(save_match_result(candidate, job, result, OUTPUT_DIR).name)
            stem = f"report_{Path(filename).stem}"
            saved.append(save_text(text_report, OUTPUT_DIR, stem, "txt").name)
            saved.append(save_text(html_report, OUTPUT_DIR, stem, "html").name)
        except FileOperationError as exc:
            entry["warnings"].append(f"Results could not be saved to disk: {exc}")
        entry.update(
            candidate=candidate,
            result=result,
            questions=questions,
            questions_source=questions_source,
            ai_commentary=ai_commentary,
            categories=categories,
            categories_source=categories_source,
            ai_extra=ai_extra,
            ai_status=ai_status,
            text_report=text_report,
            html_report=html_report,
            saved=saved,
        )
    except ResumeAnalyzerError as exc:
        logger.warning("Analysis failed: %s", exc.__class__.__name__)
        entry["error"] = str(exc)
    except Exception:  # last resort: never crash the whole page
        logger.exception("Unexpected error while analyzing a resume")
        entry["error"] = (
            "An unexpected error occurred while analyzing this resume. "
            "Details were written to the log."
        )
    return entry


def collect_resumes(
    uploads: List[Any], sample_names: List[str]
) -> List[Tuple[str, bytes]]:
    """Gather (filename, bytes) pairs from uploads and selected samples."""
    items = [(upload.name, upload.getvalue()) for upload in uploads]
    for name in sample_names:
        try:
            items.append((name, (SAMPLE_RESUME_DIR / name).read_bytes()))
        except OSError:
            st.warning(f"Could not read sample resume '{name}'.")
    return items


def run_analysis(items: List[Tuple[str, bytes]], use_ai: bool) -> None:
    """Validate the job, analyze every resume and store results in session state."""
    job = build_job_from_form()
    try:
        job.validate()
    except ValidationError as exc:
        st.error(f"Job requirements problem: {exc}")
        return
    client = AIClient.from_env() if use_ai else None
    if use_ai and client is None:
        st.info(
            "No AI API key found (set ANTHROPIC_API_KEY or OPENAI_API_KEY). "
            "Using the built-in rule-based analysis instead."
        )
    results = []
    progress = st.progress(0.0, text="Analyzing resumes...")
    for index, (filename, data) in enumerate(items, start=1):
        results.append(analyze_one(filename, data, job, client))
        progress.progress(index / len(items), text=f"Analyzed {index} of {len(items)}")
    progress.empty()
    st.session_state["results"] = results


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def show_recommendation(label: str, score: float) -> None:
    """Show the recommendation in a colour that matches its band."""
    message = f"Recommendation: {label} ({score:g}/100)"
    if score >= 80:
        st.success(message)
    elif score >= 60:
        st.info(message)
    elif score >= 40:
        st.warning(message)
    else:
        st.error(message)


def skill_text(skills: List[str]) -> str:
    return ", ".join(f"`{s}`" for s in skills) if skills else "_None_"


def render_comparison(entries: List[Dict[str, Any]]) -> None:
    """Ranked comparison table for several analyzed resumes."""
    ranked = sorted(entries, key=lambda e: e["result"].score, reverse=True)
    rows = [
        {
            "Rank": rank,
            "File": entry["filename"],
            "Candidate": entry["candidate"].name or "Not found",
            "Score": entry["result"].score,
            "Recommendation": entry["result"].recommendation,
            "Missing required": ", ".join(entry["result"].missing_required) or "-",
        }
        for rank, entry in enumerate(ranked, start=1)
    ]
    st.subheader("Candidate comparison")
    st.table(rows)


def render_entry(entry: Dict[str, Any], index: int, expanded: bool) -> None:
    """Render the full analysis of one resume."""
    if "error" in entry:
        st.error(f"{entry['filename']}: {entry['error']}")
        return
    candidate, result = entry["candidate"], entry["result"]
    title = f"{candidate.name or entry['filename']} - {result.score:g}/100"
    with st.expander(title, expanded=expanded):
        for warning in entry["warnings"]:
            st.warning(warning)
        left, right = st.columns([1, 2])
        left.metric("Match score", f"{result.score:g} / 100")
        right.progress(min(max(result.score / 100, 0.0), 1.0))
        with right:
            show_recommendation(result.recommendation, result.score)

        st.markdown("#### Candidate information")
        info_left, info_right = st.columns(2)
        info_left.markdown(
            f"**Name:** {candidate.name or 'Not found'}  \n"
            f"**Email:** {candidate.email or 'Not found'}  \n"
            f"**Phone:** {candidate.phone or 'Not found'}  \n"
            "**Experience:** "
            + (
                "Not found"
                if candidate.experience is None
                else f"{candidate.experience:g} years"
            )
        )
        info_right.markdown(
            "**Education:** "
            + ("; ".join(candidate.education) if candidate.education else "Not found")
            + "  \n**Certifications:** "
            + ("; ".join(candidate.certifications) or "None")
            + "  \n**Projects:** "
            + ("; ".join(candidate.projects) or "None")
        )
        st.markdown(f"**Technical skills:** {skill_text(candidate.skills)}")
        st.markdown(f"**Soft skills:** {skill_text(candidate.soft_skills)}")

        st.markdown("#### Matched and missing skills")
        col_a, col_b = st.columns(2)
        col_a.markdown(
            f"**Matched (required):** {skill_text(result.matched_required)}  \n"
            f"**Matched (preferred):** {skill_text(result.matched_preferred)}"
        )
        col_b.markdown(
            f"**Missing (required):** {skill_text(result.missing_required)}  \n"
            f"**Missing (preferred):** {skill_text(result.missing_preferred)}"
        )

        st.markdown("#### Scoring breakdown")
        st.table(
            [
                {
                    "Component": item["label"],
                    "Points": item["points"] if item["applicable"] else "skipped",
                    "Max": item["max_points"] if item["applicable"] else "-",
                    "Detail": item["detail"],
                }
                for item in result.breakdown.values()
            ]
        )
        st.markdown("#### Explanation")
        st.write(result.explanation)
        strengths_col, gaps_col = st.columns(2)
        strengths_col.markdown("**Strengths**")
        for item in result.strengths or ["None identified"]:
            strengths_col.markdown(f"- {item}")
        gaps_col.markdown("**Areas for improvement**")
        for item in result.improvements or ["None identified"]:
            gaps_col.markdown(f"- {item}")

        st.markdown(f"#### Suggested interview questions ({entry['questions_source']})")
        for question in entry["questions"]:
            st.markdown(f"- {question}")
        if entry["ai_commentary"]:
            st.markdown("**AI-generated commentary** (suggestion, not extracted fact)")
            st.write(entry["ai_commentary"])
        with st.expander(f"Skill categories ({entry['categories_source']})"):
            for category, skills in entry["categories"].items():
                if skills:
                    st.markdown(
                        f"**{category.replace('_', ' ').title()}:** "
                        f"{skill_text(skills)}"
                    )
        if entry["ai_status"]:
            extra = entry["ai_extra"]
            if extra is None:
                st.caption(entry["ai_status"])
            else:
                known = set(candidate.skills) | set(candidate.soft_skills)
                new_skills = [s for s in extra["skills"] if s.lower() not in known]
                st.caption(
                    "AI-found skills missed by the dictionary (verified in the "
                    f"resume text; please review): {', '.join(new_skills) or 'none'}"
                )

        st.markdown("#### Reports")
        download_a, download_b = st.columns(2)
        download_a.download_button(
            "Download report (TXT)",
            entry["text_report"],
            file_name=f"report_{index}.txt",
            mime="text/plain",
            key=f"txt_{index}",
        )
        download_b.download_button(
            "Download report (HTML)",
            entry["html_report"],
            file_name=f"report_{index}.html",
            mime="text/html",
            key=f"html_{index}",
        )
        if entry["saved"]:
            st.caption(f"Saved in outputs/: {', '.join(entry['saved'])}")


# --------------------------------------------------------------------------
# Page layout
# --------------------------------------------------------------------------


def render_sidebar() -> bool:
    """Draw the job form in the sidebar; returns the 'use AI' checkbox value."""
    with st.sidebar:
        st.header("Job requirements")
        samples = sorted(p.name for p in SAMPLE_JOB_DIR.glob("*.json"))
        st.selectbox(
            "Choose a sample job or enter your own",
            [CUSTOM_JOB, *samples],
            key="sample_job",
            on_change=load_sample_job_into_form,
        )
        if st.session_state.get("job_load_error"):
            st.error(st.session_state["job_load_error"])
        st.text_input("Job title", key="job_title")
        st.text_area(
            "Required skills (comma or line separated)", key="job_required", height=90
        )
        st.text_area("Preferred skills", key="job_preferred", height=70)
        st.number_input(
            "Minimum experience (years)",
            min_value=0.0,
            max_value=60.0,
            step=0.5,
            key="job_min_exp",
        )
        st.selectbox("Required education", EDUCATION_OPTIONS, key="job_education")
        st.text_area("Job description (optional)", key="job_description", height=90)
        st.checkbox(
            "If no required skills are typed, detect them from the description",
            key="job_auto_detect",
        )
        st.divider()
        use_ai = st.checkbox(
            "Use optional AI enhancements",
            value=False,
            help="Needs ANTHROPIC_API_KEY or OPENAI_API_KEY. Resume text is sent to "
            "the AI provider with e-mail and phone number removed.",
        )
        st.button("Reset everything", on_click=reset_app)
    return use_ai


def main() -> None:
    """Build the page."""
    st.set_page_config(page_title="Intelligent Resume Analyzer", layout="wide")
    setup_logging(OUTPUT_DIR / "analyzer.log")
    init_state()
    st.title("Intelligent Resume Analyzer")
    st.caption(
        "Upload resumes (PDF or TXT), describe the job in the sidebar, and get an "
        "explainable match score. The score is calculated by fixed rules, not by AI."
    )
    use_ai = render_sidebar()

    uploads = st.file_uploader(
        "Upload one or more resumes",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_key']}",
    )
    sample_files = sorted(p.name for p in SAMPLE_RESUME_DIR.glob("*") if p.is_file())
    sample_names = st.multiselect(
        "...or try sample resumes", sample_files, key="sample_resumes"
    )

    if st.button("Analyze resumes", type="primary"):
        items = collect_resumes(list(uploads or []), sample_names)
        if not items:
            st.error("Please upload at least one resume or select a sample resume.")
        else:
            run_analysis(items, use_ai)

    results = st.session_state["results"]
    if results:
        successful = [e for e in results if "error" not in e]
        if len(successful) > 1:
            render_comparison(successful)
        for index, entry in enumerate(results):
            render_entry(entry, index, expanded=len(results) == 1)


if __name__ == "__main__":
    main()
