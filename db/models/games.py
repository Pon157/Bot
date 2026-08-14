from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, TimestampMixin


class TicTacToeGame(TimestampMixin, Base):
    """
    Крестики-нолики с настраиваемым полем (/ttt3x3 .. /ttt10x10).
    Играется через мини-аппу (miniapps/backend/routers/ttt.py), т.к. в
    топике/группе ссылки на веб-аппы открываются некорректно — ссылки на игру
    отправляются участникам личным сообщением от бота.
    """

    __tablename__ = "tictactoe_games"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appeal_id: Mapped[int | None] = mapped_column(ForeignKey("appeals.id", ondelete="CASCADE"), nullable=True)

    board_size: Mapped[int] = mapped_column(SmallInteger)  # N в NxN, 3..10
    win_length: Mapped[int] = mapped_column(SmallInteger)  # сколько подряд нужно для победы

    # JSON-список из board_size*board_size чисел: 0 — пусто, 1 — X, 2 — O
    board: Mapped[str] = mapped_column(Text)

    turn: Mapped[int] = mapped_column(SmallInteger, default=1)  # чей ход: 1=X, 2=O
    player_x_id: Mapped[int] = mapped_column(BigInteger)
    player_o_id: Mapped[int] = mapped_column(BigInteger)

    winner: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)  # 0=ничья, 1=X, 2=O
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | finished


class SeaBattleGame(TimestampMixin, Base):
    """
    Морской бой 10x10, классический флот (1x4-палубный, 2x3-палубных,
    3x2-палубных, 4x1-палубных). Расстановка кораблей — автоматическая
    (случайная, без соприкосновений) при создании игры, чтобы не городить
    интерфейс ручной расстановки в мини-аппе — сразу играется "в бой".

    board1/board2 — JSON-список из 100 чисел на игрока:
      0 — пусто, 1 — целый корабль, 2 — подбитая клетка корабля, 3 — промах (вода)
    Каждая доска хранит и корабли владельца, и результаты выстрелов ПРОТИВНИКА
    по ней — это одновременно и "своё поле", и то, что видно по факту боя.
    """

    __tablename__ = "seabattle_games"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appeal_id: Mapped[int | None] = mapped_column(ForeignKey("appeals.id", ondelete="CASCADE"), nullable=True)

    board1: Mapped[str] = mapped_column(Text)
    board2: Mapped[str] = mapped_column(Text)

    turn: Mapped[int] = mapped_column(SmallInteger, default=1)  # чей ход: 1 или 2
    player1_id: Mapped[int] = mapped_column(BigInteger)
    player2_id: Mapped[int] = mapped_column(BigInteger)

    ready1: Mapped[bool] = mapped_column(default=False)  # расставил корабли и нажал "Готов"
    ready2: Mapped[bool] = mapped_column(default=False)

    winner: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)  # 1 или 2
    status: Mapped[str] = mapped_column(String(16), default="placing")  # placing | active | finished


class GameResult(TimestampMixin, Base):
    """
    Единый лог результатов ЛЮБОЙ мини-игры (виселица/угадай число/крестики-
    нолики/морской бой) — используется только для статистики побед в
    мини-аппе (/gamestats), не для самого игрового состояния (оно у каждой
    игры своё — TicTacToeGame/SeaBattleGame/в памяти для словесных игр).
    """

    __tablename__ = "game_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appeal_id: Mapped[int | None] = mapped_column(ForeignKey("appeals.id", ondelete="SET NULL"), nullable=True)
    game_type: Mapped[str] = mapped_column(String(20))  # hangman | guessnumber | ttt | battleship
    participants: Mapped[str] = mapped_column(Text)     # JSON-список telegram_id участников
    winner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # None = ничья/без победителя
