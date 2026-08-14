from aiogram import Dispatcher

from bot.handlers import (
    admin_management,
    admin_moderation,
    appeal_create,
    dialog_relay,
    games,
    main_menu,
    norms,
    onboarding,
    owner_tools,
    profile,
    support_topic,
)


def register_all_routers(dp: Dispatcher) -> None:
    # Порядок важен: у aiogram внутри Dispatcher хендлеры проверяются по очереди
    # регистрации роутеров, и как только один из них "принимает" апдейт — дальше
    # апдейт НЕ идёт. dialog_relay.user_message_to_topic ловит ЛЮБОЕ приватное
    # текстовое сообщение (кроме команд/сообщений от админов) через F.chat.type ==
    # "private" без фильтра по тексту кнопок — то есть это "catch-all" хендлер.
    # Раньше он был зарегистрирован ДО profile/main_menu, поэтому перехватывал
    # нажатия на "Профиль", "Изменить анкету", "Любимые администраторы",
    # "Статистика", "Панель отзывов", "Историю диалогов" и "Администрацию онлайн"
    # раньше, чем до них доходила очередь — если у пользователя не было активного
    # обращения, хендлер молча делал return (appeal is None), и кнопка выглядела
    # "неработающей". "Создать обращение" работала, потому что она обрабатывается
    # в appeal_create, который стоит раньше dialog_relay.
    #
    # Правило на будущее: специфичные хендлеры (с конкретными фильтрами по тексту/
    # команде/состоянию) регистрируются раньше, а catch-all-роутеры вроде
    # dialog_relay — последними.
    dp.include_router(onboarding.router)
    dp.include_router(support_topic.router)
    dp.include_router(admin_management.router)
    dp.include_router(admin_moderation.router)
    dp.include_router(owner_tools.router)
    dp.include_router(games.router)
    dp.include_router(norms.router)
    dp.include_router(appeal_create.router)
    dp.include_router(profile.router)
    dp.include_router(main_menu.router)
    dp.include_router(dialog_relay.router)

