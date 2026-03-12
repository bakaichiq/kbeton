# KBeton Bot ERP (Telegram + PostgreSQL)

Рабочая система учета и отчетности бетонного завода на базе **Telegram-бота + PostgreSQL** с Docker-деплоем, CI и автодеплоем.

## Что реализовано

- Telegram Bot (**aiogram 3**) с меню:
  - 📊 Дашборд
  - 💰 Финансы: P&L, статьи, правила маппинга, неразобранное (ручная разметка), импорт взаиморасчетов, цены (FinDir/Admin)
  - 🏭 Производство: закрытие смены оператором, согласование HeadProd
  - 📦 Склад: выдача/списание, остатки, минимальные остатки и алерты, инвентаризация
  - ⚙️ Админ: пользователи/роли, справочники
- API (**FastAPI**): `/health`, `/pnl`, `/pnl.xlsx`, `/prices/current`
- Импорт XLSX взаиморасчетов через S3/MinIO + Celery worker
- Классификация транзакций по правилам (contains/regex + priority)
- Версионность цен (valid_from, история изменений)
- Аудит действий (кто/что/когда/пэйлоад)
- Celery Beat:
  - ежедневный P&L (если задан `TELEGRAM_DEFAULT_CHAT_ID`)
  - алерты по складу (min_qty)

---

## Дефолты (явно фиксируем)

- Валюта по умолчанию: **KGS**
- Таймзона отчетов: **Asia/Bishkek**
- Цены:
  - бетон: `kind=concrete`, `item_key = марка`, например `M300`
  - блоки: `kind=blocks`, `item_key = blocks`
- RBAC:
  - авторизация по Telegram ID
  - новый пользователь при первом /start создается как `Viewer`
  - Admin имеет доступ ко всем командам

---

## Быстрый старт (Docker)

### 1) Подготовка окружения
Скопируйте `.env.example` → `.env` и задайте минимум:

- `TELEGRAM_BOT_TOKEN=...` (обязательно)
- `POSTGRES_PASSWORD=...` (обязательно)
- `S3_ACCESS_KEY_ID=...` и `S3_SECRET_ACCESS_KEY=...` (обязательно)
- `API_AUTH_ENABLED=true` и `API_TOKEN=...` для защиты API
- (опционально) `TELEGRAM_DEFAULT_CHAT_ID=...` для рассылок

### 2) Запуск
```bash
cd kbeton_bot_erp_full
docker build -f docker/Dockerfile.base -t kbeton-base:latest .
docker compose up -d --build
```

После старта:
- API: http://localhost:8000/health
- MinIO Console: http://localhost:9001 (логин/пароль из `.env`)

> При `API_AUTH_ENABLED=true` эндпоинты `/pnl`, `/pnl.xlsx`, `/prices/current` требуют токен в `Authorization: Bearer <API_TOKEN>` или `X-API-Key`.

> Миграции выполняются сервисом `migrate` автоматически при старте.

---

## Инициализация пользователей и ролей

### Создать/обновить пользователя
```bash
docker compose run --rm api python scripts/create_user.py --tg-id 123456789 --name "Bakai" --role Admin
```

### Назначить роль
```bash
docker compose run --rm api python scripts/set_role.py --tg-id 123456789 --role FinDir
```

### Seed demo data (опционально)
Создаст статьи, правила, расходники, цены.
```bash
docker compose run --rm api python scripts/seed_demo.py
```

---

## Работа в Telegram

1) Откройте бота → `/start`  
2) Admin/FinDir:
   - 💰 Финансы → 🧩 Неразобранное → назначить статью → (опционально) автосоздать правило contains
   - 💰 Финансы → 📄 P&L → выбрать период (xlsx выгрузка отправляется ботом)
   - 💰 Финансы → 📦 Статус импорта
   - 💰 Финансы → 📐 Правила маппинга (contains/regex + priority)
   - 💰 Финансы → 🏷️ Цены → установить цену марок бетона и блоков
   - 💰 Финансы → 📥 Загрузить взаиморасчеты (контрагенты)

3) Operator:
   - 🏭 Производство → Закрыть смену (пошаговый ввод)

4) HeadProd:
   - 🏭 Производство → Смены на согласование → approve/reject
   - 🏭 Производство → Выпуск/KPI (за последние 7 дней)

5) Warehouse:
   - 📦 Склад → Выдать / Списать / Инвентаризация / Остатки
6) Узнать свой TG ID и ID чата:
   - команда `/id`
7) Помощь и сброс ввода:
   - `/help` — краткая шпаргалка
   - `/cancel` или `отмена` — выйти из текущего ввода
   - `/today`, `/week`, `/month` — быстрый P&L
   - `/audit` — последние изменения (Admin)
8) Контрагенты:
   - 💰 Финансы → Контрагенты/Задолженность (снимки) → введите название для карточки

---

## Импорт XLSX

### Взаиморасчеты (контрагенты)
Команда бота: **📥 Загрузить взаиморасчеты (контрагенты)**  
Снимки сохраняются (snapshot_date = дата импорта), имена нормализуются.

Пример шаблона:
- `samples/counterparty_snapshot_template.xlsx`

---

## Тесты

Локально (вне docker):
```bash
pip install -r requirements.txt
pytest -q
```

В GitHub Actions:
- `.github/workflows/ci.yml` — полный CI прогон
- `.github/workflows/deploy-on-push.yml` — деплой только после успешного test job

---

## Архитектура репозитория

- `apps/api` — FastAPI API
- `apps/bot` — Telegram bot (aiogram 3)
- `apps/worker` — Celery worker/beat задачи
- `kbeton/models` — SQLAlchemy модели
- `kbeton/importers` — парсеры XLSX
- `kbeton/services` — доменная логика (auth/audit/s3/mapping/pricing)
- `kbeton/reports` — P&L и экспорт
- `alembic` — миграции
- `scripts` — администрирование (создание пользователей/ролей/seed)
- `samples` — шаблоны XLSX
- `tests` — unit tests

---

## Команды обслуживания

Открыть psql:
```bash
docker compose exec postgres psql -U kbeton -d kbeton
```

Просмотр логов:
```bash
docker compose logs -f api
docker compose logs -f bot
docker compose logs -f worker
```

## Автодеплой после push в main

Если нужно, чтобы на другом компьютере (локальный сервер) после `git push` автоматически выполнялись `git pull` и `docker compose up -d --build`, используйте workflow:

- `.github/workflows/deploy-on-push.yml`

В GitHub репозитории добавьте Secrets:

- `DEPLOY_HOST` — IP/домен серверного компьютера
- `DEPLOY_USER` — SSH пользователь
- `DEPLOY_PATH` — путь к проекту на сервере (например `/opt/kbeton_bot_erp_full`)
- `DEPLOY_SSH_KEY` — приватный SSH ключ (ed25519), соответствующий публичному ключу в `~/.ssh/authorized_keys` на сервере

Требования на серверном компьютере:

- установлен Docker + Docker Compose
- репозиторий уже склонирован в `DEPLOY_PATH`
- в корне репозитория на сервере уже создан production `.env`
- деплой выполняется через `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- SSH доступ разрешен
