"""
hiring_assistant — Advanced Resume Intelligence System
"""
__version__ = "2.0.0"
__author__ = "Your Name"

from .models import Candidate, JobRequirement, MatchResult, AnalyticsReport
from .parser import ResumeParser
from .matcher import MatchingEngine
from .reporter import ReportGenerator
from .file_manager import FileManager
from .assistant import HiringAssistant
from .analytics import AnalyticsEngine

__all__ = [
    "Candidate", "JobRequirement", "MatchResult", "AnalyticsReport",
    "ResumeParser", "MatchingEngine", "ReportGenerator",
    "FileManager", "HiringAssistant", "AnalyticsEngine",
]
