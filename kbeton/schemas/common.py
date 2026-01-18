from __future__ import annotations
from pydantic import BaseModel

class Ok(BaseModel):
    ok: bool = True
