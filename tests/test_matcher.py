"""Tests for scoring, recommendations and validation."""

import pytest

from matcher import (
    WEIGHTS,
    get_recommendation,
    score_candidate,
    score_education,
    score_experience,
)
from models import Candidate, Job
from utils import ValidationError


def test_weights_total_100():
    assert sum(WEIGHTS.values()) == 100


def test_perfect_match_scores_100(backend_job):
    candidate = Candidate(
        skills=[
            "python",
            "django",
            "sql",
            "rest api",
            "git",
            "aws",
            "docker",
            "postgresql",
            "ci/cd",
        ],
        experience=4,
        education=["B.Tech in CS"],
    )
    result = score_candidate(candidate, backend_job)
    assert result.score == 100
    assert result.recommendation == "Strongly Recommend"
    assert result.missing_required == []


def test_known_score_breakdown(strong_candidate, backend_job):
    result = score_candidate(strong_candidate, backend_job)
    # required 5/5 = 50, preferred 2/4 = 7.5, experience 25, education 10
    assert result.breakdown["required_skills"]["points"] == 50
    assert result.breakdown["preferred_skills"]["points"] == 7.5
    assert result.breakdown["experience"]["points"] == 25
    assert result.breakdown["education"]["points"] == 10
    assert result.score == 92.5
    assert result.matched_preferred == ["aws", "docker"]
    assert result.missing_preferred == ["postgresql", "ci/cd"]


def test_missing_required_skills_reported(backend_job):
    candidate = Candidate(skills=["python", "git"], experience=3, education=["B.E."])
    result = score_candidate(candidate, backend_job)
    assert result.matched_required == ["python", "git"]
    assert result.missing_required == ["django", "sql", "rest api"]
    assert result.breakdown["required_skills"]["points"] == 20
    assert any("Missing required skills" in text for text in result.improvements)


def test_skill_names_are_normalized_before_comparison():
    job = Job(title="Dev", required_skills=["JS", "Postgres", "K8s"])
    candidate = Candidate(skills=["javascript", "postgresql", "kubernetes"])
    assert score_candidate(candidate, job).score == 100


def test_soft_skills_count_toward_matching():
    job = Job(title="Lead", required_skills=["leadership", "python"])
    candidate = Candidate(skills=["python"], soft_skills=["leadership"])
    assert score_candidate(candidate, job).score == 100


def test_no_double_counting_of_duplicate_or_overlapping_skills():
    job = Job(
        title="Dev",
        required_skills=["Python", "python", "PYTHON", "sql"],
        preferred_skills=["python", "docker"],
    )
    candidate = Candidate(skills=["python"])
    result = score_candidate(candidate, job)
    assert result.matched_required == ["python"]
    assert result.missing_required == ["sql"]
    assert result.matched_preferred == []
    assert result.missing_preferred == ["docker"]
    assert result.breakdown["required_skills"]["coverage"] == 0.5


@pytest.mark.parametrize(
    "years, minimum, expected",
    [(5, 3, 1.0), (3, 3, 1.0), (1.5, 3, 0.5), (0, 3, 0.0), (None, 3, 0.0), (4, 0, 0.0)],
)
def test_experience_ratio(years, minimum, expected):
    assert score_experience(years, minimum)[0] == expected


def test_experience_points_proportional():
    job = Job(title="Dev", min_experience=4)
    result = score_candidate(Candidate(experience=1), job)
    assert result.breakdown["experience"]["points"] == 25
    assert result.score == 25.0  # only component, scaled to 100 -> 1/4 of 100


@pytest.mark.parametrize(
    "candidate_edu, required, expected",
    [
        (["B.Tech CS"], "Bachelor's", 1.0),
        (["M.Sc Statistics"], "Bachelor's", 1.0),
        (["Diploma in Engineering"], "Bachelor's", 0.5),
        (["Bachelor of Arts"], "Master's", pytest.approx(2 / 3)),
        ([], "Bachelor's", 0.0),
        (["PhD Physics"], "PhD", 1.0),
        (["Bachelor of Arts"], None, 0.0),
    ],
)
def test_education_scoring(candidate_edu, required, expected):
    assert score_education(candidate_edu, required)[0] == expected


def test_scrum_master_is_not_a_master_degree():
    assert score_education(["Certified Scrum Master"], "Master's")[1] == 0


@pytest.mark.parametrize(
    "score, label",
    [
        (0, "Not Recommended"),
        (39.99, "Not Recommended"),
        (40, "Consider"),
        (59.99, "Consider"),
        (60, "Recommend"),
        (79.99, "Recommend"),
        (80, "Strongly Recommend"),
        (100, "Strongly Recommend"),
    ],
)
def test_recommendation_thresholds(score, label):
    assert get_recommendation(score) == label


