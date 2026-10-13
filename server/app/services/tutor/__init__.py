"""Tutor services package."""
from .error_analyzer import get_error_analyzer, ErrorAnalyzer
from .graph_enhancer import get_graph_enhancer, GraphEnhancer

__all__ = [
    "get_error_analyzer", "ErrorAnalyzer",
    "get_graph_enhancer", "GraphEnhancer"
]
"""Tutor services package."""
from .error_analyzer import get_error_analyzer, ErrorAnalyzer

__all__ = ["get_error_analyzer", "ErrorAnalyzer"]
"""Track D — Personalized Tutoring & Adaptive Learning subsystem.

A source-grounded AI study companion built on top of the existing RAG stack.
Core design:
  - Multi-modal ingestion (video/transcript, textbook, slides) -> content Units
    that preserve their origin (page / slide number / video timestamp).
  - Topic graph (topics, concepts, prerequisites) tagged onto every Unit.
  - Grounded tutor chat: retrieves via existing RAG service, refuses or flags
    queries the material does not cover, and answers with cited excerpts.
  - Bayesian Knowledge Tracing (BKT) learner model updating after each quiz
    and conversation.
  - Adaptive assessment generator with answer verification, cited feedback and
    post-assessment reports.
  - Evaluation runners: RAG metrics (reusing the existing RAG evaluator) plus
    simulated student profiles measuring mastery gains and question repetition.

Everything except optional LLM-augmented generation runs offline so the whole
loop can be demoed without API keys.
"""

from app.services.tutor.store import TutorStore, get_tutor_store
from app.services.tutor.learner import LearnerModel
from app.services.tutor.knowledge import KnowledgeBaseIngestor, get_kb_ingestor
from app.services.tutor.grounding import GroundedTutor, get_grounded_tutor
from app.services.tutor.assessment import AssessmentGenerator, get_assessment_generator
from app.services.tutor.evaluation import EvaluationRunner, get_evaluation_runner

__all__ = [
    "TutorStore", "get_tutor_store", "LearnerModel",
    "KnowledgeBaseIngestor", "get_kb_ingestor",
    "GroundedTutor", "get_grounded_tutor",
    "AssessmentGenerator", "get_assessment_generator",
    "EvaluationRunner", "get_evaluation_runner",
]
