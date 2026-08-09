"""Tests for ContextCompressor wrapper."""

import pytest
from engine.llm_context import ContextCompressor


def test_context_compressor_interface():
    compressor = ContextCompressor()
    text = "This is a test prompt context string that has multiple words to be compressed."
    compressed = compressor.compress(text, target_rate=0.5)
    assert isinstance(compressed, str)


def test_context_compressor_dict():
    compressor = ContextCompressor()
    serialized = {
        "st": ["short", "this is a very long string table entry that can potentially be compressed by llmlingua"],
        "disc": [
            [1, ["discovery fact entry that contains detailed explanation of code change"]]
        ]
    }
    res = compressor.compress_serialized_dict(serialized, target_rate=0.5)
    assert "st" in res
    assert "disc" in res
