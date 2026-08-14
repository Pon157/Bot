from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import GameResult

# ─────────────────────────────────────────────────────────────────────────
# Простые словесные игры, которые можно запускать прямо в диалоге (топик
# админов <-> личка пользователя). Состояние — в памяти процесса бота, по
# одному активному "текстовому" мини-геймру на обращение: этого достаточно
# для лёгких игр и не тянет за собой отдельные таблицы/миграции. Если
# процесс бота перезапустится посреди игры — она просто потеряется, что
# приемлемо для казуального развлечения в чате.
# ─────────────────────────────────────────────────────────────────────────

HANGMAN_WORDS = [
    "ракета", "гитара", "облако", "вокзал", "тетрадь", "яблоко", "верблюд",
    "фонарь", "зеркало", "кофейня", "дельфин", "снежинка", "автобус",
    "чемодан", "радуга", "пингвин", "костёр", "паровоз", "будильник",
    "варенье", "футболка", "клавиша", "торнадо", "жираф", "мельница",
]
HANGMAN_MAX_WRONG = 6


@dataclass
class HangmanGame:
    word: str
    started_by: int
    is_custom: bool  # True — слово задал человек вручную, False — выбрано системой случайно
    guessed: set[str] = field(default_factory=set)
    wrong: int = 0

    def masked(self) -> str:
        return " ".join(letter if letter in self.guessed else "▢" for letter in self.word)

    @property
    def is_won(self) -> bool:
        return all(letter in self.guessed for letter in self.word)

    @property
    def is_lost(self) -> bool:
        return self.wrong >= HANGMAN_MAX_WRONG


@dataclass
class GuessNumberGame:
    secret: int
    started_by: int
    min_value: int = 1
    max_value: int = 100
    attempts: int = 0


# appeal_id -> активная игра (может быть только одна на обращение одновременно)
_active_games: dict[int, HangmanGame | GuessNumberGame] = {}


def has_active_game(appeal_id: int) -> bool:
    return appeal_id in _active_games


def get_active_game(appeal_id: int) -> HangmanGame | GuessNumberGame | None:
    return _active_games.get(appeal_id)


def stop_game(appeal_id: int) -> bool:
    return _active_games.pop(appeal_id, None) is not None


def start_hangman(appeal_id: int, started_by: int, custom_word: str | None = None) -> HangmanGame:
    word = (custom_word or random.choice(HANGMAN_WORDS)).strip().lower()
    game = HangmanGame(word=word, started_by=started_by, is_custom=bool(custom_word))
    _active_games[appeal_id] = game
    return game


def start_guess_number(appeal_id: int, started_by: int, max_value: int = 100) -> GuessNumberGame:
    game = GuessNumberGame(secret=random.randint(1, max_value), started_by=started_by, max_value=max_value)
    _active_games[appeal_id] = game
    return game


def render_hangman(game: HangmanGame) -> str:
    # Чёрному сердцу (проигранные жизни) готового premium-id нет — оставляем
    # обычный юникод осознанно, а не выдумываем id (это сломало бы отправку).
    hearts = ce(e.HEART) * (HANGMAN_MAX_WRONG - game.wrong) + "🖤" * game.wrong
    lock_note = (
        f"\n{ce(e.LOCK)} Слово загадал(а) один из участников — сам(а) себе он(а) угадывать не может."
        if game.is_custom else ""
    )
    return (
        f"{ce(e.GAME)} <b>Виселица</b>\n\n"
        f"<code>{game.masked()}</code>\n\n"
        f"Жизни: {hearts}\n"
        f"Уже называли: {', '.join(sorted(game.guessed)) or '—'}\n"
        f"{lock_note}\n"
        f"Присылай по одной букве. Остановить игру — /stopgame"
    )


async def broadcast_to_dialog(bot: Bot, appeal, text: str) -> None:
    """Отправляет текст и в топик обращения, и пользователю в личку."""
    if appeal.topic_id:
        try:
            await bot.send_message(settings.support_group_id, text, message_thread_id=appeal.topic_id, parse_mode="HTML")
        except Exception:
            pass
    try:
        await bot.send_message(appeal.user_id, text, parse_mode="HTML")
    except Exception:
        pass


