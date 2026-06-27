"""
Current NLP entrypoints for the frozen single-source baseline.

Only `NlpPipeline` should be treated as the public hot-path entry.
Legacy helper modules in `src/nlp/` are intentionally not re-exported here.
"""
from .nlp_pipeline import NlpPipeline

__all__ = ["NlpPipeline"]
