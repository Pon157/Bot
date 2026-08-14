from __future__ import annotations

import json
import logging
import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.types import InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.services import games as games_service
from bot.services.relay import get_active_appeal_by_topic, get_active_appeal_by_user
from bot.services.seabattle import BOARD_SIZE
from bot.states.appeal import CreateAppealForm
from bot.utils import emoji as e
from bot.utils.buttons import inline_btn
from bot.utils.emoji import ce
from db.models import Admin, SeaBattleGame, TicTacToeGame

router = Router(name="games")
logger = logging.getLogger(__name__)

# Если пользователь как раз печатает текст обращения (CreateAppealForm.typing_message),
# команды игр не должны его перехватывать — мало ли текст обращения начинается с
# "/hangman" или похоже на "/ttt3x3". Используем как доп. фильтр на приватных
# хендлерах игр ниже.
_NOT_TYPING_APPEAL = ~StateFilter(CreateAppealForm.typing_message)


def _only_support_group(message: Message) -> bool:
    return message.chat.id == settings.support_group_id


# ───────────────────── /hangman, /guessnumber, /stopgame ─────────────────────
# Простые словесные игры — работают прямо в диалоге: сообщение приходит и в
# топик, и в личку пользователю (см. bot/services/games.py). Играть могут обе
# стороны, присылая буквы/числа обычными сообщениями — dialog_relay.py
# перехватывает такие сообщения ДО обычной пересылки, пока игра активна.

