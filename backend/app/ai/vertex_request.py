"""Vertex generation request options. No task names, role bindings or model selection.

Native SDK types describe tools, thinking, safety and content parts. Transport/authentication,
automatic retries and automatic function execution are deliberately not request overrides.
"""

from typing import Any, Literal

from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, model_validator


class VertexOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_output_tokens: int = Field(gt=0, strict=True)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    top_p: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    response_mime_type: Literal["text/plain", "application/json"] = "text/plain"
    response_json_schema: dict[str, Any] | None = None
    thinking_config: types.ThinkingConfig | None = None
    safety_settings: tuple[types.SafetySetting, ...] = ()
    tools: tuple[types.Tool, ...] = ()
    tool_config: types.ToolConfig | None = None
    grounding: types.GoogleSearch | None = None
    max_grounding_queries: int | None = Field(default=None, gt=0, strict=True)
    # The shortest time limit the call may get (seconds); never below what its output allowance needs (call_timeout).
    time_floor_sec: float | None = Field(default=None, gt=0, le=290)

    @model_validator(mode="after")
    def consistent(self) -> "VertexOptions":
        if self.response_json_schema is not None and self.response_mime_type != "application/json":
            raise ValueError("A response schema requires application/json")
        if self.thinking_config:
            t = self.thinking_config
            if t.thinking_level is not None and t.thinking_budget is not None:
                raise ValueError("Use thinking level or thinking budget, not both")
            if t.thinking_level == types.ThinkingLevel.THINKING_LEVEL_UNSPECIFIED:
                raise ValueError("Use an explicit supported thinking level or omit it")
            if t.thinking_budget is not None and t.thinking_budget < -1:
                raise ValueError("Invalid thinking budget")
        return self
