from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from miniapps.backend.auth import get_current_telegram_user
from miniapps.backend.db import get_session
from db.models import GameResult, TicTacToeGame

router = APIRouter()


class MoveIn(BaseModel):
    cell: int


class GameOut(BaseModel):
    id: int
    board_size: int
    win_length: int
    board: list[int]
    turn: int
    player_x_id: int
    player_o_id: int
    winner: int | None
    status: str
    you_are: int | None


def _check_winner(board: list[int], size: int, win_length: int) -> int | None:
    def cell(r: int, c: int) -> int:
        return board[r * size + c]

    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for r in range(size):
        for c in range(size):
            player = cell(r, c)
            if player == 0:
                continue
            for dr, dc in directions:
                count = 1
                rr, cc = r + dr, c + dc
                while 0 <= rr < size and 0 <= cc < size and cell(rr, cc) == player:
                    count += 1
                    if count >= win_length:
                        return player
                    rr += dr
                    cc += dc
    if all(v != 0 for v in board):
        return 0
    return None


@router.get("/{game_id}", response_model=GameOut)
async def get_game(
    game_id: int,
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    game = await session.get(TicTacToeGame, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Игра не найдена")

    you_are = None
    if tg_user["id"] == game.player_x_id:
        you_are = 1
    elif tg_user["id"] == game.player_o_id:
        you_are = 2

    return GameOut(
        id=game.id,
        board_size=game.board_size,
        win_length=game.win_length,
        board=json.loads(game.board),
        turn=game.turn,
        player_x_id=game.player_x_id,
        player_o_id=game.player_o_id,
        winner=game.winner,
        status=game.status,
        you_are=you_are,
    )


@router.post("/{game_id}/move", response_model=GameOut)
async def make_move(
    game_id: int,
    payload: MoveIn,
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    game = await session.get(TicTacToeGame, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    if game.status != "active":
        raise HTTPException(status_code=400, detail="Игра уже завершена")

    you_are = 1 if tg_user["id"] == game.player_x_id else (2 if tg_user["id"] == game.player_o_id else None)
    if you_are is None:
        raise HTTPException(status_code=403, detail="Ты не участник этой игры")
    if you_are != game.turn:
        raise HTTPException(status_code=409, detail="Сейчас не твой ход")

    board = json.loads(game.board)
    n_cells = game.board_size * game.board_size
    if not (0 <= payload.cell < n_cells):
        raise HTTPException(status_code=400, detail="Некорректная клетка")
    if board[payload.cell] != 0:
        raise HTTPException(status_code=409, detail="Клетка уже занята")

    board[payload.cell] = you_are
    result = _check_winner(board, game.board_size, game.win_length)

    game.board = json.dumps(board)
    if result is not None:
        game.winner = result
        game.status = "finished"
        winner_id = None
        if result == 1:
            winner_id = game.player_x_id
        elif result == 2:
            winner_id = game.player_o_id
        session.add(
            GameResult(
                appeal_id=game.appeal_id,
                game_type="ttt",
                participants=json.dumps([game.player_x_id, game.player_o_id]),
                winner_id=winner_id,
            )
        )
    else:
        game.turn = 2 if game.turn == 1 else 1
    await session.commit()

    return GameOut(
        id=game.id,
        board_size=game.board_size,
        win_length=game.win_length,
        board=board,
        turn=game.turn,
        player_x_id=game.player_x_id,
        player_o_id=game.player_o_id,
        winner=game.winner,
        status=game.status,
        you_are=you_are,
    )
