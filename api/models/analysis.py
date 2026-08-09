from __future__ import annotations

from tortoise import fields, models
from .core import TimestampedFields


class AnalysisRun(TimestampedFields, models.Model):
    analysis_run_id = fields.IntField(pk=True)
    pull_request = fields.ForeignKeyField(
        "models.PullRequest", related_name="analysis_runs", on_delete=fields.CASCADE
    )
    # Head SHA captured at run time for idempotency and traceability
    head_sha = fields.CharField(max_length=128, default="")
    analyzer_version = fields.CharField(max_length=64)
    reasoning_model_version = fields.CharField(max_length=128)
    execution_duration_ms = fields.IntField(null=True)
    # Lifecycle status: queued, cloning, graph_building, deterministic_analysis,
    # reasoning, comment_generation, posting, completed, failed, partially_failed
    status = fields.CharField(max_length=32, default="completed")
    triggered_by = fields.CharField(max_length=64, default="pull_request")
    webhook_action = fields.CharField(max_length=32, null=True)
    # Delivery ID from webhook — used for deduplication. Should be unique when present.
    delivery_id = fields.CharField(max_length=128, null=True, unique=True)
    # Failure and retry metadata
    failure_stage = fields.CharField(max_length=64, null=True)
    failure_trace = fields.TextField(null=True)
    retry_count = fields.IntField(default=0)
    partial_artifacts = fields.JSONField(default=list)
    risk_score = fields.FloatField(null=True)
    risk_category = fields.CharField(max_length=64, default="")
    verdict = fields.CharField(max_length=64, default="")
    # Canonical comment should live in AnalysisComment — this field stores a short
    # summary or reference to the canonical comment for quick searching.
    generated_comment_summary = fields.TextField(null=True)
    # Reference to the canonical comment (AnalysisComment) when posted.
    canonical_comment = fields.ForeignKeyField(
        "models.AnalysisComment",
        related_name="canonical_for_run",
        null=True,
        on_delete=fields.SET_NULL,
    )
    analysis_mode = fields.CharField(max_length=32, default="")
    analysis_snapshot = fields.JSONField(default=dict)
    internal_reasoning_artifacts = fields.JSONField(default=dict)
    # Schema / format versioning to support replayability across analyzer changes
    graph_schema_version = fields.CharField(max_length=64, null=True)
    finding_schema_version = fields.CharField(max_length=64, null=True)
    reasoning_prompt_version = fields.CharField(max_length=128, null=True)
    risk_taxonomy_version = fields.CharField(max_length=64, null=True)

    class Meta(models.Model.Meta):
        table = "analysis_runs"
        # Prevent duplicate runs for the same PR/head/trigger combination
        unique_together = (("pull_request", "head_sha", "triggered_by"),)


class DeterministicAnalyzerOutput(TimestampedFields, models.Model):
    output_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun",
        related_name="deterministic_outputs",
        on_delete=fields.CASCADE,
    )
    files = fields.JSONField(default=list)
    risk_patterns = fields.JSONField(default=list)
    entry_points_affected = fields.JSONField(default=list)
    system_impact = fields.JSONField(default=list)
    excluded_files = fields.JSONField(default=list)
    compressed_for_llm = fields.JSONField(default=dict)
    dependency_graph = fields.JSONField(default=dict)
    # Indexed metadata extracted from dependency_graph / execution paths for queryability
    node_count = fields.IntField(null=True)
    edge_count = fields.IntField(null=True)
    impacted_auth_nodes_count = fields.IntField(null=True)
    service_boundary_count = fields.IntField(null=True)
    changed_execution_path_count = fields.IntField(null=True)
    impacted_services = fields.JSONField(default=list)
    execution_paths = fields.JSONField(default=list)
    auth_boundary_changes = fields.JSONField(default=list)
    dataflow_changes = fields.JSONField(default=list)
    deleted_guards = fields.JSONField(default=list)
    changed_api_contracts = fields.JSONField(default=list)
    event_flow_modifications = fields.JSONField(default=list)
    inferred_risk_regions = fields.JSONField(default=list)

    class Meta(models.Model.Meta):
        table = "deterministic_analyzer_outputs"


