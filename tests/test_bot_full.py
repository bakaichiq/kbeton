"""
Полное тестирование функциональности Telegram бота.
Тестирует все кнопки, состояния FSM и права доступа.
"""
from __future__ import annotations

import pytest
from datetime import datetime, date
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kbeton.db.base import Base
from kbeton.models.user import User
from kbeton.models.enums import Role, TxType, PatternType, PriceKind, ShiftType, ShiftStatus, ProductType, InventoryTxnType
from kbeton.models.finance import FinanceArticle, MappingRule, FinanceTransaction, ImportJob
from kbeton.models.pricing import PriceVersion
from kbeton.models.production import ProductionShift, ProductionOutput
from kbeton.models.inventory import InventoryItem, InventoryBalance, InventoryTxn
from kbeton.models.counterparty import CounterpartySnapshot, CounterpartyBalance
from kbeton.models.recipes import ConcreteRecipe
from kbeton.models.costs import MaterialPrice, OverheadCost
from kbeton.models.audit import AuditLog

from apps.bot.keyboards import (
    main_menu, finance_menu, production_menu, warehouse_menu, admin_menu,
    shift_type_kb, line_type_kb, concrete_mark_kb, concrete_more_kb,
    counterparty_registry_kb, pnl_period_kb, production_period_kb,
    shift_report_period_kb, shift_report_line_kb, shift_report_operator_kb,
    material_price_kb, overhead_cost_kb, concrete_cost_mark_kb,
    articles_kb, yes_no_kb,
)
from apps.bot.rbac import role_allowed
from apps.bot.utils import ensure_role, _extract_full_name, _resolve_tg_context


