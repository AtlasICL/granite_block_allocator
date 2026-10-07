"""Turning an allocation into something to save, paste or print."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from html import escape
from pathlib import Path

from allocator import APP_NAME, __version__
from allocator.logic import AllocationResult

NOT_PLACED = "Not placed"


def fmt(weight: float) -> str:
    return f"{weight:.2f}"


def _rows(result: AllocationResult) -> list[list[str]]:
    rows = [["Container", "BlockNo", "Weight", "Container total"]]
    for cid, (blocks, total) in enumerate(
        zip(result.containers, result.container_totals, strict=True), start=1
    ):
        for block_id, weight in blocks:
            rows.append([str(cid), block_id, fmt(weight), fmt(total)])
    for block_id, weight in result.unplaced:
        rows.append([NOT_PLACED, block_id, fmt(weight), ""])
    return rows


def to_csv(result: AllocationResult, path: str | Path) -> None:
    """Save one row per block: container, block number, weight, container total.

    Written as UTF-8 with a byte-order mark so Excel opens it correctly."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(_rows(result))


def to_clipboard_text(result: AllocationResult) -> str:
    """Tab-separated text, which pastes into Excel as separate columns."""
    buf = io.StringIO()
    csv.writer(buf, delimiter="\t", lineterminator="\n").writerows(_rows(result))
    return buf.getvalue()


def summary_line(result: AllocationResult) -> str:
    n_total = result.placed_count + len(result.unplaced)
    containers = len(result.containers)
    parts = [
        f"{containers} container{'s' if containers != 1 else ''}",
        f"{result.placed_count} of {n_total} blocks placed",
        f"{fmt(result.placed_weight)} loaded",
    ]
    if result.containers:
        parts.append(f"{result.utilisation:.1%} of capacity used")
    return " · ".join(parts)


def settings_line(result: AllocationResult, count_requested: int | None = None) -> str:
    parts = []
    if count_requested is not None:
        parts.append(f"{count_requested} container{'s' if count_requested != 1 else ''} available")
    parts.append(f"max weight {result.capacity:g}")
    parts.append("no block limit" if result.max_blocks is None else f"max {result.max_blocks} blocks each")
    parts.append("loads spread evenly" if result.balanced else "each container filled in turn")
    return " · ".join(parts)


_SHEET_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font: 14px/1.45 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
       color: #1f2328; margin: 32px auto; max-width: 820px; padding: 0 24px; }
header { display: flex; justify-content: space-between; align-items: flex-start;
         gap: 16px; border-bottom: 2px solid #1f2328; padding-bottom: 12px; }
h1 { font-size: 22px; margin: 0 0 4px; }
.meta { color: #59636e; font-size: 13px; }
.summary { margin: 16px 0 8px; font-weight: 600; }
.note { background: #fff8c5; border: 1px solid #d4a72c; border-radius: 6px;
        padding: 8px 12px; margin: 8px 0; font-size: 13px; }
section { break-inside: avoid; margin: 20px 0; }
h2 { font-size: 16px; margin: 0 0 6px; display: flex; justify-content: space-between; }
h2 span { font-weight: 400; color: #59636e; }
table { width: 100%; border-collapse: collapse; }
th, td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; }
th { background: #f6f8fa; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
td.tick { width: 70px; }
td.tick span { display: inline-block; width: 16px; height: 16px;
                border: 1.5px solid #59636e; border-radius: 3px; }
tfoot td { font-weight: 600; background: #f6f8fa; }
.leftover h2 { color: #9a6700; }
button { font: inherit; padding: 6px 14px; border-radius: 6px; border: 1px solid #d0d7de;
         background: #f6f8fa; cursor: pointer; }
footer { margin-top: 28px; color: #59636e; font-size: 12px; }
@media print {
  body { margin: 0; max-width: none; }
  .no-print { display: none; }
  section { page-break-inside: avoid; }
}
"""


def to_html(
    result: AllocationResult,
    source_name: str = "",
    count_requested: int | None = None,
    when: datetime | None = None,
    auto_print: bool = True,
) -> str:
    """A printable loading sheet: one table per container with tick boxes."""
    when = when or datetime.now()
    out: list[str] = []
    a = out.append
    a("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    a(f"<title>Loading sheet – {escape(source_name or 'allocation')}</title>")
    a(f"<style>{_SHEET_CSS}</style></head><body>")
    a("<header><div><h1>Container loading sheet</h1>")
    meta = [when.strftime("%d %b %Y, %H:%M")]
    if source_name:
        meta.append(escape(source_name))
    a(f"<div class='meta'>{' · '.join(meta)}</div>")
    a(f"<div class='meta'>{escape(settings_line(result, count_requested))}</div></div>")
    a("<button class='no-print' onclick='window.print()'>Print</button></header>")
    a(f"<p class='summary'>{escape(summary_line(result))}</p>")
    for note in result.notes:
        a(f"<div class='note'>{escape(note)}</div>")

    for cid, (blocks, total) in enumerate(
        zip(result.containers, result.container_totals, strict=True), start=1
    ):
        fill = total / result.capacity if result.capacity else 0
        a("<section>")
        a(f"<h2>Container {cid}<span>{fmt(total)} of {result.capacity:g} · {fill:.1%} full</span></h2>")
        a("<table><thead><tr><th>Block</th><th class='num'>Weight</th><th>Loaded</th></tr></thead><tbody>")
        for block_id, weight in blocks:
            a(
                f"<tr><td>{escape(block_id)}</td><td class='num'>{fmt(weight)}</td>"
                "<td class='tick'><span></span></td></tr>"
            )
        a(
            f"</tbody><tfoot><tr><td>{len(blocks)} block{'s' if len(blocks) != 1 else ''}</td>"
            f"<td class='num'>{fmt(total)}</td><td></td></tr></tfoot></table></section>"
        )

    if result.unplaced:
        a("<section class='leftover'>")
        a(f"<h2>Not placed<span>{len(result.unplaced)} blocks · {fmt(result.unplaced_weight)}</span></h2>")
        a("<table><thead><tr><th>Block</th><th class='num'>Weight</th></tr></thead><tbody>")
        for block_id, weight in result.unplaced:
            a(f"<tr><td>{escape(block_id)}</td><td class='num'>{fmt(weight)}</td></tr>")
        a("</tbody></table></section>")

    a(f"<footer>{escape(APP_NAME)} {escape(__version__)}</footer>")
    if auto_print:
        a("<script>window.addEventListener('load', () => setTimeout(() => window.print(), 300));</script>")
    a("</body></html>")
    return "\n".join(out)