async def process_hangman_guess(bot: Bot, session: AsyncSession, appeal, game: HangmanGame, letter: str, sender_id: int) -> None:
    letter = letter.lower()
    if letter in game.guessed:
        await broadcast_to_dialog(bot, appeal, f"Букву «{letter}» уже называли. Попробуй другую.")
        return

    game.guessed.add(letter)
    if letter not in game.word:
        game.wrong += 1

    if game.is_won:
        stop_game(appeal.id)
        await _record_result(session, appeal, "hangman", winner_id=sender_id)
        await broadcast_to_dialog(
            bot, appeal, f"{ce(e.PARTY)} Слово отгадано: <b>{game.word}</b>! Победа!\n\nЗапустить ещё раз — /hangman"
        )
        return
    if game.is_lost:
        stop_game(appeal.id)
        await broadcast_to_dialog(
            bot, appeal, f"💀 Жизни закончились. Загаданное слово: <b>{game.word}</b>.\n\nЕщё раз — /hangman"
        )
        return

    await broadcast_to_dialog(bot, appeal, render_hangman(game))


async def process_guess_number(bot: Bot, session: AsyncSession, appeal, game: GuessNumberGame, value: int, sender_id: int) -> None:
    game.attempts += 1
    if value == game.secret:
        stop_game(appeal.id)
        await _record_result(session, appeal, "guessnumber", winner_id=sender_id)
        await broadcast_to_dialog(
            bot, appeal,
            f"{ce(e.PARTY)} Угадал(а)! Число было {game.secret}. Попыток: {game.attempts}.\n\nЕщё раз — /guessnumber",
        )
        return
    hint = "больше" if value < game.secret else "меньше"
    await broadcast_to_dialog(
        bot, appeal, f"Загаданное число {hint}. Попыток: {game.attempts}. Диапазон: {game.min_value}–{game.max_value}."
    )


async def _record_result(session: AsyncSession, appeal, game_type: str, winner_id: int | None) -> None:
    participants = [pid for pid in (appeal.primary_admin_id, appeal.user_id) if pid is not None]
    session.add(
        GameResult(
            appeal_id=appeal.id,
            game_type=game_type,
            participants=json.dumps(participants),
            winner_id=winner_id,
        )
    )
    await session.commit()


async def try_handle_guess(bot: Bot, session: AsyncSession, appeal, sender_id: int, text: str) -> bool:
    """
    Если для этого обращения идёт игра и текст похож на ход в ней — обрабатывает
    ход и возвращает True (сообщение НЕ нужно пересылать как обычный чат).
    Иначе возвращает False — сообщение должно пойти по обычному пути (relay).
    """
    game = get_active_game(appeal.id)
    if game is None:
        return False

    text = text.strip()
    if isinstance(game, HangmanGame):
        if len(text) == 1 and text.isalpha():
            if game.is_custom and sender_id == game.started_by:
                # Загадавший слово сам не может его угадывать — но это всё ещё
                # "ход в игре" (не обычное сообщение), поэтому return True,
                # просто отвечаем отказом вместо обработки буквы.
                await broadcast_to_dialog(
                    bot, appeal,
                    f"{ce(e.NO_ENTRY)} Ты сам(а) загадал(а) это слово — угадывать его тебе нельзя, жди ход соперника.",
                )
                return True
            await process_hangman_guess(bot, session, appeal, game, text, sender_id)
            return True
        return False

    if isinstance(game, GuessNumberGame):
        if text.lstrip("-").isdigit():
            value = int(text)
            if game.min_value <= value <= game.max_value:
                await process_guess_number(bot, session, appeal, game, value, sender_id)
                return True
            await broadcast_to_dialog(
                bot, appeal, f"Число должно быть от {game.min_value} до {game.max_value}."
            )
            return True
        return False

    return False
