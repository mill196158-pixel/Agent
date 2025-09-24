from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Any

class Step(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)

class Plan(BaseModel):
    goal: str
    steps: List[Step]

def validate_plan(raw: dict) -> Plan:
    return Plan(**raw)
