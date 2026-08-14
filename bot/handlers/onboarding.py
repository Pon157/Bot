from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards.links import resources_keyboard
from bot.keyboards.main_menu import main_menu_keyboard, welcome_text
from bot.middlewares.agreement import CB_ACCEPT_AGREEMENT
from bot.middlewares.subscription import CB_CHECK_SUBSCRIPTION
from bot.states.onboarding import QuestionnaireForm
from bot.utils import emoji as e
from bot.utils.emoji import ce
from bot.utils.media import send_text_or_photo
from db.models import User

router = Router(name="onboarding")

START_STICKER = "CAACAgEAAxkBAAEGFF5qedhCeMNOeBc-LAjeCh-La11IjQAC6gIAAkzs4Ed1zNDPilb6bT0E"


async def get_or_create_user(session: AsyncSession, message: Message) -> tuple[User, bool]:
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()
    is_new = False
    if user is None:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        session.add(user)
        await session.commit()
        is_new = True
    if user.is_blocked:
        # пользователь написал боту снова — значит разблокировал его
        user.is_blocked = False
        user.blocked_at = None
        await session.commit()
    return user, is_new


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await message.answer_sticker(START_STICKER)

    user, is_new = await get_or_create_user(session, message)

    # порядок важен: подписка и соглашение уже проверены мидлварями к этому моменту,
    # остаётся проверить анкету
    if not user.questionnaire_completed:
        await start_questionnaire(message, state)
        return

    await show_main_menu(message, user)


@router.callback_query(F.data == CB_CHECK_SUBSCRIPTION)
async def cb_check_subscription(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    # SubscriptionMiddleware пропускает это событие без проверки, поэтому проверяем здесь руками через хендлер /start
    await callback.answer(f"{ce(e.CHECK)} Проверяем...", show_alert=False)
    await callback.message.delete()
    fake_message = callback.message
    user, _ = await get_or_create_user(session, callback.message)
    if not user.questionnaire_completed:
        await start_questionnaire(callback.message, state, chat_override=callback.from_user.id)
    else:
        await show_main_menu(callback.message, user, chat_override=callback.from_user.id)


@router.callback_query(F.data == CB_ACCEPT_AGREEMENT)
async def cb_accept_agreement(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    from datetime import datetime, timezone

    result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )
        session.add(user)

    user.agreement_accepted_at = datetime.now(timezone.utc)
    await session.commit()

    await callback.answer(f"{ce(e.CHECK)} Соглашение принято", show_alert=False)
    await callback.message.delete()

    if not user.questionnaire_completed:
        await start_questionnaire(callback.message, state, chat_override=callback.from_user.id)
    else:
        await show_main_menu(callback.message, user, chat_override=callback.from_user.id)


# ---------------------------- мини-анкета ----------------------------

async def start_questionnaire(message: Message, state: FSMContext, chat_override: int | None = None) -> None:
    await state.set_state(QuestionnaireForm.nickname)
    text = (
        f"{ce(e.PENCIL)} Давай немного познакомимся.\n\n"
        f"Как тебя называть? Напиши псевдоним, который будет видеть администратор "
        f"(это не обязательно твоё настоящее имя)."
    )
    chat_id = chat_override or message.chat.id
    await send_text_or_photo(
        message.bot, chat_id, text, photo_url=settings.questionnaire_nickname_photo_url
    )


@router.message(QuestionnaireForm.nickname, F.text)
async def q_nickname(message: Message, state: FSMContext) -> None:
    nickname = message.text.strip()
    if len(nickname) < 2 or len(nickname) > 64:
        await message.answer(f"{ce(e.WARNING)} Псевдоним должен быть от 2 до 64 символов. Попробуй ещё раз.")
        return
    await state.update_data(nickname=nickname)
    await state.set_state(QuestionnaireForm.about)
    await send_text_or_photo(
        message.bot,
        message.chat.id,
        f"{ce(e.CHAT)} Приятно познакомиться, <b>{nickname}</b>!\n\n"
        f"Теперь расскажи немного о себе — чем больше текста, тем лучше администратор "
        f"сможет тебя понять и подобрать подходящего собеседника.",
        photo_url=settings.questionnaire_about_photo_url,
    )


@router.message(QuestionnaireForm.about, F.text)
async def q_about(message: Message, state: FSMContext) -> None:
    if len(message.text.strip()) < 10:
        await message.answer(f"{ce(e.WARNING)} Напиши чуть подробнее, хотя бы пару предложений.")
        return
    await state.update_data(about=message.text.strip())
    await state.set_state(QuestionnaireForm.hobbies)
    await send_text_or_photo(
        message.bot,
        message.chat.id,
        f"{ce(e.SPARKLES)} И последнее — расскажи о своих хобби и интересах. "
        f"Это тоже поможет подобрать администратора, с которым будет о чём поговорить.",
        photo_url=settings.questionnaire_hobbies_photo_url,
    )


@router.message(QuestionnaireForm.hobbies, F.text)
async def q_hobbies(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if len(message.text.strip()) < 5:
        await message.answer(f"{ce(e.WARNING)} Напиши чуть подробнее.")
        return

    data = await state.get_data()
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one()
    user.nickname = data["nickname"]
    user.about = data["about"]
    user.hobbies = message.text.strip()
    user.questionnaire_completed = True
    await session.commit()

    await state.clear()
    await message.answer(f"{ce(e.CHECK)} Анкета сохранена, спасибо!")
    await show_main_menu(message, user)


# ---------------------------- главное меню ----------------------------

async def show_main_menu(message: Message, user: User, chat_override: int | None = None) -> None:
    chat_id = chat_override or message.chat.id
    await send_text_or_photo(
        message.bot,
        chat_id,
        welcome_text(),
        photo_url=settings.start_photo_url,
        reply_markup=resources_keyboard(),
    )
    await message.bot.send_message(
        chat_id,
        f"{ce(e.HOUSE)} Главное меню:",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(has_active_appeal=user.active_appeal_id is not None),
    )

