# 🧠 Smart Hiring Assistant v2

> A production-grade resume intelligence system built entirely in Python — no external ML libraries required.

Automates candidate screening by parsing resumes, matching candidates to job requirements with a multi-factor scoring engine, and generating rich reports in plain text, JSON, and HTML.

---

## ✨ Features

| Feature | Details |
|---|---|
| **Advanced NLP Parser** | Multi-strategy extraction: section-aware parsing, regex patterns, heuristic confidence scoring |
| **Skill Taxonomy Engine** | 100+ skills grouped across 8 domains (languages, web, cloud, ML, etc.) with fuzzy adjacent-skill matching |
| **Weighted Scoring** | Configurable weights across skills (required + preferred), experience (with overqualification handling), and education |
| **Work History Parsing** | Structured extraction of job titles, companies, and date ranges |
| **3 Report Formats** | Plain text (terminal/email), JSON (APIs/tools), self-contained HTML (browser/sharing) |
| **Batch Analytics** | Score distributions, skill gap analysis, top candidate identification across candidate pools |
| **CLI Interface** | Full argparse CLI with 6 built-in job presets and directory-based batch processing |
| **56-Test Suite** | Unit + integration tests covering all components |
| **Zero Dependencies** | Pure Python stdlib — nothing to install |

---

## 📁 Project Structure

```
hiring_assistant/
│
├── hiring_assistant/           # Core package
│   ├── __init__.py             # Public API exports
│   ├── models.py               # Data models (Candidate, JobRequirement, MatchResult...)
│   ├── parser.py               # Resume parser with confidence scoring
│   ├── matcher.py              # Weighted matching engine
│   ├── analytics.py            # Batch analytics engine
│   ├── reporter.py             # TXT / HTML report generator
│   ├── file_manager.py         # JSON + file persistence
│   └── assistant.py            # Top-level orchestrator (HiringAssistant)
│
├── tests/
│   └── test_suite.py           # 56 unit + integration tests
│
├── data/
│   └── sample_resumes/         # Sample .txt resume files
│
├── output/                     # Generated reports (auto-created)
├── cli.py                      # Command-line interface
├── demo.py                     # Runnable demo (5 scenarios)
└── requirements.txt            # No external dependencies
```

---

## 🚀 Quick Start

```bash
# Clone and enter the project
git clone https://github.com/yourusername/smart-hiring-assistant.git
cd smart-hiring-assistant

# No pip install needed — pure stdlib!

# Run the full demo
python demo.py

# Analyze a single resume
python cli.py analyze --resume data/sample_resumes/alice.txt --job backend

# Rank multiple candidates
python cli.py rank --dir data/sample_resumes --job fullstack

# Run the test suite
python cli.py test

# See all job presets
python cli.py jobs
```

---

## 🔧 Python API

### Single Candidate Analysis

```python
from hiring_assistant import HiringAssistant
from hiring_assistant.models import JobRequirement, EducationLevel

assistant = HiringAssistant(output_dir="output")

job = JobRequirement(
    title="Senior Backend Engineer",
    required_skills=["python", "rest api", "postgresql", "docker", "git"],
    preferred_skills=["aws", "redis", "ci/cd"],
    min_experience=4,
    education_required=EducationLevel.BACHELOR,
)

with open("resume.txt") as f:
    resume_text = f.read()

candidate, results = assistant.process_resume(
    resume_text=resume_text,
    jobs=[job],
    save=True,           # saves JSON + TXT + HTML to output/
    generate_html=True,
)

print(f"Score: {results[0].overall_score}")
print(f"Recommendation: {results[0].recommendation.value}")
```

### Batch Ranking

```python
# Rank multiple candidates for one job
ranked = assistant.rank_candidates(
    resumes=[resume1_text, resume2_text, resume3_text],
    job=job,
    save=True,
)

for candidate, result in ranked:
    print(f"{result.candidate_name}: {result.overall_score:.1f}")
```

### Custom Scoring Weights

```python
from hiring_assistant.matcher import MatchWeights

# Skills-heavy weighting for highly technical roles
weights = MatchWeights(skills=0.70, experience=0.20, education=0.10)
assistant = HiringAssistant(weights=weights)
```

