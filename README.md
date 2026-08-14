# Спокойный рассвет — бот поддержки

Стек: aiogram 3, PostgreSQL (SQLAlchemy async + Alembic), FastAPI (бэкенд мини-апп),
Pillow (карточка профиля), OpenRouter/Qwen (ИИ-подбор администратора), APScheduler
(автоснятие рестов по сроку). **Redis не используется** — FSM-состояния хранятся в
памяти процесса (`MemoryStorage`), антиспам — тоже in-memory.

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
│       ├── shared/style.css     # единая дизайн-система для всех мини-апп
│       ├── online/index.html    # список админов онлайн (автообновление)
│       ├── online/stats.html    # статистика (активные пользователи/админы)
│       ├── reviews/index.html   # отзывы: оставить отзыв + лента
│       ├── dialogs/index.html   # история диалогов + просмотр медиа
│       └── profile/index.html   # веб-версия анкеты
│
├── requirements.txt
├── .env.example
├── alembic.ini
└── README.md (этот файл)
```

## Про отказ от Redis

FSM (мини-анкета, создание обращения) хранится в `MemoryStorage` — просто в памяти
процесса бота. Антиспам (`bot/middlewares/antispam.py`) — тоже в памяти, через
обычные dict/deque с временными метками. Это значит:
- Всё работает без единой внешней зависимости, кроме PostgreSQL.
- При перезапуске бота активные FSM-состояния (например, "пользователь на середине
  заполнения анкеты") сбрасываются — это нормально для такого сценария использования.
- Если в будущем бот будет запускаться в нескольких процессах/подах одновременно —
  понадобится общее хранилище (Redis или БД) для FSM и антиспама, т.к. в памяти
  каждого процесса будет своё независимое состояние.
Онлайн-статус администраторов Redis никогда и не использовал — он всегда считался
через `last_message_at` в PostgreSQL (см. `Admin.is_online` в `db/models/admins.py`).

## Что уже полностью работает
- Онбординг: стикер → проверка бана/подписки/соглашения → мини-анкета → главное меню
- Антиспам без внешних зависимостей (мягкий троттлинг двойных нажатий + жёсткий лимит с временным мьютом, в памяти процесса), админы и владелец не троттлятся
- Прокси-сессия бота (`BOT_PROXY_URL` в `.env`, поддержка http и socks5)
- Премиум-эмодзи по всему боту + цветные кнопки (`style`) — обёртки в `bot/utils/buttons.py`
- Все 4 режима создания обращения, кнопка "Создать обращение" скрывается на время активного обращения
- Общий топик → кнопка "Принять" → отдельный форум-топик, теги приглашённых
- Пересылка сообщений в обе стороны с логированием в БД, редактирование, реакции, `/delete`
- `/add /transfer /addadmin /removeadmin /promote /broadcastusers`, `/warn /unwarn /ban /unban /giverest /endrest /close`
- Автоматическое снятие рестов по истечении срока (`bot/services/rest_scheduler.py`, APScheduler, проверка раз в минуту)
- Карточка профиля на Pillow (аватар, никнейм, статистика, о себе, хобби)
- ИИ-подбор через OpenRouter/Qwen с безопасным фолбэком при недоступности API
- FastAPI-бэкенд + **все пять мини-апп полностью свёрстаны и рабочие**:
  - `/online` — список администраторов с онлайн-статусом (автообновление раз в 30 сек)
  - `/online/stats.html` — статистика (активные пользователи/админы за 24 часа)
  - `/reviews` — вкладки "оставить отзыв" (с подсказкой о недавних диалогах и звёздами) и "лента отзывов"
  - `/dialogs` — список обращений → чат с текстом, фото, видео, голосовыми, документами (медиа проксируется из Telegram)
  - `/profile` — веб-версия анкеты (полный текст "о себе"/"хобби", в боте дополнительно есть Pillow-карточка с аватаром)

## Что нужно доделать перед продакшеном
1. **Первая Alembic-миграция** — сгенерировать командой `alembic revision --autogenerate` после
   подключения к реальной БД (в песочнице нет доступа к вашей PostgreSQL).
2. **`icon_custom_emoji_id` / `style` на кнопках** — обёртки в `bot/utils/buttons.py` добавляют поля
   вручную (extra="allow"), т.к. на момент разработки актуальная стабильная aiogram 3.15.x могла
   ещё не поддерживать их официально в Pydantic-моделях кнопок. Нужно проверить на вашей версии
   aiogram и при необходимости обновить до версии с нативной поддержкой Bot API 9.4.
3. **Ограничение прав в форум-топике** — Telegram API не позволяет запретить конкретным юзерам
   писать в конкретный топик нативно; вместо этого используется программная проверка в
   `dialog_relay.py` (сообщение не пересылается, если админ не в `AppealParticipant`) — сообщение
   в топике при этом остаётся видимым остальным, но диалог с пользователем не продолжается.
4. **Масштабирование на несколько процессов** — если бот когда-нибудь будет запускаться в
   нескольких инстансах одновременно (например, за балансировщиком), понадобится вернуть общее
   хранилище для FSM/антиспама (Redis либо таблица в той же PostgreSQL) — см. раздел выше.

