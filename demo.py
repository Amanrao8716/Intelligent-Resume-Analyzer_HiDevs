"""
demo.py — Demonstrates all features of the Smart Hiring Assistant v2.
Run: python demo.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import logging
from hiring_assistant import HiringAssistant
from hiring_assistant.models import JobRequirement, EducationLevel
from hiring_assistant.matcher import MatchWeights

# ─────────────────────────────────────────────
#  JOB DEFINITIONS
# ─────────────────────────────────────────────

JOBS = {
    "backend": JobRequirement(
        title="Senior Backend Engineer",
        required_skills=["python", "rest api", "postgresql", "docker", "git"],
        preferred_skills=["aws", "redis", "ci/cd", "linux"],
        min_experience=4,
        education_required=EducationLevel.BACHELOR,
    ),
    "fullstack": JobRequirement(
        title="Full Stack Developer",
        required_skills=["python", "react", "sql", "git"],
        preferred_skills=["typescript", "docker", "aws", "graphql"],
        min_experience=3,
        education_required=EducationLevel.BACHELOR,
    ),
}

SAMPLE_RESUMES = {
    "alice": open("data/sample_resumes/alice.txt").read(),
    "bob":   open("data/sample_resumes/bob.txt").read(),
    "carol": open("data/sample_resumes/carol.txt").read(),
}


def demo_1_single_analysis():
    """Analyze Alice against two job openings."""
    print("\n" + "━"*64)
    print("  DEMO 1 — Single Candidate, Multiple Jobs")
    print("━"*64)
    assistant = HiringAssistant(output_dir="output/demo1", log_level=logging.WARNING)
    assistant.process_resume(
        resume_text=SAMPLE_RESUMES["alice"],
        jobs=list(JOBS.values()),
        save=True,
        generate_html=True,
    )


def demo_2_batch_ranking():
    """Rank all three candidates for the Backend role."""
    print("\n" + "━"*64)
    print("  DEMO 2 — Batch Ranking with Analytics")
    print("━"*64)
    assistant = HiringAssistant(output_dir="output/demo2", log_level=logging.WARNING)
    assistant.rank_candidates(
        resumes=list(SAMPLE_RESUMES.values()),
        job=JOBS["backend"],
        save=True,
    )


def demo_3_custom_weights():
    """Use custom scoring weights (skills-heavy for a tech role)."""
    print("\n" + "━"*64)
    print("  DEMO 3 — Custom Scoring Weights")
    print("━"*64)
    weights = MatchWeights(skills=0.70, experience=0.20, education=0.10)
    assistant = HiringAssistant(
        output_dir="output/demo3",
        weights=weights,
        log_level=logging.WARNING
    )
    assistant.process_resume(
        SAMPLE_RESUMES["carol"], [JOBS["backend"]], save=True
    )


def demo_4_from_directory():
    """Load all resumes from a directory and rank."""
    print("\n" + "━"*64)
    print("  DEMO 4 — Rank From Directory")
    print("━"*64)
    assistant = HiringAssistant(output_dir="output/demo4", log_level=logging.WARNING)
    assistant.rank_from_directory("data/sample_resumes", JOBS["fullstack"], save=True)


def demo_5_custom_skills():
    """Add domain-specific skills not in the default taxonomy."""
    print("\n" + "━"*64)
    print("  DEMO 5 — Custom Skill Taxonomy Extension")
    print("━"*64)
    custom_resume = """
    Jane Tech  |  jane@example.com
    Skills: Python, Solidity, Web3.py, Hardhat, IPFS, Docker, Git
    Experience: Blockchain Developer at CryptoStartup (2021 – Present)
    Education: Bachelor of Engineering, 2020
    """
    blockchain_job = JobRequirement(
        title="Blockchain Developer",
        required_skills=["python", "solidity", "web3.py", "git"],
        preferred_skills=["hardhat", "ipfs", "docker"],
        min_experience=2,
        education_required=EducationLevel.BACHELOR,
    )
    assistant = HiringAssistant(
        output_dir="output/demo5",
        custom_skills=["solidity", "web3.py", "hardhat", "ipfs"],
        log_level=logging.WARNING,
    )
    assistant.process_resume(custom_resume, [blockchain_job], save=True)


if __name__ == "__main__":
    demo_1_single_analysis()
    demo_2_batch_ranking()
    demo_3_custom_weights()
    demo_4_from_directory()
    demo_5_custom_skills()
    print("\n✅  All demos complete. Check output/ for JSON, TXT, and HTML reports.\n")