### Custom Skill Taxonomy

```python
# Add domain-specific skills not in the default taxonomy
assistant = HiringAssistant(
    custom_skills=["solidity", "web3.py", "hardhat", "ipfs", "rust"]
)
```

### Load From Directory

```python
# Process all .txt resumes in a folder
ranked = assistant.rank_from_directory("./resumes/", job=job)
```

---

## 📊 Scoring Model

The overall score (0–100) is a weighted composite:

```
Overall = Skills×0.55 + Experience×0.30 + Education×0.15
```

**Skills score breakdown:**
- Required skills coverage → 70% of skills score
- Preferred skills coverage → 30% of skills score
- Certification bonus → up to +5 bonus points
- Adjacent-skill credit via taxonomy matching

**Experience scoring:** Tiered ratio against requirement, with overqualification awareness.

**Education scoring:** Level-based comparison with partial credit for near-misses.

| Score | Recommendation |
|---|---|
| ≥ 80 | 🟢 Strong Match — Recommended for Interview |
| ≥ 65 | 🔵 Good Match — Consider for Interview |
| ≥ 50 | 🟡 Partial Match — Review Manually |
| ≥ 35 | 🟠 Weak Match — Not Recommended |
| < 35 | 🔴 Poor Match — Does Not Meet Requirements |

---

## 🧪 Tests

```bash
# Run via CLI
python cli.py test

# Or directly
python tests/test_suite.py

# Or with pytest
pytest tests/ -v
```

**56 tests across 7 test classes:**
- `TestResumeParser` — extraction accuracy (name, email, phone, skills, education...)
- `TestModels` — data model validation and serialization roundtrips
- `TestMatchingEngine` — scoring accuracy, edge cases, custom weights
- `TestReportGenerator` — TXT and HTML report content validation
- `TestAnalyticsEngine` — batch statistics and aggregation
- `TestFileManager` — file I/O, JSON persistence, batch loading
- `TestIntegration` — full end-to-end pipeline tests

---

## 📤 Output Files

For each candidate processed, the system generates:

| File | Format | Contents |
|---|---|---|
| `{name}_profile.json` | JSON | Full parsed candidate profile |
| `{name}_results.json` | JSON | Match scores with full breakdown |
| `{name}_report.txt` | Plain text | Human-readable analysis with ASCII bars |
| `{name}_report.html` | HTML | Rich self-contained visual report |
| `{job}_ranking.txt` | Plain text | Ranked candidate comparison |
| `{job}_analytics.json` | JSON | Batch analytics and score distribution |

---

## 🛠️ CLI Reference

```
python cli.py <command> [options]

Commands:
  analyze     Analyze a single resume against a job
  rank        Rank all resumes in a directory
  test        Run the test suite
  jobs        List all built-in job presets

Options:
  --output    Output directory (default: output/)
  --verbose   Enable debug logging

Analyze options:
  --resume    Path to resume .txt file
  --job       Job preset: backend | fullstack | junior | data | devops | ml
  --all-jobs  Match against all presets
  --no-html   Skip HTML report generation

Rank options:
  --dir       Directory containing .txt resume files
  --job       Job preset to rank against
```

---

## 🏗️ Architecture

```
Raw Resume Text
      │
      ▼
┌─────────────┐    Section-aware parsing
│ ResumeParser│    Regex extraction
│             │    Confidence scoring
└──────┬──────┘
       │  Candidate
       ▼
┌─────────────┐    Skill taxonomy matching
│MatchingEngine    Experience tier scoring
│             │    Education level comparison
└──────┬──────┘
       │  MatchResult
       ▼
┌─────────────┐    Plain text report
│ReportGenerator    HTML report
│             │    Score visualisation
└──────┬──────┘
       │
       ▼
┌─────────────┐    JSON persistence
│ FileManager │    Batch loading
│             │    Analytics export
└─────────────┘
```

---

## 📄 License

Copyright (c) 2026 Nithin Bharadwaj

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software.

---

## 👤 Author
Nithin Bharadwaj

Capstone Project: Intelligent Resume Analyzer  
Demonstrates resume parsing, skill matching, and candidate recommendation using Python.
