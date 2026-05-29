from __future__ import annotations
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["text"] = "text"
    markdown: str


class ValueBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["value"] = "value"
    label: str
    value: float | int | str
    unit: str | None = None


class TableBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[Any]]
    caption: str | None = None


class ChartBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["chart"] = "chart"
    title: str
    plotly: dict[str, Any]


class RawReportBlock(BaseModel):
    """Report shape produced by Claude. The server enriches it with id+view_url before emitting."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["report"] = "report"
    title: str
    html: str


class ReportBlock(BaseModel):
    """Report shape sent to the browser — id and view_url filled in by the server."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["report"] = "report"
    id: str
    title: str
    html: str
    view_url: str


ClaudeBlock = Annotated[
    Union[TextBlock, ValueBlock, TableBlock, ChartBlock, RawReportBlock],
    Field(discriminator="kind"),
]

ClientBlock = Annotated[
    Union[TextBlock, ValueBlock, TableBlock, ChartBlock, ReportBlock],
    Field(discriminator="kind"),
]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    sql_log_id: str | None = None


class ClaudeEnvelope(BaseModel):
    """The JSON object Claude returns as its final message."""
    model_config = ConfigDict(extra="forbid")
    blocks: list[ClaudeBlock]
    citations: list[Citation] = Field(default_factory=list)
