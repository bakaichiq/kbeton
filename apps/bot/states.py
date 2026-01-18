from __future__ import annotations
from aiogram.fsm.state import State, StatesGroup

class FinanceUploadState(StatesGroup):
    waiting_file = State()

class CounterpartyUploadState(StatesGroup):
    waiting_file = State()

class CounterpartyCardState(StatesGroup):
    waiting_name = State()

class ArticleAddState(StatesGroup):
    waiting_name = State()

class MappingRuleAddState(StatesGroup):
    waiting_rule = State()

class PriceSetState(StatesGroup):
    waiting_kind = State()
    waiting_key = State()
    waiting_price = State()

class ShiftApprovalState(StatesGroup):
    reject_comment = State()

class ShiftCloseState(StatesGroup):
    waiting_shift_type = State()
    waiting_equipment = State()
    waiting_area = State()
    waiting_line_type = State()
    waiting_crushed = State()
    waiting_screening = State()
    waiting_sand = State()
    waiting_concrete_mark = State()
    waiting_concrete_qty = State()
    waiting_concrete_more = State()
    waiting_comment = State()
    waiting_confirm = State()

class ShiftReportState(StatesGroup):
    waiting_period = State()
    waiting_line = State()
    waiting_operator = State()

class InventoryTxnState(StatesGroup):
    waiting_item = State()
    waiting_qty = State()
    waiting_receiver = State()
    waiting_department = State()
    waiting_comment = State()

class InventoryAdjustState(StatesGroup):
    waiting_item = State()
    waiting_fact_qty = State()
    waiting_comment = State()

class AdminSetRoleState(StatesGroup):
    waiting_tg_id = State()
    waiting_role = State()

class ConcreteRecipeState(StatesGroup):
    waiting_mark = State()
    waiting_cement = State()
    waiting_sand = State()
    waiting_crushed = State()
    waiting_screening = State()
    waiting_water = State()
    waiting_additives = State()

class MaterialPriceState(StatesGroup):
    waiting_item = State()
    waiting_price = State()

class OverheadCostState(StatesGroup):
    waiting_name = State()
    waiting_cost = State()
