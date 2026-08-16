from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.seabattle import BOARD_SIZE, FLEET, validate_manual_board
from miniapps.backend.auth import get_current_telegram_user
from miniapps.backend.db import get_session
from db.models import GameResult, SeaBattleGame

router = APIRouter()


class MoveIn(BaseModel):
    cell: int


class PlaceIn(BaseModel):
    board: list[int]


class GameOut(BaseModel):
    id: int
    board_size: int
    fleet: list[int]
    status: str
    my_board: list[int]
    enemy_shots: list[int]
    turn: int
    winner: int | None
    you_are: int | None
    you_ready: bool
    opponent_ready: bool


def _make_out(game: SeaBattleGame, you_are: int | None) -> GameOut:
    board1 = json.loads(game.board1)
    board2 = json.loads(game.board2)
    if you_are == 1:
        my_board, enemy_board = board1, board2
        you_ready, opponent_ready = game.ready1, game.ready2
    elif you_are == 2:
        my_board, enemy_board = board2, board1
        you_ready, opponent_ready = game.ready2, game.ready1
    else:
        my_board, enemy_board = board1, board2  # зритель
        you_ready, opponent_ready = False, False

    if game.status == "placing":
        enemy_shots = [0] * (BOARD_SIZE * BOARD_SIZE)
    else:
        enemy_shots = [v if v in (2, 3) else 0 for v in enemy_board]

    return GameOut(
        id=game.id,
        board_size=BOARD_SIZE,
        fleet=FLEET,
        status=game.status,
        my_board=my_board,
        enemy_shots=enemy_shots,
        turn=game.turn,
        winner=game.winner,
        you_are=you_are,
        you_ready=you_ready,
        opponent_ready=opponent_ready,
    )


@router.get("/{game_id}", response_model=GameOut)
async def get_game(
    game_id: int,
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    game = await session.get(SeaBattleGame, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    you_are = 1 if tg_user["id"] == game.player1_id else (2 if tg_user["id"] == game.player2_id else None)
    return _make_out(game, you_are)


@router.post("/{game_id}/place", response_model=GameOut)
async def place_fleet(
    game_id: int,
    payload: PlaceIn,
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    game = await session.get(SeaBattleGame, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    if game.status != "placing":
        raise HTTPException(status_code=400, detail="Расстановка кораблей уже завершена")

    you_are = 1 if tg_user["id"] == game.player1_id else (2 if tg_user["id"] == game.player2_id else None)
    if you_are is None:
        raise HTTPException(status_code=403, detail="Ты не участник этой игры")

    ok, reason = validate_manual_board(payload.board)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    if you_are == 1:
        game.board1 = json.dumps(payload.board)
        game.ready1 = True
    else:
        game.board2 = json.dumps(payload.board)
        game.ready2 = True

    if game.ready1 and game.ready2:
        game.status = "active"
        game.turn = 1

    await session.commit()
    return _make_out(game, you_are)


@router.post("/{game_id}/fire", response_model=GameOut)
async def fire(
    game_id: int,
    payload: MoveIn,
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    game = await session.get(SeaBattleGame, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    if game.status == "placing":
        raise HTTPException(status_code=400, detail="Сначала оба игрока должны расставить корабли")
    if game.status != "active":
        raise HTTPException(status_code=400, detail="Игра уже завершена")

    you_are = 1 if tg_user["id"] == game.player1_id else (2 if tg_user["id"] == game.player2_id else None)
    if you_are is None:
        raise HTTPException(status_code=403, detail="Ты не участник этой игры")
    if you_are != game.turn:
        raise HTTPException(status_code=409, detail="Сейчас не твой ход")

    n_cells = BOARD_SIZE * BOARD_SIZE
    if not (0 <= payload.cell < n_cells):
        raise HTTPException(status_code=400, detail="Некорректная клетка")

    enemy_board = json.loads(game.board2 if you_are == 1 else game.board1)
    if enemy_board[payload.cell] in (2, 3):
        raise HTTPException(status_code=409, detail="По этой клетке уже стреляли")

    hit = enemy_board[payload.cell] == 1
    enemy_board[payload.cell] = 2 if hit else 3

    if you_are == 1:
        game.board2 = json.dumps(enemy_board)
    else:
        game.board1 = json.dumps(enemy_board)

    if not any(v == 1 for v in enemy_board):
        game.winner = you_are
        game.status = "finished"
        session.add(
            GameResult(
                appeal_id=game.appeal_id,
                game_type="battleship",
                participants=json.dumps([game.player1_id, game.player2_id]),
                winner_id=game.player1_id if you_are == 1 else game.player2_id,
            )
        )
    elif not hit:
        game.turn = 2 if game.turn == 1 else 1


    await session.commit()
    return _make_out(game, you_are)
