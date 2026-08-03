"""Gozinto node graph -> a plain HTML <table>, rowspan-merged to read like an assembly chart.

No client-side library: the table is fully server-rendered, one row per ingredient and
one column per operation "layer" (see gozinto_layout.layer_nodes). An operation cell's
rowspan covers every ingredient row that transitively feeds it, which is what produces
the bracket look -- CSS (in build_site.py's page template) supplies the actual border
styling, this module only decides the grid shape.
"""

from __future__ import annotations

import html

from gozinto_layout import layer_nodes


def to_table_html(nodes: list[dict]) -> str:
    if not nodes:
        return "<table></table>"

    by_id = {n["id"]: n for n in nodes}
    layers = layer_nodes(nodes)

    banner_ops = [n for n in layers[0] if n["type"] == "operation"]
    ingredient_rows = [n for n in layers[0] if n["type"] == "ingredient"]
    op_layers = layers[1:]

    row_index = {n["id"]: i for i, n in enumerate(ingredient_rows)}
    n_rows = len(ingredient_rows)
    n_cols = 1 + len(op_layers)

    leaf_cache: dict[str, set[str]] = {}

    def leaf_ids(node_id: str) -> set[str]:
        if node_id in leaf_cache:
            return leaf_cache[node_id]
        node = by_id[node_id]
        if node["type"] == "ingredient":
            result = {node_id}
        else:
            result = set()
            for dep in node.get("inputs") or []:
                result |= leaf_ids(dep)
        leaf_cache[node_id] = result
        return result

    # grid[r][c] is None (covered by a rowspan from above -- emit nothing) until
    # assigned (html, rowspan) at the top-left corner of that cell's span.
    grid: list[list[tuple[str, int] | None]] = [[None] * n_cols for _ in range(n_rows)]
    covered = [[False] * n_cols for _ in range(n_rows)]

    for i, ing in enumerate(ingredient_rows):
        grid[i][0] = (_ingredient_cell(ing), 1)
        covered[i][0] = True

    for c, layer in enumerate(op_layers, start=1):
        placed = []
        for op in layer:
            rows = sorted(row_index[i] for i in leaf_ids(op["id"]) if i in row_index)
            top, bottom = (rows[0], rows[-1]) if rows else (0, 0)
            placed.append((top, bottom, op))
        for top, bottom, op in placed:
            grid[top][c] = (_operation_cell(op), bottom - top + 1)
            for r in range(top, bottom + 1):
                covered[r][c] = True

    for r in range(n_rows):
        for c in range(n_cols):
            if not covered[r][c]:
                grid[r][c] = ("", 1)

    rows_html = [_banner_row(op, n_cols) for op in banner_ops]
    for r in range(n_rows):
        cells = []
        for c in range(n_cols):
            cell = grid[r][c]
            if cell is None:
                continue
            content, span = cell
            rowspan_attr = f' rowspan="{span}"' if span > 1 else ""
            if c == 0:
                cls = "ingredient"
            elif content:
                cls = "op"
            else:
                cls = "empty"
            cells.append(f'<td{rowspan_attr} class="{cls}">{content}</td>')
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    return f'<table class="gozinto">\n<tbody>\n{"".join(f"{r}\n" for r in rows_html)}</tbody>\n</table>'


def _ingredient_cell(node: dict) -> str:
    name = html.escape(node.get("name") or "")
    amount = html.escape(node.get("amount") or "")
    return f'<span class="name">{name}</span><span class="amount">{amount}</span>'


def _operation_cell(node: dict) -> str:
    technique = html.escape(node.get("technique") or "")
    detail = node.get("detail")
    detail_html = f'<span class="detail">{html.escape(detail)}</span>' if detail else ""
    return f'<span class="technique">{technique}</span>{detail_html}'


def _banner_row(node: dict, n_cols: int) -> str:
    technique = html.escape(node.get("technique") or "")
    detail = node.get("detail")
    detail_html = f' &mdash; {html.escape(detail)}' if detail else ""
    return f'<tr><td colspan="{n_cols}" class="setup">{technique}{detail_html}</td></tr>'
