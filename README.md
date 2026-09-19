# Intelligent Resume Analyzer

## 1. Project Overview

Intelligent Resume Analyzer is a beginner-friendly Python command-line tool
for screening a resume against a job's requirements. It extracts candidate
details, compares skills and experience, and generates a readable report and
JSON output.

The project is designed as a transparent first-pass screening aid. It should
support human review rather than replace human hiring decisions.

## 2. Problem Statement

Manually comparing every resume with a job description can be repetitive and
time-consuming. Important details such as required skills, years of experience,
and missing qualifications can also be overlooked.

This project provides a small, consistent workflow for extracting key resume
information and comparing it with clearly defined job requirements.

## 3. Features

- Accepts resume text interactively from the terminal.
- Extracts the candidate name, email, skills, and years of experience.
- Accepts required skills and required years of experience.
- Calculates a match score from 0 to 100.
- Displays matched skills and missing skills.
- Provides a hiring recommendation based on the score.
- Saves parsed resume data to `resume.json`.
- Saves the final analysis to `analysis_report.json`.
- Handles incomplete resume data and invalid input without crashing.

## 4. Technologies Used

- Python 3.8 or newer
- Python standard library only
- `re` for text and pattern matching
- `json` for structured file storage
- `pathlib` for file operations
- Type hints from `typing`

No third-party packages are required. The dependency list is kept in
`requirements.txt` for consistent project setup.

## 5. Project Structure

```text
Intelligent-Resume-Analyzer_HiDevs/
|-- app.py                  # Command-line application entry point
|-- resume_parser.py        # Extracts structured resume information
|-- matcher.py              # Calculates the candidate match score
|-- report_generator.py     # Handles JSON and report formatting
|-- requirements.txt        # Project dependency information
|-- README.md               # Project documentation
|-- resume.json             # Generated parsed resume data
`-- analysis_report.json    # Generated final analysis
```

### Module Responsibilities

- `app.py` reads input and coordinates the complete workflow.
- `resume_parser.py` extracts the candidate name, email, skills, and
	experience.
- `matcher.py` compares candidate information with job requirements.
- `report_generator.py` saves and loads JSON and formats the terminal report.

## 6. How the Resume Parser Works

The parser receives the resume as plain text and returns a dictionary with
these fields:

```json
{
	"name": "Alex Morgan",
	"email": "alex@example.com",
	"skills": ["docker", "python", "sql"],
	"years_experience": 5.0
}
```

The parser:

1. Reads the first meaningful resume line as the candidate name.
2. Supports common formats such as `Name: Alex Morgan` and a name followed by
	 an email address on the same line.
3. Finds an email address using a regular expression.
4. Searches for known skills and skills listed in the resume.
5. Detects numeric phrases such as `5 years of experience`.
6. Uses `None`, an empty list, or `0.0` when information is unavailable.

## 7. How the Matching Score Is Calculated

The final score combines skills and experience:

```text
skill score      = matched required skills / total required skills * 100
experience score = min(candidate years / required years, 1) * 100
match score      = skill score * 0.70 + experience score * 0.30
```

Skills contribute 70% of the score and experience contributes 30%. Experience
is capped at 100%, so having more experience than required does not increase
that component beyond its maximum.

When no skills or no experience are required, that score component receives
100. Recommendations are assigned as follows:

| Score | Recommendation |
| --- | --- |
| 75-100 | Strongly recommend |
| 50-74 | Consider for interview |
| 0-49 | Do not recommend |

## 8. JSON File Handling

The application uses two generated JSON files:

- `resume.json` stores the parsed candidate information.
- `analysis_report.json` stores the final report, including score, matched
	skills, missing skills, and recommendation.

The application loads `resume.json` again before matching. JSON read and write
operations are handled through functions in `report_generator.py`. Missing,
malformed, unreadable, or non-object JSON files produce a safe fallback rather
than an unhandled exception.

## 9. Error Handling

The application safely handles:

- Empty resume input
- Missing candidate name or email
- Missing skills
- Invalid or negative experience input
- Missing JSON files
- Malformed JSON content
- File read and write errors

Missing report values are displayed as `Not provided`, while invalid numeric
experience values default to zero. The program continues and generates a
report whenever possible.

## 10. How to Install and Run

### Prerequisites

Install Python 3.8 or newer and confirm it is available:

```sh
python3 --version
```

### Installation

From the project directory, install the listed requirements:

```sh
python3 -m pip install -r requirements.txt
```

There are currently no third-party dependencies, so installation is minimal.

### Running the Application

```sh
python3 app.py
```

Enter resume text one line at a time. Press Enter on a blank line to finish the
resume. Then enter required skills separated by commas and the required years
of experience. The generated JSON files are written to the project directory.

## 11. Sample Input and Output

### Sample Input

```text
Alex Morgan
alex@example.com
Python, SQL, Docker
5 years of experience

Python, SQL, React
3
```

The first four lines are resume text. After the blank line, `Python, SQL, React`
is the required skill list and `3` is the required experience.

### Sample Output

```text
====================================================
INTELLIGENT RESUME ANALYZER REPORT
====================================================
Candidate: Alex Morgan
Email: alex@example.com
Experience: 5.0 years
Match score: 77/100
Matched skills: python, sql
Missing skills: react
Recommendation: Strongly recommend
====================================================
```

The same analysis is also saved in `analysis_report.json`.

## 12. Future Improvements

- Accept uploaded PDF and DOCX resume files.
- Extract skills from a larger, configurable skills dictionary.
- Support job descriptions as text instead of separate skill input.
- Improve name and experience extraction with richer natural-language rules.
- Add a web interface for non-technical users.
- Add automated unit tests and test coverage reporting.
- Support configurable score weights and recommendation thresholds.
- Store analysis history in a database.
- Add privacy controls for securely removing resume data.