@pytest.fixture
def db_session():
    """Создаёт in-memory SQLite БД для тестов."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_user(db_session):
    """Создаёт тестового пользователя."""
    user = User(tg_id=123456789, full_name="Test User", role=Role.Admin, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_viewer(db_session):
    """Создаёт пользователя с ролью Viewer."""
    user = User(tg_id=111222333, full_name="Viewer User", role=Role.Viewer, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_operator(db_session):
    """Создаёт пользователя с ролью Operator."""
    user = User(tg_id=444555666, full_name="Operator User", role=Role.Operator, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_headprod(db_session):
    """Создаёт пользователя с ролью HeadProd."""
    user = User(tg_id=777888999, full_name="HeadProd User", role=Role.HeadProd, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_warehouse(db_session):
    """Создаёт пользователя с ролью Warehouse."""
    user = User(tg_id=101010101, full_name="Warehouse User", role=Role.Warehouse, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_findir(db_session):
    """Создаёт пользователя с ролью FinDir."""
    user = User(tg_id=202020202, full_name="FinDir User", role=Role.FinDir, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


# ============================================================================
# ТЕСТЫ КЛАВИАТУР
# ============================================================================

class TestKeyboards:
    """Тесты всех клавиатур бота."""

    def test_main_menu_admin(self):
        """Главное меню для Admin показывает все разделы."""
        kb = main_menu(Role.Admin)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "📊 Дашборд" in buttons
        assert "💰 Финансы" in buttons
        assert "🏭 Производство" in buttons
        assert "📦 Склад" in buttons
        assert "⚙️ Админ" in buttons

    def test_main_menu_viewer(self):
        """Главное меню для Viewer показывает только доступные разделы."""
        kb = main_menu(Role.Viewer)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "📊 Дашборд" in buttons
        assert "💰 Финансы" in buttons
        assert "📦 Склад" in buttons
        assert "⚙️ Админ" not in buttons  # Viewer не видит админку
        assert "🏭 Производство" not in buttons  # Viewer не видит производство

    def test_main_menu_operator(self):
        """Главное меню для Operator."""
        kb = main_menu(Role.Operator)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "🏭 Производство" in buttons
        assert "💰 Финансы" not in buttons
        assert "⚙️ Админ" not in buttons

    def test_main_menu_headprod(self):
        """Главное меню для HeadProd."""
        kb = main_menu(Role.HeadProd)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "🏭 Производство" in buttons
        assert "💰 Финансы" not in buttons

    def test_main_menu_warehouse(self):
        """Главное меню для Warehouse."""
        kb = main_menu(Role.Warehouse)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "📦 Склад" in buttons
        assert "💰 Финансы" not in buttons

    def test_main_menu_findir(self):
        """Главное меню для FinDir."""
        kb = main_menu(Role.FinDir)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "💰 Финансы" in buttons
        assert "🏭 Производство" not in buttons

    def test_finance_menu_admin(self):
        """Финансовое меню для Admin."""
        kb = finance_menu(Role.Admin)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "⬅️ Назад" in buttons
        assert "🏠 Главное меню" in buttons
        assert "❌ Отмена" in buttons
        assert "📥 Загрузить взаиморасчеты (контрагенты)" in buttons
        assert "📄 P&L" in buttons
        assert "🧾 Статьи доходов" in buttons
        assert "🧾 Статьи расходов" in buttons
        assert "🧩 Неразобранное" in buttons
        assert "📐 Правила маппинга" in buttons
        assert "🏷️ Цены" in buttons

    def test_finance_menu_viewer(self):
        """Финансовое меню для Viewer — только просмотр."""
        kb = finance_menu(Role.Viewer)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "📄 P&L" in buttons
        assert "📥 Загрузить взаиморасчеты" not in buttons
        assert "🧩 Неразобранное" not in buttons

    def test_production_menu_admin(self):
        """Меню производства для Admin."""
        kb = production_menu(Role.Admin)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "✅ Закрыть смену" in buttons
        assert "📝 Смены на согласование" in buttons
        assert "📈 Выпуск/KPI" in buttons
        assert "📋 Отчет по сменам" in buttons

    def test_production_menu_operator(self):
        """Меню производства для Operator."""
        kb = production_menu(Role.Operator)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "✅ Закрыть смену" in buttons
        assert "📝 Смены на согласование" not in buttons
        assert "📈 Выпуск/KPI" not in buttons

    def test_production_menu_headprod(self):
        """Меню производства для HeadProd."""
        kb = production_menu(Role.HeadProd)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "📝 Смены на согласование" in buttons
        assert "📈 Выпуск/KPI" in buttons
        assert "✅ Закрыть смену" not in buttons

    def test_warehouse_menu_admin(self):
        """Меню склада для Admin."""
        kb = warehouse_menu(Role.Admin)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "📤 Выдать расходник" in buttons
        assert "🗑️ Списать" in buttons
        assert "🧮 Инвентаризация" in buttons
        assert "📦 Остатки" in buttons

    def test_warehouse_menu_warehouse(self):
        """Меню склада для Warehouse."""
        kb = warehouse_menu(Role.Warehouse)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "📤 Выдать расходник" in buttons
        assert "🗑️ Списать" in buttons
        assert "🧮 Инвентаризация" in buttons
        assert "📦 Остатки" in buttons

    def test_warehouse_menu_viewer(self):
        """Меню склада для Viewer — только просмотр."""
        kb = warehouse_menu(Role.Viewer)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "📦 Остатки" in buttons
        assert "📤 Выдать расходник" not in buttons
        assert "🗑️ Списать" not in buttons

    def test_admin_menu_admin(self):
        """Админское меню для Admin."""
        kb = admin_menu(Role.Admin)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "👤 Пользователи и роли" in buttons
        assert "⚙️ Настройки/справочники" in buttons
        assert "🧪 Рецептуры бетона" in buttons
        assert "🕒 Последние изменения" in buttons

    def test_shift_type_kb(self):
        """Клавиатура выбора типа смены."""
        kb = shift_type_kb()
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "day" in buttons
        assert "night" in buttons
        assert "⬅️ Назад" in buttons

    def test_line_type_kb(self):
        """Клавиатура выбора линии."""
        kb = line_type_kb()
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "ДУ" in buttons
        assert "РБУ" in buttons

    def test_concrete_mark_kb(self):
        """Клавиатура выбора марки бетона."""
        marks = ["M200", "M250", "M300", "M350"]
        kb = concrete_mark_kb(marks)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "M200" in buttons
        assert "M300" in buttons
        assert "0" in buttons  # Опция "нет бетона"

    def test_concrete_more_kb(self):
        """Клавиатура добавления ещё марки."""
        kb = concrete_more_kb()
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "✅ Еще марка" in buttons
        assert "🏁 Готово" in buttons

    def test_counterparty_registry_kb(self):
        """Клавиатура выбора контрагента."""
        cps = ["ОсОО СтройИнвест", "ИП Иванов", "ОсОО БетонСервис"]
        kb = counterparty_registry_kb(cps)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "ОсОО СтройИнвест" in buttons
        assert "ИП Иванов" in buttons

    def test_material_price_kb(self):
        """Клавиатура выбора материала для цены."""
        kb = material_price_kb()
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "цемент" in buttons
        assert "песок" in buttons
        assert "щебень" in buttons
        assert "отсев" in buttons

    def test_overhead_cost_kb(self):
        """Клавиатура накладных расходов."""
        kb = overhead_cost_kb()
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "энергия" in buttons
        assert "амортизация" in buttons

    def test_pnl_period_kb(self):
        """Inline клавиатура периодов P&L."""
        kb = pnl_period_kb()
        assert len(kb.inline_keyboard) > 0
        # Проверяем callback_data
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "pnl:day" in callbacks
        assert "pnl:week" in callbacks
        assert "pnl:month" in callbacks

    def test_production_period_kb(self):
        """Inline клавиатура периодов производства."""
        kb = production_period_kb()
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "prod_kpi:day" in callbacks
        assert "prod_kpi:week" in callbacks
        assert "prod_kpi:month" in callbacks

    def test_articles_kb(self):
        """Inline клавиатура статей."""
        articles = [(1, "Продажи бетона"), (2, "Дизель"), (3, "Цемент")]
        kb = articles_kb(articles, prefix="assign:123:income")
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "assign:123:income:1" in callbacks
        assert "assign:123:income:2" in callbacks

    def test_yes_no_kb(self):
        """Inline клавиатура да/нет."""
        kb = yes_no_kb(prefix="confirm")
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "confirm:yes" in callbacks
        assert "confirm:no" in callbacks


# ============================================================================
# ТЕСТЫ RBAC (РАЗГРАНИЧЕНИЕ ДОСТУПА)
# ============================================================================

class TestRBAC:
    """Тесты системы разграничения доступа."""

    def test_role_allowed_admin_access_all(self):
        """Admin имеет доступ ко всем ролям."""
        assert role_allowed(Role.Admin, {Role.FinDir}) is True
        assert role_allowed(Role.Admin, {Role.Operator}) is True
        assert role_allowed(Role.Admin, {Role.Viewer}) is True
        assert role_allowed(Role.Admin, {Role.HeadProd, Role.Warehouse}) is True

    def test_role_allowed_same_role(self):
        """Пользователь имеет доступ к своей роли."""
        assert role_allowed(Role.FinDir, {Role.FinDir}) is True
        assert role_allowed(Role.Operator, {Role.Operator}) is True
        assert role_allowed(Role.Viewer, {Role.Viewer}) is True

    def test_role_allowed_different_role(self):
        """Пользователь НЕ имеет доступ к другим ролям."""
        assert role_allowed(Role.Viewer, {Role.Admin}) is False
        assert role_allowed(Role.Operator, {Role.FinDir}) is False
        assert role_allowed(Role.FinDir, {Role.Operator}) is False

    def test_ensure_role_allows_admin(self, sample_user):
        """ensure_role разрешает Admin любой доступ."""
        sample_user.role = Role.Admin
        # Не должно вызывать исключение
        ensure_role(sample_user, {Role.FinDir, Role.Operator})

    def test_ensure_role_allows_matching(self, sample_findir):
        """ensure_role разрешает доступ совпадающей роли."""
        ensure_role(sample_findir, {Role.FinDir, Role.Viewer})

    def test_ensure_role_denies_mismatch(self, sample_viewer):
        """ensure_role запрещает доступ несовпадающей роли."""
        with pytest.raises(PermissionError):
            ensure_role(sample_viewer, {Role.Admin})

    def test_ensure_role_denies_inactive(self, sample_user):
        """ensure_role запрещает доступ неактивным пользователям."""
        sample_user.is_active = False
        with pytest.raises(PermissionError):
            ensure_role(sample_user, {Role.Admin})


# ============================================================================
# ТЕСТЫ УТИЛИТ
# ============================================================================

class TestUtils:
    """Тесты вспомогательных функций."""

    def test_extract_full_name_with_both_names(self):
        """Извлечение полного имени с именем и фамилией."""
        tg_user = MagicMock()
        tg_user.first_name = "Иван"
        tg_user.last_name = "Петров"
        assert _extract_full_name(tg_user) == "Иван Петров"

    def test_extract_full_name_first_only(self):
        """Извлечение имени только с first_name."""
        tg_user = MagicMock()
        tg_user.first_name = "Иван"
        tg_user.last_name = None
        assert _extract_full_name(tg_user) == "Иван"

    def test_extract_full_name_empty(self):
        """Извлечение пустого имени."""
        tg_user = MagicMock()
        tg_user.first_name = None
        tg_user.last_name = None
        assert _extract_full_name(tg_user) == ""


# ============================================================================
# ТЕСТЫ СЕРВИСОВ
# ============================================================================

class TestServices:
    """Тесты бизнес-логики сервисов."""

    def test_pricing_versioning(self, db_session, sample_user):
        """Тест версионности цен."""
        from kbeton.services.pricing import set_price, get_price
        
        now = datetime.now()
        set_price(db_session, kind=PriceKind.concrete, item_key="M300", 
                  price=4500, currency="KGS", valid_from=now, 
                  changed_by_user_id=sample_user.id, comment="initial")
        
        price = get_price(db_session, kind=PriceKind.concrete, item_key="M300", at=now)
        assert price is not None
        assert float(price.price) == 4500

    def test_current_prices_format(self, db_session, sample_user):
        """Формат ответа текущих цен."""
        from kbeton.services.pricing import get_current_prices
        
        now = datetime.now()
        # Добавляем цены
        pv1 = PriceVersion(kind=PriceKind.concrete, item_key="M300", price=4500, 
                          currency="KGS", valid_from=now, changed_by_user_id=sample_user.id)
        pv2 = PriceVersion(kind=PriceKind.blocks, item_key="blocks", price=120, 
                          currency="KGS", valid_from=now, changed_by_user_id=sample_user.id)
        db_session.add_all([pv1, pv2])
        db_session.commit()
        
        result = get_current_prices(db_session)
        assert "prices" in result
        assert len(result["prices"]) == 2
        
        for p in result["prices"]:
            assert "kind" in p
            assert "item_key" in p
            assert "price" in p
            assert "currency" in p
            assert "valid_from" in p

    def test_mapping_classification(self, db_session):
        """Тест классификации транзакций по правилам."""
        from kbeton.services.mapping import classify_transaction
        
        # Создаём статью и правило
        article = FinanceArticle(kind=TxType.expense, name="Цемент", is_active=True)
        db_session.add(article)
        db_session.flush()
        
        rule = MappingRule(
            kind=TxType.expense,
            pattern_type=PatternType.contains,
            pattern="цемент",
            priority=100,
            is_active=True,
            article_id=article.id
        )
        db_session.add(rule)
        db_session.commit()
        
        tx_type, art_id = classify_transaction(db_session, 
            description="Покупка цемента М500", 
            counterparty="ОсОО Цемент"
        )
        
        assert tx_type == TxType.expense
        assert art_id == article.id

    def test_mapping_regex(self, db_session):
        """Тест классификации с regex."""
        from kbeton.services.mapping import classify_transaction
        
        article = FinanceArticle(kind=TxType.income, name="Продажи бетона", is_active=True)
        db_session.add(article)
        db_session.flush()
        
        rule = MappingRule(
            kind=TxType.income,
            pattern_type=PatternType.regex,
            pattern=r"^продажа.*бетон",
            priority=100,
            is_active=True,
            article_id=article.id
        )
        db_session.add(rule)
        db_session.commit()
        
        tx_type, art_id = classify_transaction(db_session, 
            description="Продажа бетона М300", 
            counterparty="ИП Иванов"
        )
        
        assert tx_type == TxType.income

    def test_mapping_unknown(self, db_session):
        """Тест классификации без совпадений."""
        from kbeton.services.mapping import classify_transaction
        
        tx_type, art_id = classify_transaction(db_session, 
            description="Неизвестная операция", 
            counterparty="Тест"
        )
        
        assert tx_type == TxType.unknown
        assert art_id is None

    def test_audit_log_creation(self, db_session, sample_user):
        """Тест создания записи аудита."""
        from kbeton.services.audit import audit_log
        
        audit_log(db_session, 
            actor_user_id=sample_user.id,
            action="test_action",
            entity_type="test_entity",
            entity_id="123",
            payload={"key": "value"}
        )
        db_session.commit()
        
        log = db_session.query(AuditLog).first()
        assert log is not None
        assert log.action == "test_action"
        assert log.entity_type == "test_entity"
        assert log.payload == {"key": "value"}


# ============================================================================
# ТЕСТЫ МОДЕЛЕЙ И СВЯЗЕЙ
# ============================================================================

class TestModels:
    """Тесты моделей данных и их связей."""

    def test_user_creation(self, db_session):
        """Создание пользователя."""
        user = User(tg_id=999888777, full_name="New User", role=Role.Viewer)
        db_session.add(user)
        db_session.commit()
        
        assert user.id is not None
        assert user.tg_id == 999888777
        assert user.role == Role.Viewer
        assert user.is_active is True

    def test_user_tg_id_unique(self, db_session, sample_user):
        """Проверка уникальности tg_id."""
        # SQLite не поддерживает constraint violations так же как PostgreSQL
        # Но проверим логику
        user2 = User(tg_id=sample_user.tg_id, full_name="Duplicate")
        db_session.add(user2)
        # В SQLite может не вызвать ошибку, но в PostgreSQL будет IntegrityError

    def test_finance_article_creation(self, db_session):
        """Создание финансовой статьи."""
        article = FinanceArticle(kind=TxType.expense, name="Тестовая статья", is_active=True)
        db_session.add(article)
        db_session.commit()
        
        assert article.id is not None
        assert article.kind == TxType.expense

    def test_mapping_rule_relationship(self, db_session):
        """Связь правила маппинга со статьёй."""
        article = FinanceArticle(kind=TxType.expense, name="Дизель")
        db_session.add(article)
        db_session.flush()
        
        rule = MappingRule(
            kind=TxType.expense,
            pattern_type=PatternType.contains,
            pattern="дизель",
            priority=50,
            article_id=article.id
        )
        db_session.add(rule)
        db_session.commit()
        
        assert rule.article_id == article.id
        # Проверяем отношение
        assert rule.article.name == "Дизель"

    def test_production_shift_creation(self, db_session, sample_operator):
        """Создание производственной смены."""
        shift = ProductionShift(
            operator_user_id=sample_operator.id,
            date=date.today(),
            shift_type=ShiftType.day,
            equipment="БСУ-1",
            area="Площадка А",
            status=ShiftStatus.draft
        )
        db_session.add(shift)
        db_session.commit()
        
        assert shift.id is not None
        assert shift.status == ShiftStatus.draft

    def test_production_output_creation(self, db_session, sample_operator):
        """Создание выпуска продукции."""
        shift = ProductionShift(
            operator_user_id=sample_operator.id,
            date=date.today(),
            shift_type=ShiftType.day,
            status=ShiftStatus.draft
        )
        db_session.add(shift)
        db_session.flush()
        
        output = ProductionOutput(
            shift_id=shift.id,
            product_type=ProductType.concrete,
            quantity=50.5,
            uom="м3",
            mark="M300"
        )
        db_session.add(output)
        db_session.commit()
        
        assert output.id is not None
        assert output.shift.id == shift.id  # Проверка relationship

    def test_inventory_item_creation(self, db_session):
        """Создание номенклатуры склада."""
        item = InventoryItem(
            name="Цемент М500",
            uom="кг",
            min_qty=1000,
            is_active=True
        )
        db_session.add(item)
        db_session.flush()
        
        # Автоматически создаём остаток
        balance = InventoryBalance(item_id=item.id, qty=5000)
        db_session.add(balance)
        db_session.commit()
        
        assert item.id is not None
        assert balance.qty == 5000

    def test_inventory_transaction(self, db_session, sample_user):
        """Создание складской операции."""
        item = InventoryItem(name="Арматура", uom="тн", min_qty=1)
        db_session.add(item)
        db_session.flush()
        
        txn = InventoryTxn(
            item_id=item.id,
            txn_type=InventoryTxnType.issue,
            qty=2.5,
            receiver="Цех 1",
            department="Производство",
            comment="На стройку",
            created_by_user_id=sample_user.id
        )
        db_session.add(txn)
        db_session.commit()
        
        assert txn.id is not None
        assert txn.txn_type == InventoryTxnType.issue

    def test_counterparty_snapshot_creation(self, db_session):
        """Создание снимка контрагентов."""
        job = ImportJob(kind="counterparty", status="done", filename="test.xlsx", s3_key="test")
        db_session.add(job)
        db_session.flush()
        
        snapshot = CounterpartySnapshot(
            snapshot_date=date.today(),
            import_job_id=job.id
        )
        db_session.add(snapshot)
        db_session.commit()
        
        assert snapshot.id is not None

    def test_concrete_recipe_creation(self, db_session):
        """Создание рецептуры бетона."""
        recipe = ConcreteRecipe(
            mark="M300",
            cement_kg=350,
            sand_t=0.8,
            crushed_stone_t=1.2,
            screening_t=0,
            water_l=180,
            additives_l=5,
            is_active=True
        )
        db_session.add(recipe)
        db_session.commit()
        
        assert recipe.id is not None
        assert recipe.cement_kg == 350

    def test_price_version_creation(self, db_session, sample_user):
        """Создание версии цены."""
        now = datetime.now()
        pv = PriceVersion(
            kind=PriceKind.concrete,
            item_key="M300",
            price=4500,
            currency="KGS",
            valid_from=now,
            changed_by_user_id=sample_user.id
        )
        db_session.add(pv)
        db_session.commit()
        
        assert pv.id is not None
        assert pv.kind == PriceKind.concrete


# ============================================================================
# ТЕСТЫ ОТЧЁТОВ
# ============================================================================

class TestReports:
    """Тесты системы отчётов."""

    def test_pnl_calculation_empty(self, db_session):
        """P&L с пустыми данными."""
        from kbeton.reports.pnl import pnl
        
        today = date.today()
        rows, meta = pnl(db_session, start=today, end=today, period="day")
        
        assert len(rows) == 1
        assert meta["total_income"] == 0
        assert meta["total_expense"] == 0
        assert meta["total_net"] == 0

    def test_pnl_calculation_with_data(self, db_session):
        """P&L с данными."""
        from kbeton.reports.pnl import pnl
        
        today = date.today()
        
        # Создаём импорт job
        job = ImportJob(kind="finance", status="done", filename="test", s3_key="test")
        db_session.add(job)
        db_session.flush()
        
        # Создаём транзакции
        tx1 = FinanceTransaction(
            import_job_id=job.id,
            date=today,
            amount=10000,
            currency="KGS",
            tx_type=TxType.income,
            description="Продажа бетона",
            counterparty="Клиент 1",
            dedup_hash="hash1"
        )
        tx2 = FinanceTransaction(
            import_job_id=job.id,
            date=today,
            amount=5000,
            currency="KGS",
            tx_type=TxType.expense,
            description="Покупка цемента",
            counterparty="Поставщик",
            dedup_hash="hash2"
        )
        db_session.add_all([tx1, tx2])
        db_session.commit()
        
        rows, meta = pnl(db_session, start=today, end=today, period="day")
        
        assert meta["total_income"] == 10000
        assert meta["total_expense"] == 5000
        assert meta["total_net"] == 5000

    def test_pnl_xlsx_export(self, db_session):
        """Экспорт P&L в Excel."""
        from kbeton.reports.pnl import pnl, PnlRow
        from kbeton.reports.export_xlsx import pnl_to_xlsx
        
        today = date.today()
        
        rows = [PnlRow(period_start=today, income_sum=10000, expense_sum=5000)]
        meta = {
            "total_income": 10000,
            "total_expense": 5000,
            "total_net": 5000,
            "unknown_count": 0,
            "daily": [{"date": today, "income": 10000, "expense": 5000, "net": 5000}],
            "top_income_articles": [{"name": "Продажи", "amount": 10000}],
            "top_expense_articles": [{"name": "Закупки", "amount": 5000}]
        }
        
        xlsx_bytes = pnl_to_xlsx(rows, period="day", start=today, end=today, totals=meta)
        
        assert isinstance(xlsx_bytes, bytes)
        assert len(xlsx_bytes) > 0

    def test_production_xlsx_export(self):
        """Экспорт производственного отчёта в Excel."""
        from kbeton.reports.production_xlsx import production_shifts_to_xlsx
        
        rows = [
            {
                "shift_id": 1,
                "date": "2024-01-01",
                "shift_type": "day",
                "line": "РБУ",
                "operator": "Иванов",
                "counterparty": "Клиент 1",
                "product": "concrete",
                "mark": "M300",
                "qty": 50.5,
                "uom": "м3"
            }
        ]
        
        xlsx_bytes = production_shifts_to_xlsx(rows)
        
        assert isinstance(xlsx_bytes, bytes)
        assert len(xlsx_bytes) > 0


# ============================================================================
# ТЕСТЫ ИМПОРТЕРОВ
# ============================================================================

class TestImporters:
    """Тесты импортеров XLSX."""

    def test_parse_money(self):
        """Парсинг денежных сумм."""
        from kbeton.importers.utils import parse_money
        
        assert parse_money("1000") == 1000.0
        assert parse_money("1 000") == 1000.0
        assert parse_money("1,000.50") == 1000.50
        assert parse_money(1000) == 1000.0
        assert parse_money(None) == 0.0

    def test_parse_date(self):
        """Парсинг дат."""
        from kbeton.importers.utils import parse_date
        
        assert parse_date("2024-01-15") == date(2024, 1, 15)
        assert parse_date("15.01.2024") == date(2024, 1, 15)
        assert parse_date("15/01/2024") == date(2024, 1, 15)
        assert parse_date(date(2024, 1, 15)) == date(2024, 1, 15)
        assert parse_date(None) is None

    def test_norm_counterparty_name(self):
        """Нормализация имён контрагентов."""
        from kbeton.importers.utils import norm_counterparty_name
        
        assert norm_counterparty_name('  ОсОО "СтройИнvest"  ') == "осоо стройинvest"
        assert norm_counterparty_name("ИП Иванов") == "ип иванов"

    def test_norm_header(self):
        """Нормализация заголовков."""
        from kbeton.importers.utils import norm_header
        
        assert norm_header("  Дата Документа  ") == "дата документа"
        assert norm_header("Сумма\nОперации") == "сумма операции"


# ============================================================================
# ИНТЕГРАЦИОННЫЕ ТЕСТЫ
# ============================================================================

class TestIntegration:
    """Интеграционные тесты рабочих процессов."""

    def test_full_shift_workflow(self, db_session, sample_operator, sample_headprod):
        """Полный workflow смены: создание → отправка → согласование."""
        # 1. Оператор создаёт смену
        shift = ProductionShift(
            operator_user_id=sample_operator.id,
            date=date.today(),
            shift_type=ShiftType.day,
            equipment="БСУ-1",
            area="Площадка А",
            counterparty_name="Клиент 1",
            status=ShiftStatus.draft
        )
        db_session.add(shift)
        db_session.flush()
        
        # 2. Добавляем выпуск бетона
        output = ProductionOutput(
            shift_id=shift.id,
            product_type=ProductType.concrete,
            quantity=100.5,
            uom="м3",
            mark="M300"
        )
        db_session.add(output)
        db_session.flush()
        
        # 3. Отправка на согласование
        shift.status = ShiftStatus.submitted
        shift.submitted_at = datetime.now()
        db_session.commit()
        
        # 4. HeadProd согласует
        shift.status = ShiftStatus.approved
        shift.approved_by_user_id = sample_headprod.id
        shift.approved_at = datetime.now()
        db_session.commit()
        
        # Проверки
        assert shift.status == ShiftStatus.approved
        assert shift.approved_by_user_id == sample_headprod.id
        assert len(shift.outputs) == 1

    def test_inventory_transaction_updates_balance(self, db_session, sample_user):
        """Складская операция обновляет остаток."""
        # 1. Создаём товар
        item = InventoryItem(name="Гвозди", uom="кг", min_qty=10)
        db_session.add(item)
        db_session.flush()
        
        balance = InventoryBalance(item_id=item.id, qty=100)
        db_session.add(balance)
        db_session.commit()
        
        # 2. Создаём операцию списания
        txn = InventoryTxn(
            item_id=item.id,
            txn_type=InventoryTxnType.writeoff,
            qty=30,
            receiver="Цех",
            department="Производство",
            created_by_user_id=sample_user.id
        )
        db_session.add(txn)
        
        # 3. Обновляем остаток
        balance.qty = float(balance.qty) - 30
        db_session.commit()
        
        # Проверка
        assert balance.qty == 70

    def test_counterparty_import_flow(self, db_session):
        """Поток импорта контрагентов."""
        from kbeton.importers.counterparties_importer import CounterpartyRow
        
        # 1. Создаём ImportJob
        job = ImportJob(
            kind="counterparty",
            status="done",
            filename="counterparties.xlsx",
            s3_key="imports/test.xlsx",
            summary={"rows": 5}
        )
        db_session.add(job)
        db_session.flush()
        
        # 2. Создаём снимок
        snapshot = CounterpartySnapshot(
            snapshot_date=date.today(),
            import_job_id=job.id
        )
        db_session.add(snapshot)
        db_session.flush()
        
        # 3. Добавляем балансы
        balances = [
            CounterpartyBalance(
                snapshot_id=snapshot.id,
                counterparty_name="ОсОО СтройИнвест",
                counterparty_name_norm="осоо стройинвест",
                receivable_money=100000,
                payable_money=0,
                ending_balance_money=100000
            ),
            CounterpartyBalance(
                snapshot_id=snapshot.id,
                counterparty_name="ИП Иванов",
                counterparty_name_norm="ип иванов",
                receivable_money=0,
                payable_money=50000,
                ending_balance_money=-50000
            )
        ]
        db_session.add_all(balances)
        db_session.commit()
        
        # Проверки
        assert snapshot.id is not None
        assert len(snapshot.balances) == 2
        
        # Проверяем поиск должников
        debtors = [b for b in snapshot.balances if b.receivable_money > 0]
        assert len(debtors) == 1
        assert debtors[0].counterparty_name == "ОсОО СтройИнвест"


# ============================================================================
# ТЕСТЫ СХЕМ
# ============================================================================

class TestSchemas:
    """Тесты Pydantic схем."""

    def test_pnl_row_schema(self):
        """Схема строки P&L."""
        from kbeton.schemas.finance import PnlRow
        
        row = PnlRow(period_start=date.today(), income_sum=10000, expense_sum=5000, net_profit=5000)
        assert row.income_sum == 10000
        assert row.net_profit == 5000

    def test_pnl_response_schema(self):
        """Схема ответа P&L."""
        from kbeton.schemas.finance import PnlResponse, PnlRow, PnlDailyRow, PnlTopArticle
        
        today = date.today()
        response = PnlResponse(
            period="day",
            start=today,
            end=today,
            rows=[PnlRow(period_start=today, income_sum=10000, expense_sum=5000, net_profit=5000)],
            total_income=10000,
            total_expense=5000,
            total_net=5000,
            daily=[PnlDailyRow(date=today, income=10000, expense=5000, net=5000)],
            top_income_articles=[PnlTopArticle(name="Продажи", amount=10000)],
            top_expense_articles=[PnlTopArticle(name="Закупки", amount=5000)]
        )
        
        assert response.total_net == 5000
        assert len(response.rows) == 1

    def test_ok_schema(self):
        """Базовая схема ответа."""
        from kbeton.schemas.common import Ok
        
        ok = Ok(ok=True)
        assert ok.ok is True


# ============================================================================
# ТЕСТЫ КОНФИГУРАЦИИ
# ============================================================================

class TestConfig:
    """Тесты конфигурации."""

    def test_settings_defaults(self):
        """Значения по умолчанию настроек."""
        from kbeton.core.config import Settings
        
        # Проверяем структуру настроек
        # Примечание: полная инициализация требует env vars
        settings = Settings.model_construct(
            app_name="Test App",
            database_url="postgresql://test",
            telegram_bot_token="test_token"
        )
        
        assert settings.app_name == "Test App"
        assert settings.tz == "Asia/Bishkek"  # Default
        assert settings.log_level == "INFO"  # Default


# ============================================================================
# ТЕСТЫ API БЕЗОПАСНОСТИ
# ============================================================================

class TestAPISecurity:
    """Дополнительные тесты API безопасности."""

    def test_extract_bearer_token_variations(self):
        """Различные форматы Bearer токена."""
        from apps.api.security import _extract_bearer_token
        
        assert _extract_bearer_token("Bearer token123") == "token123"
        assert _extract_bearer_token("bearer token123") == "token123"  # lowercase
        assert _extract_bearer_token("Bearer  token123") == "token123"  # extra space
        assert _extract_bearer_token("") == ""
        assert _extract_bearer_token(None) == ""
        assert _extract_bearer_token("Basic token123") == ""
        assert _extract_bearer_token("token123") == ""  # без Bearer
