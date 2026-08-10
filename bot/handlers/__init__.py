from aiogram import Dispatcher

from bot.handlers import (
    admin_management,
    admin_moderation,
    appeal_create,
    dialog_relay,
    main_menu,
    onboarding,
    profile,
    support_topic,
)


def register_all_routers(dp: Dispatcher) -> None:
    # порядок важен: онбординг должен успевать перехватывать состояния FSM раньше общих хендлеров
    dp.include_router(onboarding.router)
    dp.include_router(support_topic.router)
    dp.include_router(admin_management.router)
    dp.include_router(admin_moderation.router)
    dp.include_router(appeal_create.router)
    dp.include_router(dialog_relay.router)
    dp.include_router(profile.router)
    dp.include_router(main_menu.router)
