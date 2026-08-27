import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict


def contract_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
