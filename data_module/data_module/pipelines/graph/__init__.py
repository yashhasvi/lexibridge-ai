"""data_module.pipelines.graph"""
from .extractor import TripleExtractor
from .builder import GraphBuilder

__all__ = ["TripleExtractor", "GraphBuilder"]
