# Intelligent Resume Analyzer

A Python application that screens resumes automatically. It reads PDF/TXT resumes,
extracts candidate information, compares it with job requirements using a
**deterministic, explainable 0-100 score**, and produces recommendations and
professional reports. Optional AI features add suggestions but never touch the score.

## Key features

- Reads **PDF** (via `pypdf`) and **TXT** resumes; handles empty, corrupted, encrypted and
  unsupported files with clear messages.
- Extracts name, email, phone, technical skills, soft skills, years of experience,
  education, certifications and projects using regular expressions and an
  **extendable skill dictionary** (aliases such as `JS` -> `javascript`, no duplicates).
- Never invents data: anything not found is `None` or an empty list.
- Weighted scoring (required skills 50, preferred skills 15, experience 25, education 10)
  with a per-component breakdown, matched/missing skills and a written explanation.
- Recommendation bands: 80-100 Strongly Recommend, 60-79 Recommend, 40-59 Consider,
  0-39 Not Recommended.
- Saves candidate profiles, match results (JSON) and reports (TXT and HTML) with unique
  file names, so earlier results are never overwritten.
- Streamlit interface: multi-resume upload, ranked comparison, report download, reset.
- Optional AI layer (extraction suggestions, skill categories, explanation, interview
  questions) with output validation and a rule-based fallback. Works with **no API key**.
- Custom exceptions, `logging` (no personal data in logs) and **163 pytest tests**.

## Technology stack

Python 3.10+, Streamlit (UI), pypdf (PDF text), pytest (tests), standard library only for
everything else (`re`, `dataclasses`, `json`, `logging`, `urllib`).

## Architecture and data flow

```
PDF/TXT upload --> resume_parser.py --> Candidate (models.py)
                                              |
Job form / job JSON --> Job (models.py) ------+--> matcher.py --> MatchResult
                                                        |
                    ai_prompts.py (optional AI, with fallback) --+
                                                        |
        report_generator.py (TXT/HTML)  +  file_manager.py (JSON/TXT/HTML on disk)
                                                        |
                                                     app.py (UI)
```

| File | Responsibility |
|------|----------------|
| `app.py` | Streamlit interface and entry point |
| `resume_parser.py` | Reading PDF/TXT, text cleaning, section detection, field extraction |
| `matcher.py` | Scoring, recommendation bands, strengths/gaps, explanation |
| `report_generator.py` | Text and HTML reports |
| `file_manager.py` | Safe JSON/TXT/HTML saving and JSON loading |
| `models.py` | `Candidate`, `Job`, `MatchResult` dataclasses with validation |
| `ai_prompts.py` | Prompt templates, small API client, output validators, fallbacks |
| `utils.py` | Exceptions, logging setup, text helpers, `SkillDictionary` |

## Project structure

```
resume_analyzer/
|-- app.py
|-- resume_parser.py
|-- matcher.py
|-- report_generator.py
|-- file_manager.py
|-- models.py
|-- ai_prompts.py
|-- utils.py
|-- requirements.txt
|-- pytest.ini
|-- README.md
|-- sample_data/
|   |-- resumes/   (5 TXT resumes + 1 PDF)
|   `-- jobs/      (4 job descriptions as JSON)
|-- outputs/       (generated JSON results, reports and analyzer.log)
`-- tests/         (pytest suite)
```

## Installation

```bash
cd resume_analyzer
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Environment variables (optional AI)

The analyzer works without any key. To enable the optional AI suggestions set **one** of:

```bash
export ANTHROPIC_API_KEY="your-key"     # optional: ANTHROPIC_MODEL
# or
export OPENAI_API_KEY="your-key"        # optional: OPENAI_MODEL
```

Never put keys in the code. When AI is used, resume text is sent to the provider with
e-mail addresses and phone numbers replaced by `[EMAIL]` / `[PHONE]`.

## Run the application

```bash
streamlit run app.py
```

In GitHub Codespaces, open the forwarded port 8501 when prompted. In the app:
1. Pick a sample job in the sidebar (or type your own requirements).
2. Upload resumes, or pick sample resumes from the drop-down.
3. Click **Analyze resumes**. Use **Reset everything** to start over.

Generated files appear in `outputs/` (`candidate_*.json`, `result_*.json`,
`report_*.txt`, `report_*.html`).

## Run the tests

```bash
python -m pytest
```

## Scoring rules

| Component | Points | Rule |
|-----------|--------|------|
| Required skills | 50 | 50 x matched / required |
| Preferred skills | 15 | 15 x matched / preferred (skills also listed as required are not counted twice) |
| Experience | 25 | 25 x min(candidate years / minimum years, 1); unknown experience counts as 0 |
| Education | 10 | Levels: Diploma 1, Bachelor's 2, Master's 3, PhD 4. Meeting/exceeding the level = full points, otherwise candidate level / required level |

Skill names are normalized (case, aliases) before comparison. If a job leaves a component
empty (e.g. no preferred skills), that component is skipped and the remaining weights are
scaled so the total is still 100; this prevents division by zero and "free" points. A job
with no requirements at all is rejected with a validation error. The same input always
gives the same score.

## Sample input and output

Resume `sample_data/resumes/anita_desai.txt` against `python_backend_developer.json`:

```
Overall match score: 55 / 100
Required skills:   20 / 50 points - 2 of 5 required skills matched
Preferred skills:  0 / 15 points - 0 of 4 preferred skills matched
Experience:        25 / 25 points - 3 years vs 3 required
Education:         10 / 10 points - Candidate: Master's degree; required: Bachelor's degree
Matched skills (required):  python, sql
Missing skills (required):  django, rest api, git
RECOMMENDATION: Consider
```

Saved profile (`outputs/candidate_*.json`, shortened):

```json
{
  "name": "Anita Desai",
  "email": "anita.desai@example.com",
  "skills": ["python", "sql", "pandas", "tableau"],
  "experience": 3.0,
  "projects": []
}
```

## Error handling approach

`ResumeAnalyzerError` is the base class of `ParseError`, `ValidationError`,
`FileOperationError` and `AIServiceError`. Low-level errors (missing file, permissions,
invalid JSON, corrupted PDF, HTTP failures) are converted into these exceptions with
readable messages. The UI shows the message for the failing resume while other resumes
still get analyzed. Unexpected errors are logged with a traceback to `outputs/analyzer.log`
and shown as a generic message. Logs and messages never contain resume text, names, e-mail
addresses, phone numbers or API keys.

## Limitations

- Skill detection is dictionary-based: skills outside `TECHNICAL_SKILLS` / `SOFT_SKILLS` in
  `utils.py` are not found (extend with `SkillDictionary.add_skill`).
- Scanned/image-only PDFs have no text layer and are rejected (no OCR).
- Name extraction is a heuristic (a "Name:" label or a short first line); unusual layouts
  may give `None`.
- Experience comes from an explicit statement ("5 years of experience") or date ranges in an
  Experience section; ranges written with years only count January to January.
- A bare "C" is only detected inside the skills section.
- Because experience (25) and education (10) are worth points, a candidate missing several
  required skills can still reach "Consider" or "Recommend"; always read the breakdown.
- The AI client (`urllib`, Anthropic/OpenAI) is covered by unit tests with fake responses,
  but was not run against the live services.

## Future enhancements

OCR for scanned PDFs, DOCX support, semantic skill matching, configurable weights in the UI,
and a database for candidate history.
