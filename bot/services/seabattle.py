from __future__ import annotations

import random

BOARD_SIZE = 10
FLEET = [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]  # классический флот: 1x4, 2x3, 3x2, 4x1


def generate_board() -> list[int]:
    """Случайно расставляет классический флот на поле 10x10 без соприкосновений (даже по диагонали)."""
    size = BOARD_SIZE
    board = [0] * (size * size)

    def cell(r: int, c: int) -> int:
        return r * size + c

    def fits(r: int, c: int, length: int, horizontal: bool) -> bool:
        cells = [(r, c + i) if horizontal else (r + i, c) for i in range(length)]
        for rr, cc in cells:
            if not (0 <= rr < size and 0 <= cc < size):
                return False
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    nr, nc = rr + dr, cc + dc
                    if 0 <= nr < size and 0 <= nc < size and board[cell(nr, nc)] == 1:
                        return False
        return True

    for length in FLEET:
        placed = False
        for _ in range(500):
            horizontal = random.random() < 0.5
            r = random.randint(0, size - 1)
            c = random.randint(0, size - 1)
            if fits(r, c, length, horizontal):
                cells = [(r, c + i) if horizontal else (r + i, c) for i in range(length)]
                for rr, cc in cells:
                    board[cell(rr, cc)] = 1
                placed = True
                break
        if not placed:
            return generate_board()

    return board


def validate_manual_board(board: list[int]) -> tuple[bool, str]:
    """
    Проверяет, что вручную расставленный флот (список из 100 клеток, 1=корабль,
    0=пусто) РОВНО соответствует классическому набору — 1x4, 2x3, 3x2, 4x1
    палубных, всего 20 клеток кораблей — и что корабли нигде не соприкасаются
    (даже по диагонали), как в классических правилах. Возвращает (ok, причина).
    """
    size = BOARD_SIZE
    if len(board) != size * size:
        return False, "Некорректный размер поля"
    if any(v not in (0, 1) for v in board):
        return False, "Поле должно содержать только 0 и 1"
    total = sum(board)
    if total != sum(FLEET):
        return False, f"Всего должно быть занято {sum(FLEET)} клеток кораблями, сейчас {total}"

    def cell(r: int, c: int) -> int:
        return r * size + c

    visited = [False] * len(board)
    segment_lengths: list[int] = []

    for r in range(size):
        for c in range(size):
            idx = cell(r, c)
            if board[idx] != 1 or visited[idx]:
                continue
            # BFS по 4-связности — это один корабль (прямая линия)
            stack = [(r, c)]
            visited[idx] = True
            cells_in_ship = [(r, c)]
            while stack:
                cr, cc = stack.pop()
                for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < size and 0 <= nc < size:
                        nidx = cell(nr, nc)
                        if board[nidx] == 1 and not visited[nidx]:
                            visited[nidx] = True
                            stack.append((nr, nc))
                            cells_in_ship.append((nr, nc))

            # корабль обязан быть прямой линией (1xN или Nx1) — проверяем, что
            # все клетки лежат в одной строке ИЛИ в одном столбце
            rows = {p[0] for p in cells_in_ship}
            cols = {p[1] for p in cells_in_ship}
            if len(rows) > 1 and len(cols) > 1:
                return False, "Корабль должен быть прямой линией, а не углом/квадратом"
            segment_lengths.append(len(cells_in_ship))

            # ни одна клетка этого корабля не должна соприкасаться (даже по
            # диагонали) с клеткой ДРУГОГО корабля
            for cr, cc in cells_in_ship:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        nr, nc = cr + dr, cc + dc
                        if 0 <= nr < size and 0 <= nc < size and (nr, nc) not in cells_in_ship:
                            if board[cell(nr, nc)] == 1:
                                return False, "Корабли не должны соприкасаться друг с другом (даже по диагонали)"

    if sorted(segment_lengths) != sorted(FLEET):
        counts = {length: segment_lengths.count(length) for length in set(segment_lengths)}
        return False, (
            f"Неверный состав флота: нужно 1x4-палубный, 2x3-палубных, 3x2-палубных, "
            f"4x1-палубных (10 кораблей). Сейчас: {counts}"
        )

    return True, "ok"
