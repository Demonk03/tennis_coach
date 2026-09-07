"""Выгрузка матчей из Supabase в markdown-лог для Obsidian.

Требует SUPABASE_URL и SUPABASE_KEY (в .env рядом со скриптом или в окружении).

    python3 export_log.py            # печатает блок в stdout
    python3 export_log.py --write    # вписывает блок в заметку между маркерами
"""

import os
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

from dotenv import load_dotenv

load_dotenv()

NOTE_PATH = (
    "/Users/dkossenkov/Documents/Private files/Second brain/08 Hobbies/Tennis.md"
)
START_MARKER = "<!-- tennis-log:start -->"
END_MARKER = "<!-- tennis-log:end -->"

SURFACE_RU = {
    "hard": "хард",
    "clay": "грунт",
    "grass": "трава",
    "carpet": "ковёр",
    "other": "другое",
}
FORMAT_RU = {
    "tournament": "турнир",
    "1h_session": "1 час",
    "2h_session": "2 часа",
    "friendly": "спарринг",
}


def fetch(table: str, query: str) -> list[dict[str, Any]]:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    request = urllib.request.Request(
        f"{url}/rest/v1/{table}?{query}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        import json

        return json.load(response)


def parse_sets(final_score: str | None) -> list[tuple[int, int]]:
    if not final_score:
        return []
    sets = []
    for chunk in re.findall(r"(\d+)\s*[-:]\s*(\d+)", final_score):
        sets.append((int(chunk[0]), int(chunk[1])))
    return sets


def result_of(final_score: str | None) -> str:
    sets = parse_sets(final_score)
    if not sets:
        return "—"
    won = sum(1 for mine, theirs in sets if mine > theirs)
    lost = len(sets) - won
    if won == lost:
        return "="
    return "W" if won > lost else "L"


def level_of(raw: str | None) -> str:
    if not raw:
        return "—"
    match = re.search(r"\d+(?:[.,]\d+)?", raw)
    return match.group(0).replace(",", ".") if match else "—"


def cell(text: str | None, limit: int = 0) -> str:
    if not text:
        return "—"
    value = " ".join(text.split())
    if limit and len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value.replace("|", "\\|")


def build_rows() -> list[dict[str, Any]]:
    matches = fetch("matches", "select=*&status=eq.completed&order=match_date")
    preps = {p["match_id"]: p for p in fetch("match_prep", "select=*")}
    reviews = {r["match_id"]: r for r in fetch("match_reviews", "select=*")}
    rows = []
    for match in matches:
        prep = preps.get(match["id"], {})
        review = reviews.get(match["id"], {})
        rows.append({**match, "prep": prep, "review": review})
    return rows


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        START_MARKER,
        "",
        "### Матчи из приложения",
        "",
        "| Дата | Соперник | Ур. | Покр. | Формат | Счёт | Рез | Ф | М | Энергия до |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        review = row["review"]
        prep = row["prep"]
        lines.append(
            "| {date} | {opponent} | {level} | {surface} | {fmt} | {score} | {result} "
            "| {phys} | {ment} | {energy} |".format(
                date=row["match_date"],
                opponent=cell(row["opponent_name"], 24),
                level=level_of(row["opponent_level"]),
                surface=SURFACE_RU.get(row["surface"], row["surface"]),
                fmt=FORMAT_RU.get(row["session_format"], row["session_format"]),
                score=cell(row["final_score"]),
                result=result_of(row["final_score"]),
                phys=review.get("physical_rating", "—"),
                ment=review.get("mental_rating", "—"),
                energy=prep.get("energy_level", "—"),
            )
        )

    lines += ["", "### Разборы матчей", ""]
    for row in reversed(rows):
        review = row["review"]
        prep = row["prep"]
        lines.append(
            f"**{row['match_date']} — {cell(row['opponent_name'])} "
            f"({level_of(row['opponent_level'])}), {cell(row['final_score'])} "
            f"{result_of(row['final_score'])}**"
        )
        lines.append("")
        if prep.get("physical_state"):
            lines.append(f"- До, физика: {cell(prep['physical_state'])}")
        if prep.get("mindset"):
            lines.append(f"- До, настрой: {cell(prep['mindset'])}")
        if review.get("technical_comment"):
            lines.append(f"- После, техника: {cell(review['technical_comment'])}")
        if review.get("mental_comment"):
            lines.append(f"- После, ментал: {cell(review['mental_comment'])}")
        lines.append("")

    lines.append(END_MARKER)
    return "\n".join(lines)


def write_note(block: str) -> None:
    with open(NOTE_PATH, encoding="utf-8") as handle:
        note = handle.read()
    if START_MARKER not in note or END_MARKER not in note:
        raise SystemExit("В заметке нет маркеров tennis-log:start / tennis-log:end")
    head, rest = note.split(START_MARKER, 1)
    _, tail = rest.split(END_MARKER, 1)
    with open(NOTE_PATH, "w", encoding="utf-8") as handle:
        handle.write(head + block + tail)


if __name__ == "__main__":
    block = render(build_rows())
    if "--write" in sys.argv:
        write_note(block)
        print(f"Обновлено: {NOTE_PATH}")
    else:
        print(block)
