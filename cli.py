#!/usr/bin/env python3
"""
cli.py — Command-line interface for the Smart Hiring Assistant.

Usage examples:
  # Analyze a single resume against a built-in job
  python cli.py analyze --resume data/sample_resumes/alice.txt --job backend

  # Rank all resumes in a folder against a job
  python cli.py rank --dir data/sample_resumes --job fullstack

  # Run test suite
  python cli.py test
"""

import argparse
import sys
import os
import logging

# Ensure package is importable when running from project root
sys.path.insert(0, os.path.dirname(__file__))

from hiring_assistant import HiringAssistant
from hiring_assistant.models import JobRequirement, EducationLevel
from hiring_assistant.matcher import MatchWeights


# ─────────────────────────────────────────────
#  BUILT-IN JOB PRESETS
# ─────────────────────────────────────────────

PRESET_JOBS = {
    "backend": JobRequirement(
        title="Senior Backend Engineer",
        required_skills=["python", "rest api", "postgresql", "docker", "git"],
        preferred_skills=["aws", "redis", "ci/cd", "linux", "microservices"],
        min_experience=4,
        education_required=EducationLevel.BACHELOR,
        description="Build scalable backend services.",
    ),
    "fullstack": JobRequirement(
        title="Full Stack Developer",
        required_skills=["python", "react", "sql", "git"],
        preferred_skills=["typescript", "docker", "aws", "graphql", "node.js"],
        min_experience=3,
        education_required=EducationLevel.BACHELOR,
    ),
    "junior": JobRequirement(
        title="Junior Python Developer",
        required_skills=["python", "git", "sql"],
        preferred_skills=["html", "css", "rest api", "flask"],
        min_experience=0,
        education_required=EducationLevel.DIPLOMA,
    ),
    "data": JobRequirement(
        title="Data Engineer",
        required_skills=["python", "sql", "pandas", "aws", "git"],
        preferred_skills=["spark", "airflow", "docker", "postgresql", "data analysis"],
        min_experience=2,
        education_required=EducationLevel.BACHELOR,
    ),
    "devops": JobRequirement(
        title="DevOps Engineer",
        required_skills=["docker", "kubernetes", "aws", "linux", "git"],
        preferred_skills=["terraform", "ansible", "ci/cd", "python", "bash"],
        min_experience=3,
        education_required=EducationLevel.BACHELOR,
    ),
    "ml": JobRequirement(
        title="ML Engineer",
        required_skills=["python", "machine learning", "tensorflow", "pandas", "git"],
        preferred_skills=["pytorch", "mlflow", "docker", "aws", "sql"],
        min_experience=2,
        education_required=EducationLevel.MASTER,
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hiring-assistant",
        description="🧠 Smart Hiring Assistant — Resume Intelligence System v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python cli.py analyze --resume alice.txt --job backend
  python cli.py rank --dir ./resumes --job fullstack --output results/
  python cli.py test
  python cli.py jobs
        """,
    )
    parser.add_argument(
        "--output", "-o", default="output",
        help="Output directory for saved files (default: output/)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose debug logging"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ── analyze ──
    analyze = sub.add_parser("analyze", help="Analyze a single resume")
    analyze.add_argument("--resume", "-r", required=True, help="Path to resume .txt file")
    analyze.add_argument(
        "--job", "-j", required=True,
        choices=list(PRESET_JOBS.keys()),
        help="Job preset to match against"
    )
    analyze.add_argument(
        "--all-jobs", action="store_true",
        help="Match against all preset jobs"
    )
    analyze.add_argument("--no-html", action="store_true", help="Skip HTML report")

    # ── rank ──
    rank = sub.add_parser("rank", help="Rank multiple resumes for a job")
    rank.add_argument(
        "--dir", "-d", required=True,
        help="Directory containing resume .txt files"
    )
    rank.add_argument(
        "--job", "-j", required=True,
        choices=list(PRESET_JOBS.keys()),
        help="Job preset to rank candidates for"
    )

    # ── test ──
    sub.add_parser("test", help="Run the unit test suite")

    # ── jobs ──
    sub.add_parser("jobs", help="List all available job presets")

    return parser


def cmd_analyze(args):
    log_level = logging.DEBUG if args.verbose else logging.INFO
    assistant = HiringAssistant(output_dir=args.output, log_level=log_level)

    jobs = list(PRESET_JOBS.values()) if args.all_jobs else [PRESET_JOBS[args.job]]
    assistant.process_resume_file(
        filepath=args.resume,
        jobs=jobs,
        save=True,
        generate_html=not args.no_html,
    )


def cmd_rank(args):
    log_level = logging.DEBUG if args.verbose else logging.INFO
    assistant = HiringAssistant(output_dir=args.output, log_level=log_level)
    assistant.rank_from_directory(
        resume_dir=args.dir,
        job=PRESET_JOBS[args.job],
        save=True,
    )


def cmd_test(_args):
    import unittest
    from tests.test_suite import (
        TestResumeParser, TestModels, TestMatchingEngine,
        TestReportGenerator, TestAnalyticsEngine, TestFileManager, TestIntegration
    )
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [TestResumeParser, TestModels, TestMatchingEngine,
                TestReportGenerator, TestAnalyticsEngine, TestFileManager, TestIntegration]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


def cmd_jobs(_args):
    print("\n  Available Job Presets\n  " + "─" * 40)
    for key, job in PRESET_JOBS.items():
        print(f"\n  [{key}]  {job.title}")
        print(f"    Required  : {', '.join(job.required_skills)}")
        print(f"    Preferred : {', '.join(job.preferred_skills)}")
        print(f"    Min Exp   : {job.min_experience}y   Education: {job.education_required.label()}")
    print()


def main():
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "analyze": cmd_analyze,
        "rank":    cmd_rank,
        "test":    cmd_test,
        "jobs":    cmd_jobs,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
