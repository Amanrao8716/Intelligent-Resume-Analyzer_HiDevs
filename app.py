"""Command-line entry point for the Intelligent Resume Analyzer."""

from resume_parser import parse_resume
from matcher import match_resume
from report_generator import create_report, format_report, load_json, save_json


RESUME_FILE = "resume.json"
REPORT_FILE = "analysis_report.json"


def read_resume_text() -> str:
    """Read multiple resume lines until the user enters a blank line."""
    print("Enter resume text one line at a time. Press Enter on a blank line to finish.")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def read_required_skills() -> list:
    """Read a comma-separated skill list, allowing an empty list."""
    value = input("Required skills (comma-separated, optional): ").strip()
    return [skill.strip() for skill in value.split(",") if skill.strip()]


def read_required_years() -> float:
    """Read required experience safely, defaulting invalid input to zero."""
    value = input("Required years of experience (optional): ").strip()
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except ValueError:
        print("Invalid experience input; using 0 years.")
        return 0.0


def main() -> None:
    """Run one complete resume analysis."""
    resume_text = read_resume_text()
    required_skills = read_required_skills()
    required_years = read_required_years()

    if not resume_text:
        print("No resume text was provided. A report will still be generated.")

    resume_data = parse_resume(resume_text, required_skills)
    if not save_json(resume_data, RESUME_FILE):
        print(f"Warning: could not save {RESUME_FILE}.")

    saved_resume = load_json(RESUME_FILE) or resume_data
    match_data = match_resume(
        saved_resume.get("skills", []),
        required_skills,
        saved_resume.get("years_experience", 0),
        required_years,
    )
    report = create_report(saved_resume, match_data)

    if save_json(report, REPORT_FILE):
        print(f"Saved parsed resume to {RESUME_FILE}.")
        print(f"Saved analysis report to {REPORT_FILE}.")
    else:
        print(f"Warning: could not save {REPORT_FILE}.")
    print(format_report(report))


if __name__ == "__main__":
    main()
