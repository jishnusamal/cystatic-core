from pydantic import BaseModel, Field
from typing import Literal, List
from dataclasses import dataclass, field
from core_engine.risk_flags import SignalType


ChangeType = Literal["added", "modified", "deleted", "renamed"]

class FunctionChanged(BaseModel):
    name: str
    file_path: str
    change_type: ChangeType = "modified"
    start_line: int | None = None
    end_line: int | None = None


class ImportChanged(BaseModel):
    module: str
    symbol: str | None = None
    file_path: str
    change_type: ChangeType = "modified"


class KeywordDetected(BaseModel):
    keyword: str
    category: SignalType
    file_path: str
    line_number: int | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class FileChanged(BaseModel):
    path: str
    change_type: ChangeType = "modified"
    added_lines: int = 0
    removed_lines: int = 0


class PullRequestIR(BaseModel):
    files_changed: list[FileChanged] = Field(default_factory=list)
    functions_changed: list[FunctionChanged] = Field(default_factory=list)
    imports_changed: list[ImportChanged] = Field(default_factory=list)
    keywords_detected: list[KeywordDetected] = Field(default_factory=list)


@dataclass
class DiffLine:
    line_type: str
    content: str
    source_line_no: int | None
    target_line_no: int | None


@dataclass
class DiffHunk:
    file_path: str
    source_start: int
    source_length: int
    target_start: int
    target_length: int
    added_lines: List[int] = field(default_factory=list)
    removed_lines: List[int] = field(default_factory=list)
    lines: List[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    file_path: str
    added_lines: List[int]
    removed_lines: List[int]
    hunks: List[DiffHunk]


@dataclass
class DiffIR:
    files: List[FileDiff]