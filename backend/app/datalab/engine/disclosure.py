"""Disclosure control (decision 2026-10-03, rebuilt after Codex's audit, finding 2), one policy for every
output made from a result. A count of records from 1 to threshold - 1 is hidden, and so is any total
of that size. Totals are part of the table: a row, its total and the column of totals are each a line
that must not leave exactly one hidden entry, zeros included. Then every hidden small count is audited
by linear programming: given everything shown, the range it could take must be at least the threshold
wide; when it isn't, the smallest further entry in its row or column is hidden too, and the audit runs
again. Every hidden entry carries the same neutral mark, so a hidden small count can't be told from a
hidden larger one. Tables, charts, map labels, report text and the workbooks are all built from the
same masked table, never from the raw counts."""

from dataclasses import dataclass

import numpy as np

HIDDEN = "–"
NOTE = "– hidden to protect privacy: a count below {t}, or a number that would reveal one."


def note(threshold: int) -> str:
    return NOTE.format(t=threshold)


def few(n: int, threshold: int) -> str:
    """A count in running text: shown when 0 or at least the threshold, otherwise "fewer than N"."""
    return f"{n:,}" if n == 0 or n >= threshold else f"fewer than {threshold}"


@dataclass
class Protection:
    """Which entries of a table to hide: the cells, each row's total, each column's total, the grand total."""

    cells: np.ndarray
    rows: np.ndarray
    columns: np.ndarray
    total: bool

    @property
    def any(self) -> bool:
        return bool(self.cells.any() or self.rows.any() or self.columns.any() or self.total)


def protect(counts: np.ndarray, threshold: int, row_totals: bool = True, column_totals: bool = True) -> Protection:
    """The hidden entries of a table of counts shown with the totals asked for (a one-way table is a
    single row with its total). Small counts and small totals are hidden; then complementary entries,
    until no line has a single hidden entry and every small count's feasible range is wide enough."""
    counts = np.asarray(counts, dtype=float)
    if counts.ndim == 1:
        counts = counts.reshape(1, -1)
    r, c = counts.shape
    grid = np.zeros((r + 1, c + 1))
    grid[:r, :c] = counts
    grid[:r, c] = counts.sum(axis=1)
    grid[r, :c] = counts.sum(axis=0)
    grid[r, c] = counts.sum()
    present = np.zeros_like(grid, dtype=bool)  # entries that appear in the output at all
    present[:r, :c] = True
    if row_totals:
        present[:r, c] = True
    if column_totals:
        present[r, :c] = True
    present[r, c] = row_totals or column_totals
    hidden = present & (grid > 0) & (grid < threshold)
    if 0 < grid[r, c] < threshold:  # too few records altogether: nothing is shown
        hidden = present.copy()
    primary = hidden.copy()
    for _ in range(grid.size + 1):
        _complete_lines(grid, hidden, present, r, c)
        weak = [(i, j) for i, j in zip(*np.nonzero(primary), strict=True) if _width(grid, hidden, present, r, c, i, j) < threshold]
        if not weak:
            break
        grown = False
        for i, j in weak:
            if _hide_next(grid, hidden, present, r, c, i, j):
                grown = True
                break
        if not grown:  # nothing left to hide around it: hide what remains present
            hidden = present.copy()
            break
    return Protection(cells=hidden[:r, :c], rows=hidden[:r, c], columns=hidden[r, :c], total=bool(hidden[r, c]))


def _lines(r: int, c: int) -> list[list[tuple[int, int]]]:
    """Each row with its total, and each column with its total (the totals row and column included)."""
    rows = [[(i, j) for j in range(c + 1)] for i in range(r + 1)]
    cols = [[(i, j) for i in range(r + 1)] for j in range(c + 1)]
    return rows + cols


def _complete_lines(grid: np.ndarray, hidden: np.ndarray, present: np.ndarray, r: int, c: int) -> None:
    changed = True
    while changed:
        changed = False
        for line in _lines(r, c):
            shown_here = [(i, j) for i, j in line if present[i, j]]
            if sum(hidden[i, j] for i, j in shown_here) != 1:
                continue
            if len(shown_here) < len(line):  # a line whose total isn't shown has no equation to solve
                continue
            options = [(i, j) for i, j in shown_here if not hidden[i, j]]
            if not options:
                continue
            # the smallest other entry, a body cell before a total, a non-zero count before a zero
            i, j = min(options, key=lambda ij: (ij[0] == r or ij[1] == c, grid[ij] == 0, grid[ij]))
            hidden[i, j] = True
            changed = True


def _hide_next(grid: np.ndarray, hidden: np.ndarray, present: np.ndarray, r: int, c: int, i: int, j: int) -> bool:
    options = [(i, k) for k in range(c + 1) if present[i, k] and not hidden[i, k]] + [(k, j) for k in range(r + 1) if present[k, j] and not hidden[k, j]]
    if not options:
        return False
    a, b = min(options, key=lambda ij: (ij[0] == r or ij[1] == c, grid[ij] == 0, grid[ij]))
    hidden[a, b] = True
    return True


def _width(grid: np.ndarray, hidden: np.ndarray, present: np.ndarray, r: int, c: int, i: int, j: int) -> float:
    """How wide a range a hidden entry could take given everything shown (and every count >= 0)."""
    from scipy.optimize import linprog

    unknown = [(a, b) for a in range(r + 1) for b in range(c + 1) if hidden[a, b] or not present[a, b]]
    index = {cell: k for k, cell in enumerate(unknown)}
    rows_eq, rhs = [], []
    for line in _lines(r, c):
        body, total = line[:-1], line[-1]
        coeffs = np.zeros(len(unknown))
        constant = 0.0
        for cell in body:
            if cell in index:
                coeffs[index[cell]] += 1
            else:
                constant += grid[cell]
        if total in index:
            coeffs[index[total]] -= 1
        else:
            constant -= grid[total]
        if coeffs.any():
            rows_eq.append(coeffs)
            rhs.append(-constant)
    target = np.zeros(len(unknown))
    target[index[(i, j)]] = 1
    bounds = [(0, None)] * len(unknown)
    a_eq = np.array(rows_eq) if rows_eq else None
    b_eq = np.array(rhs) if rows_eq else None
    low = linprog(target, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    high = linprog(-target, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not low.success:
        return 0.0
    if high.status == 3:  # unbounded above: as wide as can be
        return float("inf")
    return float(-high.fun - low.fun) if high.success else 0.0