class AnalysisJob(TimestampedFields, models.Model):
    """Queue/job entity separate from AnalysisRun for leasing, retries, and scheduling."""

    job_id = fields.IntField(pk=True)
    repo_full_name = fields.CharField(max_length=255)
    owner_login = fields.CharField(max_length=255, null=True)
    repo_name = fields.CharField(max_length=255, null=True)
    pr_number = fields.IntField()
    head_sha = fields.CharField(max_length=128, null=True)
    base_sha = fields.CharField(max_length=128, null=True)
    action = fields.CharField(max_length=64)
    installation_id = fields.BigIntField(null=True)
    payload_json = fields.JSONField(default=dict)
    result_summary = fields.JSONField(default=dict)
    error_stage = fields.CharField(max_length=64, null=True)
    error_trace = fields.TextField(null=True)
    pull_request = fields.ForeignKeyField(
        "models.PullRequest", related_name="jobs", null=True, on_delete=fields.SET_NULL
    )
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun",
        related_name="job_record",
        null=True,
        on_delete=fields.SET_NULL,
    )
    status = fields.CharField(max_length=32, default="queued")
    attempts = fields.IntField(default=0)
    max_attempts = fields.IntField(default=5)
    priority = fields.IntField(default=50)
    lease_owner = fields.CharField(max_length=255, null=True)
    lease_expires_at = fields.DatetimeField(null=True)
    next_retry_at = fields.DatetimeField(null=True)
    idempotency_key = fields.CharField(max_length=128, null=True, unique=True)
    delivery_id = fields.CharField(max_length=128, null=True)

    class Meta(models.Model.Meta):
        table = "analysis_jobs"


class RiskFinding(TimestampedFields, models.Model):
    finding_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun", related_name="risk_findings", on_delete=fields.CASCADE
    )
    category = fields.CharField(max_length=128)
    severity = fields.CharField(max_length=32)
    confidence_bucket = fields.CharField(max_length=32)
    confidence = fields.FloatField(null=True)
    evidence = fields.JSONField(default=dict)
    affected_components = fields.JSONField(default=list)
    inferred_blast_radius = fields.JSONField(default=list)
    code_locations = fields.JSONField(default=list)
    summary = fields.TextField(default="")

    class Meta(models.Model.Meta):
        table = "risk_findings"


class AnalysisArtifact(TimestampedFields, models.Model):
    artifact_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun", related_name="artifacts", on_delete=fields.CASCADE
    )
    artifact_type = fields.CharField(max_length=64)
    storage_uri = fields.CharField(max_length=512, null=True)
    checksum = fields.CharField(max_length=128, null=True)
    mime_type = fields.CharField(max_length=128, null=True)
    size_bytes = fields.BigIntField(null=True)
    payload_json = fields.JSONField(null=True)
    metadata = fields.JSONField(default=dict)

    class Meta(models.Model.Meta):
        table = "analysis_artifacts"


class AnalysisComment(TimestampedFields, models.Model):
    comment_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun", related_name="comments", on_delete=fields.CASCADE
    )
    body = fields.TextField()
    comment_type = fields.CharField(max_length=32, default="initial")
    suppressed = fields.BooleanField(default=False)
    human_overridden = fields.BooleanField(default=False)
    reactions = fields.JSONField(default=dict)
    github_comment_id = fields.BigIntField(null=True)
    posted_at = fields.DatetimeField(null=True)

    class Meta(models.Model.Meta):
        table = "analysis_comments"


class FeedbackSignal(TimestampedFields, models.Model):
    feedback_signal_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun",
        related_name="feedback_signals",
        null=True,
        on_delete=fields.SET_NULL,
    )
    pull_request = fields.ForeignKeyField(
        "models.PullRequest", related_name="feedback_signals", on_delete=fields.CASCADE
    )
    signal_type = fields.CharField(max_length=64)
    value = fields.BooleanField(null=True)
    source = fields.CharField(max_length=64, default="manual")
    details = fields.JSONField(default=dict)
    observed_at = fields.DatetimeField(auto_now_add=True)

    class Meta(models.Model.Meta):
        table = "feedback_signals"


class EvaluationCase(TimestampedFields, models.Model):
    evaluation_case_id = fields.IntField(pk=True)
    slug = fields.CharField(max_length=255, unique=True)
    case_type = fields.CharField(max_length=64)
    source_repo = fields.CharField(max_length=255, null=True)
    source_pr_number = fields.IntField(null=True)
    expected_verdict = fields.CharField(max_length=64, null=True)
    expected_findings = fields.JSONField(default=list)
    historical_misses = fields.JSONField(default=list)
    tags = fields.JSONField(default=list)
    notes = fields.TextField(default="")

    class Meta(models.Model.Meta):
        table = "evaluation_cases"
