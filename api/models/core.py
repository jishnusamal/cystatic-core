from __future__ import annotations

from tortoise import fields, models


class TimestampedFields:
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


class Organization(TimestampedFields, models.Model):
    org_id = fields.IntField(pk=True)
    github_installation_id = fields.BigIntField(null=True, unique=True)
    github_organization_login = fields.CharField(max_length=255, null=True)
    plan = fields.CharField(max_length=64, default="free")
    billing_status = fields.CharField(max_length=64, default="inactive")
    onboarding_status = fields.CharField(max_length=64, default="pending")
    owner_login = fields.CharField(max_length=255, null=True)
    owner_name = fields.CharField(max_length=255, null=True)
    owner_email = fields.CharField(max_length=255, null=True)
    metadata = fields.JSONField(default=dict)

    class Meta(models.Model.Meta):
        table = "organizations"


class Repository(TimestampedFields, models.Model):
    repo_id = fields.IntField(pk=True)
    organization = fields.ForeignKeyField(
        "models.Organization", related_name="repositories", on_delete=fields.CASCADE
    )
    github_repo_id = fields.BigIntField(null=True)
    full_name = fields.CharField(max_length=255, unique=True)
    name = fields.CharField(max_length=255)
    enabled = fields.BooleanField(default=True)
    default_branch = fields.CharField(max_length=255, default="main")
    language_breakdown = fields.JSONField(default=dict)
    framework_hints = fields.JSONField(default=list)
    last_analyzed_pr_number = fields.IntField(null=True)
    last_analyzed_head_sha = fields.CharField(max_length=128, null=True)
    last_analysis_at = fields.DatetimeField(null=True)
    installation_metadata = fields.JSONField(default=dict)

    class Meta(models.Model.Meta):
        table = "repositories"


class PullRequest(TimestampedFields, models.Model):
    pull_request_id = fields.IntField(pk=True)
    repository = fields.ForeignKeyField(
        "models.Repository", related_name="pull_requests", on_delete=fields.CASCADE
    )
    github_pr_id = fields.BigIntField(null=True)
    number = fields.IntField()
    title = fields.CharField(max_length=512, default="")
    author_login = fields.CharField(max_length=255, default="")
    head_sha = fields.CharField(max_length=128, default="")
    base_sha = fields.CharField(max_length=128, default="")
    merge_sha = fields.CharField(max_length=128, null=True)
    state = fields.CharField(max_length=32, default="open")
    merged = fields.BooleanField(default=False)
    changed_files = fields.JSONField(default=list)
    changed_files_count = fields.IntField(default=0)
    factor_verdict = fields.CharField(max_length=64, null=True)
    analysis_version = fields.CharField(max_length=64, null=True)

    class Meta(models.Model.Meta):
        table = "pull_requests"
        unique_together = (("repository", "number"),)


class PullRequestSnapshot(TimestampedFields, models.Model):
    snapshot_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun", related_name="snapshots", on_delete=fields.CASCADE
    )
    pull_request = fields.ForeignKeyField(
        "models.PullRequest", related_name="snapshots", on_delete=fields.CASCADE
    )
    snapshot_kind = fields.CharField(max_length=64, default="analysis_input")
    head_sha = fields.CharField(max_length=128, default="")
    base_sha = fields.CharField(max_length=128, default="")
    title = fields.CharField(max_length=512, default="")
    author_login = fields.CharField(max_length=255, default="")
    state = fields.CharField(max_length=32, default="")
    merged = fields.BooleanField(default=False)
    changed_files = fields.JSONField(default=list)
    raw_payload = fields.JSONField(default=dict)

    class Meta(models.Model.Meta):
        table = "pull_request_snapshots"
