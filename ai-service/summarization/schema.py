"""Only source excerpts are accepted, including names and spoken deadlines."""

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Fact(StrictModel):
    text: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class Action(StrictModel):
    assignee: str | None = None
    task: str = Field(min_length=1)
    deadline_text: str | None = None
    evidence: str | None = None
    needs_confirmation: bool = False


class Extraction(StrictModel):
    objectives: list[Fact]
    results: list[Fact]
    issues: list[Fact]
    decisions: list[Fact]
    actions: list[Action]


class SummaryData(Extraction):
    warnings: list[str] = Field(default_factory=list)
