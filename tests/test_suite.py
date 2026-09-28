"""
tests/test_suite.py — Comprehensive unit tests for the Hiring Assistant.
Run with:  python -m pytest tests/ -v
       or: python tests/test_suite.py
"""

import sys
import os
import json
import logging
import unittest
import tempfile
from pathlib import Path

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hiring_assistant.models import (
    Candidate, JobRequirement, EducationLevel,
    RecommendationTier, WorkExperience, ScoreBreakdown, MatchResult,
)
from hiring_assistant.parser import ResumeParser
from hiring_assistant.matcher import MatchingEngine, MatchWeights
from hiring_assistant.reporter import ReportGenerator
from hiring_assistant.analytics import AnalyticsEngine
from hiring_assistant.file_manager import FileManager


# ─────────────────────────────────────────────
#  FIXTURES
# ─────────────────────────────────────────────

SAMPLE_RESUME = """
Alice Johnson
alice.johnson@email.com | +1-555-0101
linkedin.com/in/alicejohnson | github.com/alicejohnson
New York, NY

Summary
Experienced backend engineer with 5 years building scalable systems in Python.

Skills
Python, Django, Flask, REST API, PostgreSQL, Redis, Docker, AWS, Git, Linux, CI/CD, Agile

Experience
Senior Software Engineer – TechCorp (2020 – Present)
  Led a team of 4 building microservices for 2M users.

Software Developer – StartupXYZ (2018 – 2020)
  Developed REST APIs with Flask and PostgreSQL.

Education
Bachelor of Science in Computer Science – State University, 2018

Certifications
AWS Certified Solutions Architect
"""

MINIMAL_RESUME = "John Doe\njohn@example.com\nPython developer"

EMPTY_RESUME = "   "

JOB_BACKEND = JobRequirement(
    title="Senior Backend Engineer",
    required_skills=["python", "rest api", "postgresql", "docker", "git"],
    preferred_skills=["aws", "redis", "ci/cd", "linux"],
    min_experience=4,
    education_required=EducationLevel.BACHELOR,
)

JOB_JUNIOR = JobRequirement(
    title="Junior Developer",
    required_skills=["python", "git"],
    preferred_skills=["sql"],
    min_experience=0,
    education_required=EducationLevel.DIPLOMA,
)


# ─────────────────────────────────────────────
#  PARSER TESTS
# ─────────────────────────────────────────────

