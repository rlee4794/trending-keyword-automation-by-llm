#!/usr/bin/env python3
"""Export daily_trending_{REGION}.json to a formatted XLSX workbook.

Produces a 3-sheet workbook:
  1. 本日要點 — daily highlights with signal + description
  2. 熱門菜式 — Top N dish keywords with term→concept, posts, likes, background
  3. 原始數據摘要 — pipeline execution summary

The daily highlights are inferred from the keyword data automatically.
Usage:
  python3 scripts/export_xlsx.py --date 2026-07-29 --region hk
  python3 scripts/export_xlsx.py --date 2026-07-29 --region hk --output /path/to/output.xlsx --top 15
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
except ImportError:
    print("ERROR: openpyxl is required. Install with: pip install openpyxl", file=sys.stderr)
    sys.exit(1)

# ── helpers ──────────────────────────────────────────────────────────

TITLE_FONT = Font(name="Microsoft YaHei", size=16, bold=True, color="1F4E79")
HEADER_FONT = Font(name="Microsoft YaHei", size=11, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
BODY_FONT = Font(name="Microsoft YaHei", size=10)
SUBTITLE_FONT = Font(name="Microsoft YaHei", size=9, color="666666")
THIN_BORDER = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)

REGION_LABEL = {"hk": "HK", "tw": "TW"}


def _style_header_row(ws, row: int, headers: list[str]) -> None:
    for col, val in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER


def _write_cell(ws, row: int, col: int, value, *, bold: bool = False, center: bool = False) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = Font(name="Microsoft YaHei", size=10, bold=bold)
    cell.border = THIN_BORDER
    cell.alignment = Alignment(
        horizontal="center" if center else "left",
        vertical="center",
        wrap_text=True,
    )


# ── signal inference ─────────────────────────────────────────────────

def _infer_highlights(keywords: list[dict]) -> list[tuple[str, str]]:
    """Heuristic signal detection from keyword data."""
    highlights: list[tuple[str, str]] = []
    used = set()

    for kw in keywords:
        term = kw.get("term", "")
        concept = kw.get("concept", term)
        likes = kw.get("total_likes", 0)
        post_count = kw.get("post_count", 0)
        sources = kw.get("sources", [])
        source_str = ", ".join(sources[:3]) if sources else ""

        display = f"{term} → {concept}" if term != concept else term

        # Single-post viral spike
        if post_count == 1 and likes > 8000 and display not in used:
            highlights.append((f"{display} 單帖爆發", f"單帖 {likes/1000:.1f}K likes{('，來自 ' + source_str) if source_str else ''}，極高互動"))
            used.add(display)
            continue

        # Multi-post sustained trend
        if post_count >= 4 and likes > 10000 and display not in used:
            highlights.append((f"{display} 持續熱度", f"{post_count} 帖累計 {likes/1000:.1f}K likes，跨平台/跨 source 持續發酵"))
            used.add(display)
            continue

    # If fewer than 3 signals, pad with generic observations
    if len(highlights) < 3:
        total_posts = sum(k.get("post_count", 0) for k in keywords)
        total_keywords = len(keywords)
        if ("pipeline_stats" not in used):
            highlights.append(("Pipeline 摘要", f"共 {total_posts} posts 通過 threshold，提取 {total_keywords} 個關鍵詞"))
            used.add("pipeline_stats")

    return highlights[:5]


# ── sheet builders ───────────────────────────────────────────────────

def _build_highlights_sheet(wb: Workbook, highlights: list[tuple[str, str]], date: str, region: str) -> None:
    ws = wb.active
    ws.title = "本日要點"

    region_label = REGION_LABEL.get(region, region.upper())

    ws.merge_cells("A1:B1")
    ws["A1"] = f"📊 {region_label} F&B 熱門關鍵字 — 本日要點（{date}）"
    ws["A1"].font = TITLE_FONT
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 35

    ws.merge_cells("A2:B2")
    ws["A2"] = f"Pipeline 自動生成 | 資料來源: Instagram + Threads | Google Trends: disabled"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 22

    _style_header_row(ws, 4, ["要點", "說明"])
    ws.row_dimensions[4].height = 25

    for i, (label, desc) in enumerate(highlights, 5):
        _write_cell(ws, i, 1, label, bold=True)
        _write_cell(ws, i, 2, desc)
        ws.row_dimensions[i].height = 30

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 70


def _build_dishes_sheet(wb: Workbook, keywords: list[dict], posts: list[dict], date: str, region: str, top_n: int) -> None:
    ws = wb.create_sheet("熱門菜式")
    region_label = REGION_LABEL.get(region, region.upper())

    # Build lookup: post index → caption (posts are stored as a list, position is the index)
    post_caption: dict[int, str] = {}
    for idx, p in enumerate(posts):
        cap = p.get("caption_snippet", "") or ""
        # Use first 300 chars of caption as background detail
        post_caption[idx] = cap[:300].strip()

    ws.merge_cells("A1:F1")
    ws["A1"] = f"🔥 Social 熱門菜式（按互動熱度，Top {top_n}）"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 35

    ws.merge_cells("A2:F2")
    ws["A2"] = f"資料來源: Instagram + Threads | 日期: {date} | 地區: {region_label}"
    ws["A2"].font = SUBTITLE_FONT

    _style_header_row(ws, 4, ["關鍵詞", "Concept", "Posts", "Likes", "Shares", "背景 / 帖文摘要"])

    # Sort by engagement (likes + shares)
    for k in keywords:
        k["engagement"] = k.get("total_likes", 0) + k.get("total_shares", 0)
    active = sorted(
        [k for k in keywords if k.get("post_count", 0) > 0],
        key=lambda x: x["engagement"],
        reverse=True,
    )[:top_n]

    for i, kw in enumerate(active, 5):
        term = kw.get("term", "")
        concept = kw.get("concept", term)
        post_count = kw.get("post_count", 0)
        likes = kw.get("total_likes", 0)
        shares = kw.get("total_shares", 0)
        sources = kw.get("sources", [])
        source_str = ", ".join(sources[:3]) if sources else ""

        display = f"{term} → {concept}" if term != concept else term

        # Build background: source + caption snippet from first associated post
        bg_parts = []
        if source_str:
            bg_parts.append(f"來源: {source_str}")

        # Get caption from first related post
        post_indices = kw.get("post_indices", [])
        if post_indices:
            first_idx = post_indices[0]
            cap = post_caption.get(first_idx, "")
            if cap:
                # Extract ~70 chars, prioritize keeping venue/location context
                # Strip newlines, collapse whitespace
                cap_flat = " ".join(cap.replace("\n", " ").split())
                cap_short = cap_flat[:70]
                if len(cap_flat) > 70:
                    cap_short = cap_short.rstrip() + "…"
                bg_parts.append(cap_short)

        bg = " | ".join(bg_parts) if bg_parts else f"{post_count} 帖提及"

        _write_cell(ws, i, 1, display)
        _write_cell(ws, i, 2, concept)
        _write_cell(ws, i, 3, post_count, center=True)
        _write_cell(ws, i, 4, f"{likes/1000:.1f}K", center=True)
        _write_cell(ws, i, 5, f"{shares/1000:.1f}K", center=True)
        _write_cell(ws, i, 6, bg)
        ws.row_dimensions[i].height = 30

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 8
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 10
    ws.column_dimensions["F"].width = 40


def _build_summary_sheet(wb: Workbook, data: dict, date: str, region: str) -> None:
    ws = wb.create_sheet("原始數據摘要")

    ws.merge_cells("A1:C1")
    ws["A1"] = "Pipeline 執行摘要"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 30

    threshold = data.get("threshold", {})
    ig_th = threshold.get("instagram", {})
    threads_th = threshold.get("threads", {})

    posts = data.get("posts", [])
    ig_count = sum(1 for p in posts if p.get("platform") == "instagram")
    threads_count = sum(1 for p in posts if p.get("platform") == "threads")
    active_kw = sum(1 for k in data.get("keywords", []) if k.get("post_count", 0) > 0)

    summary = [
        ("日期", date),
        ("地區", REGION_LABEL.get(region, region.upper())),
        ("通過 threshold posts", f"{len(posts)} ({ig_count} IG + {threads_count} Threads)"),
        ("提取 keyword 數", f"{active_kw} (有 post 關聯)"),
        ("Threshold (IG)", f"like≥{ig_th.get('min_likes', '?')} OR share≥{ig_th.get('min_shares', '?')}"),
        ("Threshold (Threads)", f"like≥{threads_th.get('min_likes', '?')} OR share≥{threads_th.get('min_shares', '?')}"),
        ("Google Trends", "enabled" if threshold.get("google", {}).get("enabled") else "disabled"),
        ("Generated at", data.get("generated_at", "")),
    ]

    for i, (k, v) in enumerate(summary, 3):
        _write_cell(ws, i, 1, k, bold=True)
        _write_cell(ws, i, 2, v)

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 55


# ── main ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Export daily trending data to XLSX")
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--region", default="hk", choices=["hk", "tw"], help="Region (default: hk)")
    parser.add_argument("--output", help="Output XLSX path (default: workspace)")
    parser.add_argument("--top", type=int, default=30, help="Top N dishes to include (default: 30)")
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parent.parent
    json_path = skill_dir / "runs" / args.date / f"daily_trending_{args.region.upper()}.json"

    if not json_path.exists():
        print(f"ERROR: {json_path} not found. Run the pipeline first.", file=sys.stderr)
        sys.exit(1)

    with open(json_path) as f:
        data = json.load(f)

    keywords = data.get("keywords", [])
    posts = data.get("posts", [])

    # Infer highlights
    highlights = _infer_highlights(keywords)

    # Build workbook
    wb = Workbook()
    _build_highlights_sheet(wb, highlights, args.date, args.region)
    _build_dishes_sheet(wb, keywords, posts, args.date, args.region, args.top)
    _build_summary_sheet(wb, data, args.date, args.region)

    # Output path
    if args.output:
        output = Path(args.output)
    else:
        output = Path.home() / ".openclaw" / "workspace" / f"{REGION_LABEL.get(args.region, args.region.upper())}_FB_Trending_{args.date}.xlsx"

    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output))
    print(f"✅ XLSX exported: {output}")


if __name__ == "__main__":
    main()
