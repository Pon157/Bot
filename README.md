# Спокойный рассвет — бот поддержки

Стек: aiogram 3, PostgreSQL (SQLAlchemy async + Alembic), Redis (FSM + антиспам + онлайн),
FastAPI (бэкенд мини-апп), Pillow (карточка профиля), OpenRouter/Qwen (ИИ-подбор администратора).

## Быстрый старт

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # заполнить BOT_TOKEN, OWNER_ID, DATABASE_URL, SUPPORT_GROUP_ID и т.д.

# первая миграция (после заполнения .env)
alembic revision --autogenerate -m "init"
alembic upgrade head

# сам бот
python -m bot.main

# бэкенд мини-апп (отдельным процессом)
uvicorn miniapps.backend.app:app --host 0.0.0.0 --port 8080
```

Группа обращений должна быть форум-группой (Topics включены), бот — админом в ней
с правами `can_manage_topics`, `can_delete_messages`. `SUPPORT_TOPIC_ID` — id топика,
куда падают новые обращения до принятия (можно создать топик "Обращения" и указать его id).

## Структура проекта

```
spokoyny_rassvet/
├── bot/
│   ├── main.py                  # точка входа, прокси-сессия, регистрация мидлварей
│   ├── config.py                # pydantic-settings, чтение .env
│   ├── handlers/
│   │   ├── __init__.py          # register_all_routers
│   │   ├── onboarding.py        # /start, стикер, мини-анкета
│   │   ├── main_menu.py         # статистика/отзывы/онлайн/история — кнопки-ссылки на мини-аппы
│   │   ├── profile.py           # карточка профиля, изменить анкету, любимые админы
│   │   ├── appeal_create.py     # создание обращения — все 4 режима
│   │   ├── support_topic.py     # кнопка "Принять" в общем топике
│   │   ├── dialog_relay.py      # пересылка сообщений/реакций/редактирования user<->topic
│   │   ├── admin_management.py  # /add /transfer /addadmin /removeadmin /promote /broadcastusers, овнер-панель
│   │   └── admin_moderation.py  # /warn /unwarn /ban /unban /giverest /endrest /close /delete
│   ├── middlewares/
│   │   ├── db_session.py        # sqlalchemy-сессия в data
│   │   ├── admin_context.py     # is_admin/db_admin в data
│   │   ├── ban.py                # блокировка забаненных
│   │   ├── antispam.py          # троттлинг на Redis (мягкий + жёсткий лимиты)
│   │   ├── subscription.py      # обязательная подписка на каналы из ENV
│   │   └── agreement.py         # пользовательское соглашение
│   ├── keyboards/
│   │   ├── main_menu.py         # reply-клавиатура главного меню
│   │   ├── links.py             # инлайн-ссылки на ресурсы
│   │   ├── appeal.py            # выбор режима/админа при создании обращения
│   │   └── support_topic.py     # кнопка "Принять"
│   ├── states/
│   │   ├── onboarding.py        # FSM мини-анкеты
│   │   └── appeal.py            # FSM создания обращения
│   ├── services/
│   │   ├── appeals.py           # создание/принятие/закрытие обращений
│   │   ├── relay.py             # пересылка сообщений, поиск зеркал
│   │   ├── ai_matching.py       # ИИ-подбор администратора через OpenRouter (Qwen)
│   │   └── profile_card.py      # генерация PNG-карточки профиля (Pillow)
│   └── utils/
│       ├── emoji.py             # реестр премиум-эмодзи + рендер под HTML/tg-emoji
│       ├── buttons.py           # обёртки кнопок с icon_custom_emoji_id и style (Bot API 9.4)
│       └── permissions.py       # проверки ролей (owner/head_admin)
│
├── db/
│   ├── base.py                  # Base, engine, sessionmaker
│   ├── models/
│   │   ├── users.py             # User, FavoriteAdmin, Warn
│   │   ├── admins.py            # Admin, AdminRest, AdminRole
│   │   ├── appeals.py           # Appeal, AppealParticipant, AppealMessage
│   │   └── reviews.py           # Review
│   └── migrations/              # Alembic (env.py настроен на settings.database_url)
│
├── miniapps/backend/
│   ├── app.py                   # FastAPI-приложение, монтирует static + роутеры
│   ├── auth.py                  # проверка подписи Telegram WebApp initData
│   ├── db.py                    # сессия БД для FastAPI
│   ├── routers/
│   │   ├── reviews.py           # недавние собеседники + создание/лента отзывов
│   │   ├── online.py            # список админов с онлайн-статусом
│   │   ├── dialogs.py           # история диалогов + проксирование медиа из Telegram
│   │   ├── stats.py             # активные пользователи/админы
│   │   └── profile.py           # данные анкеты для мини-аппы профиля
│   └── static/
│       ├── online/index.html    # готовый пример мини-аппы (задаёт стиль остальным)
│       ├── reviews/             # заготовка под фронтенд отзывов
│       ├── dialogs/             # заготовка под фронтенд истории диалогов
│       └── profile/             # заготовка под фронтенд профиля
│
├── requirements.txt
├── .env.example
├── alembic.ini
└── README.md (этот файл)
```

## Что уже полностью работает
- Онбординг: стикер → проверка бана/подписки/соглашения → мини-анкета → главное меню
- Антиспам на Redis (мягкий троттлинг двойных нажатий + жёсткий лимит с временным мьютом), админы и владелец не троттлятся
- Прокси-сессия бота (`BOT_PROXY_URL` в `.env`, поддержка http и socks5)
- Премиум-эмодзи по всему боту + цветные кнопки (`style`) — обёртки в `bot/utils/buttons.py`
- Все 4 режима создания обращения, кнопка "Создать обращение" скрывается на время активного обращения
- Общий топик → кнопка "Принять" → отдельный форум-топик, теги приглашённых
- Пересылка сообщений в обе стороны с логированием в БД, редактирование, реакции, `/delete`
- `/add /transfer /addadmin /removeadmin /promote /broadcastusers`, `/warn /unwarn /ban /unban /giverest /endrest /close`
- Карточка профиля на Pillow (аватар, никнейм, статистика, о себе, хобби)
- ИИ-подбор через OpenRouter/Qwen с безопасным фолбэком при недоступности API
- FastAPI-бэкенд мини-апп: отзывы, онлайн, история диалогов (с проксированием медиа), статистика

## Что нужно доделать перед продакшеном
1. **Фронтенды мини-апп "Отзывы", "История диалогов", "Профиль", "Статистика"** — сделан только
   `online/index.html` как образец стиля. Остальные страницы нужно сверстать аналогично
   (дизайн-система уже задана в CSS-переменных примера).
2. **Первая Alembic-миграция** — сгенерировать командой `alembic revision --autogenerate` после
   подключения к реальной БД (в песочнице нет доступа к вашей PostgreSQL).
3. **Периодическая проверка ONLINE_TIMEOUT / рестов по сроку** — сейчас `is_online` считается на
   лету по `last_message_at`, а `AdminRest.until` не снимается автоматически — стоит добавить
   APScheduler-джобу, которая раз в минуту возвращает `is_active=True` админам с истёкшим рестом.
4. **`icon_custom_emoji_id` / `style` на кнопках** — обёртки в `bot/utils/buttons.py` добавляют поля
   вручную (extra="allow"), т.к. на момент разработки актуальная стабильная aiogram 3.15.x могла
   ещё не поддерживать их официально в Pydantic-моделях кнопок. Нужно проверить на вашей версии
   aiogram и при необходимости обновить до версии с нативной поддержкой Bot API 9.4.
5. **Загрузка фото пользователя в аватар мини-аппы профиля** — сейчас аватар рисуется только в
   Pillow-карточке (в боте), в веб-версии профиля (`/profile`) можно добавить отдельно.
6. **Ограничение прав в форум-топике** — Telegram API не позволяет запретить конкретным юзерам
   писать в конкретный топик нативно; вместо этого используется программная проверка в
   `dialog_relay.py` (сообщение не пересылается, если админ не в `AppealParticipant`) — сообщение
   в топике при этом остаётся видимым остальным, но диалог с пользователем не продолжается.
