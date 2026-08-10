from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.appeal import (
    CB_ADMIN_PREFIX,
    CB_CANCEL,
    CB_MODE_AI,
    CB_MODE_FASTEST,
    CB_MODE_FAVORITES,
    CB_MODE_NICKNAME,
    admins_list_keyboard,
    choose_mode_keyboard,
)
from bot.keyboards.main_menu import BTN_CREATE_APPEAL, main_menu_keyboard
from bot.services.ai_matching import ai_match_admins
from bot.services.appeals import create_appeal, get_online_admins
from bot.states.appeal import CreateAppealForm
from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import Admin, AppealMode, FavoriteAdmin, User

router = Router(name="appeal_create")


@router.message(F.text == BTN_CREATE_APPEAL)
async def start_create_appeal(message: Message, state: FSMContext, session: AsyncSession) -> None:
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()
    if user and user.active_appeal_id:
        await message.answer(f"{ce(e.WARNING)} У тебя уже есть открытое обращение.")
        return

    # прячем кнопку "Создать обращение" пока идёт создание/пока обращение открыто
    await message.answer(
        f"{ce(e.FIRE)} Как хочешь связаться с администратором?",
        parse_mode="HTML",
        reply_markup=choose_mode_keyboard(),
    )
    await message.answer(
        "Клавиатура скрыта до отмены/закрытия обращения.",
        reply_markup=main_menu_keyboard(has_active_appeal=True),
    )
    await state.set_state(CreateAppealForm.choosing_mode)


@router.callback_query(CreateAppealForm.choosing_mode, F.data == CB_CANCEL)
async def cancel_creation(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(f"{ce(e.CROSS)} Создание обращения отменено.", parse_mode="HTML")
    await callback.message.answer(
        "Главное меню:", reply_markup=main_menu_keyboard(has_active_appeal=False)
    )


@router.callback_query(CreateAppealForm.choosing_mode, F.data == CB_MODE_NICKNAME)
async def mode_nickname(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    result = await session.execute(select(Admin).where(Admin.is_active.is_(True)))
    admins = result.scalars().all()
    items = [(a.telegram_id, a.nickname, a.is_online) for a in admins]
    if not items:
        await callback.answer("Пока нет администраторов в системе", show_alert=True)
        return
    await state.update_data(mode=AppealMode.BY_NICKNAME.value)
    await state.set_state(CreateAppealForm.choosing_admin_by_nickname)
    await callback.message.edit_text(
        f"{ce(e.SEARCH)} Выбери администратора (онлайн подсвечены зелёным):",
        parse_mode="HTML",
        reply_markup=admins_list_keyboard(items),
    )


@router.callback_query(CreateAppealForm.choosing_admin_by_nickname, F.data.startswith(CB_ADMIN_PREFIX))
async def pick_admin_by_nickname(callback: CallbackQuery, state: FSMContext) -> None:
    admin_id = int(callback.data.split(":")[-1])
    await state.update_data(invited_admin_ids=[admin_id])
    await state.set_state(CreateAppealForm.typing_message)
    await callback.message.edit_text(
        f"{ce(e.CHAT)} Опиши свой вопрос одним сообщением (можно с фото/видео/голосовым)."
    )


@router.callback_query(CreateAppealForm.choosing_mode, F.data == CB_MODE_FAVORITES)
async def mode_favorites(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    result = await session.execute(
        select(FavoriteAdmin.admin_id).where(FavoriteAdmin.user_id == callback.from_user.id)
    )
    ids = [row[0] for row in result.all()]
    if not ids:
        await callback.answer("У тебя пока нет избранных администраторов", show_alert=True)
        return
    await state.update_data(mode=AppealMode.FAVORITES.value, invited_admin_ids=ids)
    await state.set_state(CreateAppealForm.typing_message)
    await callback.message.edit_text(
        f"{ce(e.STAR)} Будут вызваны твои любимые администраторы. Опиши свой вопрос одним сообщением."
    )


@router.callback_query(CreateAppealForm.choosing_mode, F.data == CB_MODE_FASTEST)
async def mode_fastest(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    result = await session.execute(select(Admin).where(Admin.is_active.is_(True)))
    ids = [a.telegram_id for a in result.scalars().all()]
    await state.update_data(mode=AppealMode.FASTEST.value, invited_admin_ids=ids)
    await state.set_state(CreateAppealForm.typing_message)
    await callback.message.edit_text(
        f"{ce(e.ZAP)} Обращение увидят все администраторы, ответит тот, кто примет первым. "
        f"Опиши свой вопрос одним сообщением."
    )


@router.callback_query(CreateAppealForm.choosing_mode, F.data == CB_MODE_AI)
async def mode_ai(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one()
    admins_res = await session.execute(select(Admin).where(Admin.is_active.is_(True)))
    admins = admins_res.scalars().all()
    if not admins:
        await callback.answer("Пока нет администраторов в системе", show_alert=True)
        return

    await callback.answer(f"{ce(e.SPARKLES)} Подбираем...", show_alert=False)
    ids, reason = await ai_match_admins(user, admins)

    await state.update_data(mode=AppealMode.AI_MATCH.value, invited_admin_ids=ids)
    await state.set_state(CreateAppealForm.typing_message)
    await callback.message.edit_text(
        f"{ce(e.SPARKLES)} ИИ подобрал администраторов для тебя.\n"
        f"<i>{reason}</i>\n\n"
        f"Опиши свой вопрос одним сообщением.",
        parse_mode="HTML",
    )


@router.message(CreateAppealForm.typing_message)
async def submit_appeal(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    mode = AppealMode(data["mode"])
    invited_admin_ids = data.get("invited_admin_ids", [])

    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one()

    first_text = message.text or message.caption or "(медиа без подписи)"
    appeal = await create_appeal(session, message.bot, user, mode, invited_admin_ids, first_text)

    # если в первом сообщении было медиа — пересылаем его в общий топик отдельно
    if message.content_type != "text":
        from bot.config import settings

        await message.copy_to(settings.support_group_id, message_thread_id=settings.support_topic_id)

    await state.clear()
    await message.answer(
        f"{ce(e.CHECK)} Обращение №{appeal.id} создано и отправлено администраторам. "
        f"Как только кто-то из них ответит — сообщение придёт сюда же.",
        parse_mode="HTML",
    )
