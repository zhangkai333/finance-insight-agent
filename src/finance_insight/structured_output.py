from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T=TypeVar("T",bound=BaseModel)
def extract_json(text:str)->dict:
    cleaned=re.sub(r"^```(?:json)?\s*|\s*```$","",text.strip(),flags=re.I); start=cleaned.find("{"); end=cleaned.rfind("}")
    if start<0 or end<start: raise ValueError("LLM 输出中没有 JSON 对象")
    candidate=cleaned[start:end+1]
    try: return json.loads(candidate)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",\s*([}\]])",r"\1",candidate).replace("'",'"'))
def validate_structured(text:str,model:type[T])->T:
    try: return model.model_validate(extract_json(text))
    except (ValueError,json.JSONDecodeError,ValidationError) as exc: raise ValueError(f"结构化输出校验失败: {exc}") from exc