class TestResumeParser(unittest.TestCase):

    def setUp(self):
        self.parser = ResumeParser()

    def test_parse_name(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertEqual(c.name, "Alice Johnson")

    def test_parse_email(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertEqual(c.email, "alice.johnson@email.com")

    def test_parse_phone(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertIn("555", c.phone)

    def test_parse_linkedin(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertIn("linkedin.com/in/alicejohnson", c.linkedin)

    def test_parse_github(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertIn("github.com/alicejohnson", c.github)

    def test_parse_skills_detected(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertIn("python", c.skills)
        self.assertIn("docker", c.skills)
        self.assertIn("aws", c.skills)

    def test_skills_deduplicated(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertEqual(len(c.skills), len(set(c.skills)))

    def test_parse_education(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertEqual(c.education, EducationLevel.BACHELOR)

    def test_parse_experience_nonzero(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertGreater(c.experience_years, 0)

    def test_parse_certifications(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertTrue(any("AWS" in cert for cert in c.certifications))

    def test_parse_confidence_high_for_full_resume(self):
        c = self.parser.parse(SAMPLE_RESUME)
        self.assertGreaterEqual(c.parse_confidence, 0.7)

    def test_parse_confidence_low_for_minimal_resume(self):
        c = self.parser.parse(MINIMAL_RESUME)
        self.assertLessEqual(c.parse_confidence, 0.6)

    def test_empty_resume_raises(self):
        with self.assertRaises(ValueError):
            self.parser.parse(EMPTY_RESUME)

    def test_too_short_raises(self):
        with self.assertRaises(ValueError):
            self.parser.parse("hi")

    def test_custom_skills_detected(self):
        parser = ResumeParser(custom_skills=["zigbee", "lora"])
        c = parser.parse("Jane Doe\njane@test.com\nExpert in zigbee and lora protocols")
        self.assertIn("zigbee", c.skills)
        self.assertIn("lora", c.skills)

    def test_skills_are_lowercase(self):
        c = self.parser.parse(SAMPLE_RESUME)
        for skill in c.skills:
            self.assertEqual(skill, skill.lower())


# ─────────────────────────────────────────────
#  MODEL TESTS
# ─────────────────────────────────────────────

class TestModels(unittest.TestCase):

    def test_education_level_ordering(self):
        self.assertGreater(EducationLevel.PHD.value, EducationLevel.MASTER.value)
        self.assertGreater(EducationLevel.MASTER.value, EducationLevel.BACHELOR.value)

    def test_education_from_string(self):
        self.assertEqual(EducationLevel.from_string("Bachelor of Science"), EducationLevel.BACHELOR)
        self.assertEqual(EducationLevel.from_string("PhD in CS"), EducationLevel.PHD)
        self.assertEqual(EducationLevel.from_string("M.Tech"), EducationLevel.MASTER)
        self.assertEqual(EducationLevel.from_string("gibberish"), EducationLevel.UNKNOWN)

    def test_recommendation_tier_thresholds(self):
        self.assertEqual(RecommendationTier.from_score(85), RecommendationTier.STRONG)
        self.assertEqual(RecommendationTier.from_score(70), RecommendationTier.GOOD)
        self.assertEqual(RecommendationTier.from_score(55), RecommendationTier.PARTIAL)
        self.assertEqual(RecommendationTier.from_score(38), RecommendationTier.WEAK)
        self.assertEqual(RecommendationTier.from_score(20), RecommendationTier.POOR)

    def test_work_experience_duration(self):
        w = WorkExperience(start_year=2018, end_year=2023)
        self.assertEqual(w.duration_years, 5.0)

    def test_work_experience_present(self):
        import datetime
        w = WorkExperience(start_year=2020, end_year=None)
        expected = datetime.datetime.now().year - 2020
        self.assertAlmostEqual(w.duration_years, expected, delta=1)

    def test_candidate_serialization_roundtrip(self):
        c = Candidate(
            name="Test User",
            email="test@test.com",
            skills=["python", "docker"],
            experience_years=3.0,
            education=EducationLevel.BACHELOR,
        )
        d = c.to_dict()
        c2 = Candidate.from_dict(d)
        self.assertEqual(c2.name, c.name)
        self.assertEqual(c2.email, c.email)
        self.assertEqual(c2.education, c.education)

    def test_candidate_skills_deduplication(self):
        c = Candidate(skills=["Python", "python", "PYTHON"])
        self.assertEqual(c.skills, ["python"])

    def test_job_requirement_skills_lowercase(self):
        job = JobRequirement(
            title="Dev",
            required_skills=["Python", "AWS"],
            preferred_skills=["Docker"],
        )
        self.assertIn("python", job.required_skills)
        self.assertIn("aws", job.required_skills)


# ─────────────────────────────────────────────
#  MATCHER TESTS
# ─────────────────────────────────────────────

class TestMatchingEngine(unittest.TestCase):

    def setUp(self):
        self.engine = MatchingEngine()
        self.parser = ResumeParser()

    def _candidate_with_skills(self, skills, exp=5, edu=EducationLevel.BACHELOR):
        return Candidate(name="Test", skills=skills, experience_years=exp, education=edu)

    def test_perfect_match_score_high(self):
        c = self._candidate_with_skills(
            ["python", "rest api", "postgresql", "docker", "git", "aws", "redis"]
        )
        r = self.engine.match(c, JOB_BACKEND)
        self.assertGreaterEqual(r.overall_score, 85)

    def test_no_skills_match_score_low(self):
        c = self._candidate_with_skills(["java", "spring"], exp=1, edu=EducationLevel.HIGH_SCHOOL)
        r = self.engine.match(c, JOB_BACKEND)
        self.assertLessEqual(r.overall_score, 50)

    def test_score_in_range(self):
        c = self._candidate_with_skills(["python", "git"])
        r = self.engine.match(c, JOB_BACKEND)
        self.assertGreaterEqual(r.overall_score, 0)
        self.assertLessEqual(r.overall_score, 100)

    def test_missing_skills_populated(self):
        c = self._candidate_with_skills(["python"])
        r = self.engine.match(c, JOB_BACKEND)
        self.assertIn("rest api", r.missing_required_skills)
        self.assertIn("docker", r.missing_required_skills)

    def test_matched_skills_populated(self):
        c = self._candidate_with_skills(["python", "docker", "git"])
        r = self.engine.match(c, JOB_BACKEND)
        self.assertIn("python", r.matched_required_skills)

    def test_experience_overqualified_slight_penalty(self):
        job = JobRequirement(
            title="Junior", required_skills=["python"], min_experience=1, max_experience=2
        )
        c = self._candidate_with_skills(["python"], exp=10)
        r = self.engine.match(c, job)
        self.assertLessEqual(r.breakdown.experience_total, 80)

    def test_junior_job_no_experience_required(self):
        c = self._candidate_with_skills(["python", "git"], exp=0)
        r = self.engine.match(c, JOB_JUNIOR)
        self.assertEqual(r.breakdown.experience_total, 100.0)

    def test_education_gap_penalized(self):
        c = self._candidate_with_skills(["python", "docker", "git"], edu=EducationLevel.HIGH_SCHOOL)
        r = self.engine.match(c, JOB_BACKEND)
        self.assertLess(r.breakdown.education_total, 60)

    def test_recommendation_tier_assigned(self):
        c = self._candidate_with_skills(["python", "docker", "git", "rest api", "postgresql"])
        r = self.engine.match(c, JOB_BACKEND)
        self.assertIsInstance(r.recommendation, RecommendationTier)

    def test_strengths_generated(self):
        c = self._candidate_with_skills(
            ["python", "rest api", "postgresql", "docker", "git"], exp=8
        )
        r = self.engine.match(c, JOB_BACKEND)
        self.assertGreater(len(r.strengths), 0)

    def test_gaps_generated_for_weak_candidate(self):
        c = self._candidate_with_skills(["java"], exp=1, edu=EducationLevel.HIGH_SCHOOL)
        r = self.engine.match(c, JOB_BACKEND)
        self.assertGreater(len(r.gaps), 0)

    def test_custom_weights(self):
        weights = MatchWeights(skills=0.40, experience=0.40, education=0.20)
        engine = MatchingEngine(weights=weights)
        c = self._candidate_with_skills(["python", "docker", "git"])
        r = engine.match(c, JOB_BACKEND)
        self.assertIsNotNone(r.overall_score)

    def test_weights_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            MatchWeights(skills=0.5, experience=0.4, education=0.4)

    def test_batch_match_sorted(self):
        candidates = [
            self._candidate_with_skills(["python", "git"], exp=2),
            self._candidate_with_skills(
                ["python", "docker", "git", "rest api", "postgresql"], exp=5
            ),
            self._candidate_with_skills(["java"], exp=1),
        ]
        results = self.engine.batch_match(candidates, JOB_BACKEND)
        scores = [r.overall_score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))


# ─────────────────────────────────────────────
#  REPORTER TESTS
# ─────────────────────────────────────────────

class TestReportGenerator(unittest.TestCase):

    def setUp(self):
        self.reporter = ReportGenerator()
        parser = ResumeParser()
        self.candidate = parser.parse(SAMPLE_RESUME)
        engine = MatchingEngine()
        self.result = engine.match(self.candidate, JOB_BACKEND)

    def test_text_report_contains_name(self):
        report = self.reporter.candidate_report_text(self.candidate, [self.result])
        self.assertIn("Alice Johnson", report)

    def test_text_report_contains_score(self):
        report = self.reporter.candidate_report_text(self.candidate, [self.result])
        self.assertIn(str(int(self.result.overall_score)), report)

    def test_text_report_contains_recommendation(self):
        report = self.reporter.candidate_report_text(self.candidate, [self.result])
        self.assertIn("RECOMMENDATION", report)

    def test_html_report_is_valid_html(self):
        html = self.reporter.candidate_report_html(self.candidate, [self.result])
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("</html>", html)

    def test_html_report_contains_name(self):
        html = self.reporter.candidate_report_html(self.candidate, [self.result])
        self.assertIn("Alice Johnson", html)

    def test_html_report_contains_skills(self):
        html = self.reporter.candidate_report_html(self.candidate, [self.result])
        self.assertIn("python", html)


# ─────────────────────────────────────────────
#  ANALYTICS TESTS
# ─────────────────────────────────────────────

class TestAnalyticsEngine(unittest.TestCase):

    def setUp(self):
        parser = ResumeParser()
        engine = MatchingEngine()
        resumes = [
            SAMPLE_RESUME,
            "Bob Smith\nbob@test.com\nPython, Git developer\n3 years experience",
            "Carol Lee\ncarol@test.com\nJava developer\nBachelor's degree",
        ]
        self.results = []
        for r in resumes:
            try:
                c = parser.parse(r)
                self.results.append(engine.match(c, JOB_BACKEND))
            except ValueError:
                pass
        self.analytics = AnalyticsEngine()

    def test_analytics_total_count(self):
        report = self.analytics.analyze(self.results, JOB_BACKEND.title)
        self.assertEqual(report.total_candidates, len(self.results))

    def test_analytics_avg_score_range(self):
        report = self.analytics.analyze(self.results, JOB_BACKEND.title)
        self.assertGreaterEqual(report.avg_score, 0)
        self.assertLessEqual(report.avg_score, 100)

    def test_analytics_top_candidate_is_string(self):
        report = self.analytics.analyze(self.results, JOB_BACKEND.title)
        self.assertIsInstance(report.top_candidate, str)

    def test_analytics_empty_raises(self):
        with self.assertRaises(ValueError):
            self.analytics.analyze([], "Test Job")


# ─────────────────────────────────────────────
#  FILE MANAGER TESTS
# ─────────────────────────────────────────────

class TestFileManager(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fm = FileManager(base_dir=self.tmp)
        self.candidate = Candidate(
            name="Test User",
            email="test@test.com",
            skills=["python", "docker"],
            experience_years=3.0,
            education=EducationLevel.BACHELOR,
        )

    def test_save_and_load_candidate(self):
        self.fm.save_candidate(self.candidate, "test_profile.json")
        loaded = self.fm.load_candidate(Path(self.tmp) / "test_profile.json")
        self.assertEqual(loaded.name, self.candidate.name)
        self.assertEqual(loaded.email, self.candidate.email)

    def test_save_text_report(self):
        path = self.fm.save_text_report("Test report content", "test.txt")
        self.assertTrue(path.exists())
        self.assertIn("Test report content", path.read_text())

    def test_save_html_report(self):
        path = self.fm.save_html_report("<html><body>Test</body></html>", "test.html")
        self.assertTrue(path.exists())

    def test_load_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.fm.load_candidate("/nonexistent/path/file.json")

    def test_load_all_resumes_from_dir(self):
        d = Path(self.tmp) / "resumes"
        d.mkdir()
        (d / "r1.txt").write_text(SAMPLE_RESUME)
        (d / "r2.txt").write_text(MINIMAL_RESUME)
        texts = self.fm.load_all_resumes(d)
        self.assertEqual(len(texts), 2)

    def test_load_all_resumes_empty_dir(self):
        d = Path(self.tmp) / "empty"
        d.mkdir()
        self.assertEqual(self.fm.load_all_resumes(d), [])


# ─────────────────────────────────────────────
#  INTEGRATION TEST
# ─────────────────────────────────────────────

class TestIntegration(unittest.TestCase):

    def test_full_pipeline(self):
        """End-to-end: parse → match → report → save → load."""
        from hiring_assistant.assistant import HiringAssistant
        with tempfile.TemporaryDirectory() as tmp:
            assistant = HiringAssistant(output_dir=tmp, log_level=logging.ERROR)
            candidate, results = assistant.process_resume(
                SAMPLE_RESUME, [JOB_BACKEND, JOB_JUNIOR], save=True
            )
            # Check outputs
            self.assertEqual(candidate.name, "Alice Johnson")
            self.assertEqual(len(results), 2)
            # Both results should be valid scores in range
            for r in results:
                self.assertGreaterEqual(r.overall_score, 0)
                self.assertLessEqual(r.overall_score, 100)

            # Check files created
            files = list(Path(tmp).iterdir())
            extensions = {f.suffix for f in files}
            self.assertIn(".json", extensions)
            self.assertIn(".txt", extensions)
            self.assertIn(".html", extensions)

    def test_ranking_pipeline(self):
        """End-to-end: batch rank → analytics → save."""
        from hiring_assistant.assistant import HiringAssistant
        with tempfile.TemporaryDirectory() as tmp:
            assistant = HiringAssistant(output_dir=tmp, log_level=logging.ERROR)
            resumes = [SAMPLE_RESUME, MINIMAL_RESUME]
            pairs = assistant.rank_candidates(resumes, JOB_BACKEND, save=True)
            self.assertGreaterEqual(len(pairs), 1)
            scores = [r.overall_score for _, r in pairs]
            self.assertEqual(scores, sorted(scores, reverse=True))


# ─────────────────────────────────────────────
#  RUNNER
# ─────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    test_classes = [
        TestResumeParser,
        TestModels,
        TestMatchingEngine,
        TestReportGenerator,
        TestAnalyticsEngine,
        TestFileManager,
        TestIntegration,
    ]
    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
