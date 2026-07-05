"""Framework-specific parsers for Python language adapter."""

from language_adapters.python.frameworks.fastapi import FastAPIParser
from language_adapters.python.frameworks.flask import FlaskParser

__all__ = ["FastAPIParser", "FlaskParser"]