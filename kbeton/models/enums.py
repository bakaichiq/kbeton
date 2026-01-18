from __future__ import annotations
from enum import Enum

class Role(str, Enum):
    Admin = "Admin"
    FinDir = "FinDir"
    HeadProd = "HeadProd"
    Operator = "Operator"
    Warehouse = "Warehouse"
    Viewer = "Viewer"

class TxType(str, Enum):
    income = "income"
    expense = "expense"
    unknown = "unknown"

class PatternType(str, Enum):
    contains = "contains"
    regex = "regex"

class ShiftType(str, Enum):
    day = "day"
    night = "night"

class ShiftStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"

class ProductType(str, Enum):
    crushed_stone = "crushed_stone"
    screening = "screening"
    sand = "sand"
    concrete = "concrete"
    blocks = "blocks"

class InventoryTxnType(str, Enum):
    issue = "issue"
    writeoff = "writeoff"
    adjustment = "adjustment"

class PriceKind(str, Enum):
    concrete = "concrete"
    blocks = "blocks"
