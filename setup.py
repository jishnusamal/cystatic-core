"""Setuptools metadata for optional packaging."""

from setuptools import find_packages, setup

setup(
    name="cystatic-core",
    version="0.1.0",
    description="Blast radius and impact analysis for code changes",
    packages=find_packages(exclude=("tests", "tests.*", "actions")),
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.110.0",
        "uvicorn[standard]>=0.27.0",
        "pydantic>=2.0.0",
        "httpx>=0.26.0",
    ],
    extras_require={
        "dev": ["pytest>=8.0.0"],
    },
)
