# 🧠 Intelligent Resume Analyzer

An AI-inspired resume screening tool built using Python that automates the initial candidate evaluation process. The system extracts relevant information from resumes, compares candidate skills and experience against job requirements, and generates a match score with hiring recommendations.

Designed as a practical HR Tech solution, this project demonstrates how resume parsing, skill matching, and structured reporting can simplify the recruitment process.

---

## ✨ Features

| Feature                      | Details                                                                           |
| ---------------------------- | --------------------------------------------------------------------------------- |
| **Resume Parsing**           | Extracts candidate name, email, skills, and years of experience from resume text. |
| **Skill Matching**           | Compares candidate skills with the required skills for a job role.                |
| **Experience Evaluation**    | Considers candidate experience while calculating the match score.                 |
| **Match Score**              | Generates a score between 0 and 100 based on candidate-job compatibility.         |
| **Hiring Recommendation**    | Provides a recommendation based on the candidate's overall score.                 |
| **Missing Skills Detection** | Identifies skills required for a role that are not found in the resume.           |
| **JSON Reports**             | Stores structured candidate information and analysis results in JSON format.      |
| **Error Handling**           | Handles missing or incomplete information during resume processing.               |
| **Modular Architecture**     | Separates parsing, matching, and report generation into independent modules.      |

---

## 📁 Project Structure

```text
Intelligent-Resume-Analyzer_HiDevs/
│
├── app.py                  # Main application entry point
├── resume_parser.py        # Extracts candidate details from resumes
├── matcher.py              # Calculates skill and experience match scores
├── report_generator.py    # Generates analysis reports
│
├── requirements.txt        # Project dependencies
├── README.md               # Project documentation
├── .gitignore              # Excludes unnecessary files
│
├── resume.json             # Generated candidate profile (if created)
└── analysis_report.json    # Generated analysis report (if created)
```

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/Amanrao8716/Intelligent-Resume-Analyzer_HiDevs.git
```

### 2. Navigate to the Project Directory

```bash
cd Intelligent-Resume-Analyzer_HiDevs
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Application

```bash
python app.py
```

Follow the prompts to provide resume information and the required skills for the target job role.

---

## ⚙️ How It Works

The system follows a simple resume-screening pipeline:

```text
Resume Input
     │
     ▼
Resume Parser
     │
     ├── Extract Candidate Name
     ├── Extract Email
     ├── Identify Skills
     └── Detect Experience
     │
     ▼
Matching Engine
     │
     ├── Compare Required Skills
     ├── Evaluate Experience
     └── Calculate Match Score
     │
     ▼
Recommendation Engine
     │
     ├── Generate Hiring Recommendation
     └── Identify Missing Skills
     │
     ▼
Report Generator
     │
     └── Export Results in JSON Format
```

---

## 📊 Matching and Scoring

The analyzer evaluates candidates based on their compatibility with the job requirements.

**The analysis includes:**

* Skill coverage: Measures how many required skills are present in the candidate's resume.
* Experience evaluation: Considers the candidate's relevant years of experience.
* Match score: Produces an overall score from 0 to 100.
* Missing skills: Highlights the skills that may need further evaluation.
* Recommendation: Classifies candidates based on their overall match score.

The score is intended to support initial screening and should not replace human evaluation during hiring.

---

## 📤 Output

The application generates structured JSON data containing candidate information and analysis results.

| Output                 | Description                                                          |
| ---------------------- | -------------------------------------------------------------------- |
| `resume.json`          | Stores extracted candidate profile information.                      |
| `analysis_report.json` | Contains the match score, missing skills, and hiring recommendation. |

These outputs can be used for further analysis, integration with other applications, or record keeping.

---

## 🛠️ Technologies Used

* **Python** — Core programming language
* **Regular Expressions (Regex)** — Pattern-based information extraction
* **JSON** — Structured data storage
* **Object-Oriented Programming** — Modular and maintainable code
* **Git & GitHub** — Version control and project collaboration

---

## 🎯 Use Cases

* Initial resume screening for recruiters
* Candidate skill-gap identification
* Comparing candidate profiles against job requirements
* Automating repetitive resume evaluation tasks
* Demonstrating practical Python applications in HR Tech

---

## 🎥 Project Demo

Watch the project demonstration:

[▶️ Intelligent Resume Analyzer — YouTube Demo](https://youtu.be/LsFSOYBerVY?si=I1oilf_5AFvBZF_K)

---

## 👨‍💻 Author

**Aman Rao**

* GitHub: [@Amanrao8716](https://github.com/Amanrao8716)
* Project Repository: [Intelligent Resume Analyzer](https://github.com/Amanrao8716/Intelligent-Resume-Analyzer_HiDevs)

---

## 📄 License

This project was developed as part of the HiDevs HR Tech project initiative for learning and demonstrating resume screening and candidate matching concepts.
