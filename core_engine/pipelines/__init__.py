"""
Pipelines — modular pipeline implementations for PR analysis.

Each pipeline has a single responsibility:
  - ChangeUnderstandingPipeline: Analyze the change itself
  - EvidencePipeline: Generate semantic evidence
  - InferencePipeline: Generate hypotheses and scenarios
  - EvidenceNormalizationPipeline: Transform inference into reviewer-ready facts
  - ReviewPipeline: LLM review and verdict aggregation
"""