@router.message(Command("hangman"), F.message_thread_id.is_not(None))
async def cmd_hangman(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _only_support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Это не топик активного обращения.")
        return
    await _start_hangman(message, appeal, started_by=db_admin.telegram_id)


@router.message(Command("hangman"), F.chat.type == "private", _NOT_TYPING_APPEAL)
async def cmd_hangman_user(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is not None:
        return
    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Игру можно начать только внутри активного диалога с администратором.")
        return
    await _start_hangman(message, appeal, started_by=message.from_user.id)


async def _start_hangman(message: Message, appeal, started_by: int) -> None:
    if games_service.has_active_game(appeal.id):
        await message.reply(f"{ce(e.WARNING)} В этом диалоге уже идёт игра. Останови её — /stopgame")
        return

    command_text = (message.text or "").split(maxsplit=1)
    custom_word = command_text[1].strip() if len(command_text) > 1 else None
    if custom_word and not re.fullmatch(r"[а-яёА-ЯЁa-zA-Z]{2,20}", custom_word):
        await message.reply(f"{ce(e.WARNING)} Слово должно состоять из 2-20 букв без пробелов и цифр.")
        return

    game = games_service.start_hangman(appeal.id, started_by, custom_word)
    await games_service.broadcast_to_dialog(message.bot, appeal, games_service.render_hangman(game))


@router.message(Command("guessnumber"), F.message_thread_id.is_not(None))
async def cmd_guess_number(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _only_support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Это не топик активного обращения.")
        return
    await _start_guess_number(message, appeal, started_by=db_admin.telegram_id)


@router.message(Command("guessnumber"), F.chat.type == "private", _NOT_TYPING_APPEAL)
async def cmd_guess_number_user(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is not None:
        return
    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Игру можно начать только внутри активного диалога с администратором.")
        return
    await _start_guess_number(message, appeal, started_by=message.from_user.id)


async def _start_guess_number(message: Message, appeal, started_by: int) -> None:
    if games_service.has_active_game(appeal.id):
        await message.reply(f"{ce(e.WARNING)} В этом диалоге уже идёт игра. Останови её — /stopgame")
        return

    command_text = (message.text or "").split(maxsplit=1)
    max_value = 100
    if len(command_text) > 1 and command_text[1].strip().isdigit():
        max_value = max(10, min(10000, int(command_text[1].strip())))

    game = games_service.start_guess_number(appeal.id, started_by, max_value)
    await games_service.broadcast_to_dialog(
        message.bot, appeal,
        f"{ce(e.GAME)} <b>Угадай число</b>\n\nЯ загадал число от {game.min_value} до {game.max_value}. Присылай варианты!\n"
        f"Остановить игру — /stopgame",
    )


@router.message(Command("stopgame"), F.message_thread_id.is_not(None))
async def cmd_stop_game(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _only_support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        return
    await _stop_game(message, appeal)


@router.message(Command("stopgame"), F.chat.type == "private", _NOT_TYPING_APPEAL)
async def cmd_stop_game_user(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is not None:
        return
    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        return
    await _stop_game(message, appeal)


async def _stop_game(message: Message, appeal) -> None:
    if games_service.stop_game(appeal.id):
        await games_service.broadcast_to_dialog(message.bot, appeal, f"{ce(e.CROSS)} Игра остановлена.")
    else:
        await message.reply(f"{ce(e.INFO)} Сейчас нет активной игры.")


# ───────────────────── /ttt3x3 .. /ttt10x10 ─────────────────────
# Крестики-нолики удобнее в виде мини-аппы, но ссылки на веб-аппы некорректно
# открываются, если прислать их прямо в группу/топик — поэтому ссылки на игру
# отправляются личным сообщением от бота: и админу, который её начал, и
# пользователю (у него уже есть личка с ботом). В топик уходит только
# короткое текстовое уведомление, что игра создана.

@router.message(Command("gamestats"))
async def cmd_gamestats(message: Message) -> None:
    if not settings.gamestats_webapp_url or not settings.gamestats_webapp_url.startswith("https://"):
        await message.reply(f"{ce(e.WARNING)} Не настроен GAMESTATS_WEBAPP_URL в .env.")
        return
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[inline_btn("Открыть", emo=e.CHART, web_app=WebAppInfo(url=settings.gamestats_webapp_url), style="primary")]]
    )
    await message.answer(f"{ce(e.GAME)} Статистика побед в играх:", reply_markup=markup)


TTT_MIN_SIZE = 3
TTT_MAX_SIZE = 10


async def _create_ttt_game(message: Message, session: AsyncSession, appeal, n: int, m: int, x_id: int, o_id: int) -> None:
    if n != m or not (TTT_MIN_SIZE <= n <= TTT_MAX_SIZE):
        await message.reply(
            f"{ce(e.WARNING)} Поле должно быть квадратным, от {TTT_MIN_SIZE}x{TTT_MIN_SIZE} до "
            f"{TTT_MAX_SIZE}x{TTT_MAX_SIZE}, например /ttt3x3 или /ttt10x10."
        )
        return

    if not settings.ttt_webapp_url or not settings.ttt_webapp_url.startswith("https://"):
        # Раньше это молча приводило к тому, что Telegram отвергал сообщение
        # с некорректной (пустой/относительной) web_app-ссылкой, а ошибка
        # тихо проглатывалась — выглядело как "ссылка вообще никому не
        # пришла", хотя оба участника реально писали боту. Теперь говорим
        # прямо, в чём дело, вместо неопределённого "не удалось отправить".
        await message.reply(
            f"{ce(e.WARNING)} Не настроен TTT_WEBAPP_URL в .env (должен начинаться с https://) — "
            "без него Telegram не принимает кнопку мини-аппы. Игра не создана."
        )
        return

    win_length = n if n <= 3 else 4  # для больших полей 4 в ряд, иначе игра почти не заканчивается
    board = [0] * (n * n)
    game = TicTacToeGame(
        appeal_id=appeal.id,
        board_size=n,
        win_length=win_length,
        board=json.dumps(board),
        turn=1,
        player_x_id=x_id,
        player_o_id=o_id,
        status="active",
    )
    session.add(game)
    await session.commit()

    url = settings.ttt_webapp_url.rstrip("/") + f"/?game_id={game.id}"
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[inline_btn("Играть", emo=e.PLAY, web_app=WebAppInfo(url=url), style="primary")]]
    )

    failed_for: list[int] = []
    for uid, role in ((x_id, "✕"), (o_id, "○")):
        try:
            await message.bot.send_message(
                uid,
                f"{ce(e.GAME)} Игра «Крестики-нолики {n}x{n}» создана (обращение №{appeal.id}). Ты играешь за {role}.",
                reply_markup=markup,
            )
        except Exception:
            logger.exception("games: не удалось отправить приглашение в TTT пользователю %s", uid)
            failed_for.append(uid)

    note = (
        f"{ce(e.CHECK)} Игра «Крестики-нолики {n}x{n}» создана. Ссылки на игру отправлены в личку "
        f"обоим участникам (в топике/группе кнопка мини-аппы работает некорректно)."
    )
    if failed_for:
        note += (
            f"\n{ce(e.WARNING)} Не удалось отправить ссылку: {', '.join(str(u) for u in failed_for)} "
            "— смотри полный текст ошибки в логах tg-bot (вероятные причины: пользователь ни разу "
            "не писал боту в личку, либо заблокировал бота)."
        )
    await message.reply(note, parse_mode="HTML")


@router.message(F.text.regexp(r"^/ttt(\d{1,2})x(\d{1,2})(?:@\w+)?(?:\s|$)"), F.message_thread_id.is_not(None))
async def cmd_ttt_admin(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _only_support_group(message) or db_admin is None:
        return
    match = re.match(r"^/ttt(\d{1,2})x(\d{1,2})", message.text)
    n, m = int(match.group(1)), int(match.group(2))

    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Это не топик активного обращения.")
        return

    await _create_ttt_game(message, session, appeal, n, m, x_id=db_admin.telegram_id, o_id=appeal.user_id)


@router.message(F.text.regexp(r"^/ttt(\d{1,2})x(\d{1,2})(?:@\w+)?(?:\s|$)"), F.chat.type == "private", _NOT_TYPING_APPEAL)
async def cmd_ttt_user(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is not None:
        return  # админы играют из топика, не из своей личной переписки с ботом
    match = re.match(r"^/ttt(\d{1,2})x(\d{1,2})", message.text)
    n, m = int(match.group(1)), int(match.group(2))

    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Игру можно начать только внутри активного диалога с администратором.")
        return

    # в диалоге пользователь всегда играет за ○, админ — за ✕ (см. _create_ttt_game)
    await _create_ttt_game(message, session, appeal, n, m, x_id=appeal.primary_admin_id, o_id=appeal.user_id)


# ───────────────────── /seabattle ─────────────────────
# Морской бой 10x10, классический флот. Как и в крестиках-ноликах, играется
# через мини-аппу, ссылки уходят личным сообщением обоим участникам (в
# группе/топике web_app-кнопки открываются некорректно). Расстановка
# кораблей — РУЧНАЯ: оба игрока расставляют флот сами в мини-аппе и жмут
# "Готов" (сервер проверяет, что состав флота и отсутствие соприкосновений
# соблюдены — см. bot/services/seabattle.py:validate_manual_board), бой
# начинается, когда готовы оба.

async def _create_seabattle_game(message: Message, session: AsyncSession, appeal, p1_id: int, p2_id: int) -> None:
    if not settings.battleship_webapp_url or not settings.battleship_webapp_url.startswith("https://"):
        await message.reply(
            f"{ce(e.WARNING)} Не настроен BATTLESHIP_WEBAPP_URL в .env (должен начинаться с https://). Игра не создана."
        )
        return

    empty_board = [0] * (BOARD_SIZE * BOARD_SIZE)
    game = SeaBattleGame(
        appeal_id=appeal.id,
        board1=json.dumps(empty_board),
        board2=json.dumps(empty_board),
        turn=1,
        player1_id=p1_id,
        player2_id=p2_id,
        status="placing",
    )
    session.add(game)
    await session.commit()

    url = settings.battleship_webapp_url.rstrip("/") + f"/?game_id={game.id}"
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[inline_btn("Играть", emo=e.PLAY, web_app=WebAppInfo(url=url), style="primary")]]
    )

    failed_for: list[int] = []
    for uid in (p1_id, p2_id):
        try:
            await message.bot.send_message(
                uid,
                f"{ce(e.GAME)} Игра «Морской бой» создана (обращение №{appeal.id}). Расставь свой флот и жми «Готов»!",
                reply_markup=markup,
            )
        except Exception:
            logger.exception("games: не удалось отправить приглашение в Морской бой пользователю %s", uid)
            failed_for.append(uid)

    note = (
        f"{ce(e.CHECK)} Игра «Морской бой» создана. Ссылки отправлены в личку обоим участникам "
        f"(в топике/группе кнопка мини-аппы работает некорректно)."
    )
    if failed_for:
        note += (
            f"\n{ce(e.WARNING)} Не удалось отправить ссылку: {', '.join(str(u) for u in failed_for)} "
            "— смотри логи tg-bot (вероятно, не писал(и) боту в личку или заблокировал(и) бота)."
        )
    await message.reply(note, parse_mode="HTML")


@router.message(Command("seabattle"), F.message_thread_id.is_not(None))
async def cmd_seabattle_admin(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _only_support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Это не топик активного обращения.")
        return
    await _create_seabattle_game(message, session, appeal, p1_id=db_admin.telegram_id, p2_id=appeal.user_id)


@router.message(Command("seabattle"), F.chat.type == "private", _NOT_TYPING_APPEAL)
async def cmd_seabattle_user(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is not None:
        return
    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Игру можно начать только внутри активного диалога с администратором.")
        return
    await _create_seabattle_game(message, session, appeal, p1_id=appeal.primary_admin_id, p2_id=appeal.user_id)
