from tortoise import fields, models

class AnalysisRecord(models.Model):
    id = fields.IntField(pk=True)
    repo = fields.CharField(max_length=255)
    pr_number = fields.IntField()
    analysis_result = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "analysis_records"