@pytest.mark.parametrize("bad", [-1, 100.01, float("nan"), "80", None, True])
def test_recommendation_rejects_invalid_scores(bad):
    with pytest.raises(ValidationError):
        get_recommendation(bad)


def test_score_always_between_0_and_100(backend_job):
    candidates = [
        Candidate(),
        Candidate(skills=["python"], experience=60),
        Candidate(skills=["x"] * 5, experience=0, education=["PhD"]),
        Candidate(skills=["python", "django", "sql", "rest api", "git"], experience=50),
    ]
    for candidate in candidates:
        result = score_candidate(candidate, backend_job)
        assert 0 <= result.score <= 100
        assert all(
            0 <= part["points"] <= part["max_points"] + 1e-9
            for part in result.breakdown.values()
        )


def test_empty_candidate_scores_zero_without_crashing(backend_job):
    result = score_candidate(Candidate(), backend_job)
    assert result.score == 0
    assert result.recommendation == "Not Recommended"
    assert any("not found" in text for text in result.improvements)


def test_deterministic_results(strong_candidate, backend_job):
    first = score_candidate(strong_candidate, backend_job)
    for _ in range(5):
        assert score_candidate(strong_candidate, backend_job) == first


def test_empty_component_groups_do_not_divide_by_zero():
    job = Job(title="Dev", required_skills=["python"])  # nothing else specified
    result = score_candidate(Candidate(skills=["python"]), job)
    assert result.score == 100
    assert result.breakdown["preferred_skills"]["applicable"] is False
    assert result.breakdown["experience"]["max_points"] == 0
    assert "skipped" in result.explanation.lower()


def test_job_with_only_preferred_skills_still_scores():
    job = Job(title="Dev", preferred_skills=["python", "sql"])
    assert score_candidate(Candidate(skills=["python"]), job).score == 50


def test_completely_empty_job_requirements_rejected():
    with pytest.raises(ValidationError, match="no requirements"):
        score_candidate(Candidate(skills=["python"]), Job(title="Dev"))
    with pytest.raises(ValidationError):
        score_candidate(Candidate(), Job(title="Dev", required_skills=["  ", ""]))


def test_missing_job_title_rejected():
    with pytest.raises(ValidationError, match="title"):
        score_candidate(Candidate(), Job(title="  ", required_skills=["python"]))


@pytest.mark.parametrize("years", [-1, 99, float("nan"), "3", True])
def test_invalid_experience_values_rejected(years):
    with pytest.raises(ValidationError):
        score_candidate(
            Candidate(experience=years), Job(title="D", required_skills=["a"])
        )
    with pytest.raises(ValidationError):
        score_candidate(
            Candidate(), Job(title="D", required_skills=["a"], min_experience=years)
        )


def test_unknown_education_requirement_rejected():
    job = Job(title="D", required_skills=["a"], required_education="Wizard school")
    with pytest.raises(ValidationError, match="education"):
        score_candidate(Candidate(), job)


def test_invalid_skill_list_type_rejected():
    with pytest.raises(ValidationError):
        score_candidate(
            Candidate(skills="python"), Job(title="D", required_skills=["a"])
        )


def test_explanation_mentions_score_and_band(strong_candidate, backend_job):
    result = score_candidate(strong_candidate, backend_job)
    assert "92.5/100" in result.explanation
    assert "Strongly Recommend" in result.explanation
    assert "not a final hiring decision" in result.explanation


def test_five_realistic_candidate_job_pairs():
    from conftest import SAMPLE_JOBS, SAMPLE_RESUMES
    from datetime import date
    from file_manager import load_job
    from resume_parser import parse_resume_file

    expectations = {
        ("priya_sharma.txt", "python_backend_developer.json"): "Strongly Recommend",
        ("anita_desai.txt", "data_analyst.json"): "Strongly Recommend",
        ("priya_sharma.txt", "data_analyst.json"): "Recommend",
        ("anita_desai.txt", "python_backend_developer.json"): "Consider",
        ("rahul_verma.txt", "python_backend_developer.json"): "Not Recommended",
    }
    for (resume, job_file), label in expectations.items():
        candidate = parse_resume_file(SAMPLE_RESUMES / resume, today=date(2026, 10, 4))
        result = score_candidate(candidate, load_job(SAMPLE_JOBS / job_file))
        assert result.recommendation == label, (resume, result.score)
        assert 0 <= result.score <= 100
