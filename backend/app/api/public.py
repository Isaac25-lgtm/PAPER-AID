"""Serialize student responses without exposing disabled writing scores."""

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.runtime import Runtime


def student_json(rt: Runtime, value: BaseModel) -> JSONResponse:
    """Keep stored scores for calibration and admin while hiding them from every student route."""
    payload = value.model_dump(mode="json", by_alias=True)
    if not rt.settings.show_ai_score:
        _hide_score(payload)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


def _hide_score(value: object) -> None:
    if isinstance(value, list):
        for item in value:
            _hide_score(item)
    elif isinstance(value, dict):
        for key in ("analysis", "analysisAfter"):
            result = value.get(key)
            if isinstance(result, dict):
                for field in ("percent", "band", "confidence"):
                    result.pop(field, None)
        for child in value.values():
            _hide_score(child)
