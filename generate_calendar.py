from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo
import csv
import html
import json
import os
import re

import requests

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

MANUAL_FIXTURES_CSV = DATA_DIR / "manual_fixtures.csv"
BROADCASTERS_CSV = DATA_DIR / "broadcasters.csv"
OVERRIDES_CSV = DATA_DIR / "overrides.csv"

OUT_ICS = DOCS_DIR / "wc2026.ics"
OUT_INDEX = DOCS_DIR / "index.html"
OUT_STATUS = DOCS_DIR / "status.json"

FIFA_RAW_DEBUG = DATA_DIR / "fifa_raw_debug.html"
SPORTSCHAU_RAW_DEBUG = DATA_DIR / "sportschau_raw_debug.html"
ZDF_RAW_DEBUG = DATA_DIR / "zdf_raw_debug.html"

FIFA_FIXTURES_URL = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures"
SPORTSCHAU_SCHEDULE_URL = "https://www.sportschau.de/fussball/fifa-wm-2026/der-spielplan-der-fussball-wm-2026%2Cfifawm-spielplan-100.html"
ZDF_SCHEDULE_URL = "https://www.zdf.de/fussball-wm-spielplan-ergebnisse-live-100"

TZ = ZoneInfo("Europe/Berlin")
CALENDAR_NAME = "FIFA World Cup 2026 - ARD/ZDF Planning"

ONLY_FROM_TODAY_ONWARDS = True
INCLUDE_UNKNOWN_BROADCASTER_AS_TBD = True
EXCLUDE_01_TO_12 = False

@dataclass
class Match:
    match_no: int
    date: str
    time: str
    round: str
    group: str
    team_a: str
    team_b: str
    stream: str
    source_url: str
    notes: str = ""
    include: str = ""

def clean(value: object) -> str:
    return "" if value is None else str(value).strip()

def berlin_today() -> date:
    override = os.environ.get("START_DATE_OVERRIDE", "").strip()
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    return datetime.now(TZ).date()

def normalize_stream(value: str) -> str:
    text = clean(value)
    upper = text.upper()
    lower = text.lower()

    if "ZDF ODER MAGENTA" in upper or "ZDF/MAGENTA" in upper:
        return "ZDF/Magenta TBC"
    if "ARD ODER MAGENTA" in upper or "ARD/MAGENTA" in upper:
        return "ARD/Magenta TBC"
    if ("ARD" in upper or "ZDF" in upper) and "TBC" in upper:
        if "ARD" in upper and "ZDF" in upper:
            return "ARD/ZDF TBC"
        if "ARD" in upper:
            return "ARD TBC"
        return "ZDF TBC"
    if "DAS ERSTE" in upper:
        return "ARD"
    if "MAGENTA" in upper and "ARD" not in upper and "ZDF" not in upper:
        return "MagentaTV only"
    if "ARD" in upper and "ZDF" in upper:
        return "ARD/ZDF"
    if "ARD" in upper:
        return "ARD"
    if "ZDF" in upper:
        return "ZDF"
    if "TBC" in upper or not text:
        return "TBC"
    return text

def is_magenta_only(stream: str) -> bool:
    return normalize_stream(stream) == "MagentaTV only"

def is_confirmed_free_tv(stream: str) -> bool:
    return normalize_stream(stream) in {"ARD", "ZDF", "ARD/ZDF"}

def is_unknown_stream_candidate(stream: str) -> bool:
    return normalize_stream(stream) in {
        "TBC", "ARD/ZDF TBC", "ARD TBC", "ZDF TBC", "ZDF/Magenta TBC", "ARD/Magenta TBC"
    }

def display_stream(stream: str) -> str:
    norm = normalize_stream(stream)
    if norm in {"ARD", "ZDF", "ARD/ZDF"}:
        return norm
    return "TBD"

def unresolved_text(text: str) -> bool:
    lower = clean(text).lower()
    return any(term in lower for term in [
        "winner", "loser", "runner-up", "runner up", "1st group", "2nd group",
        "3rd group", "best third", "best 3rd", "sieger", "verlierer", "match ", "spiel "
    ])

def display_team(text: str) -> str:
    return "TBD" if not clean(text) or unresolved_text(text) else clean(text)

def fixture_title(m: Match) -> str:
    return f"{display_team(m.team_a)} vs {display_team(m.team_b)}"

def stage_code(m: Match) -> str:
    r = clean(m.round).lower()
    if "group" in r or "vorrunde" in r:
        return "Group"
    if "round of 32" in r or "sechzehntel" in r or "r32" in r:
        return "R32"
    if "round of 16" in r or "achtelfinale" in r or "r16" in r:
        return "R16"
    if "quarter" in r or "viertel" in r:
        return "QF"
    if "semi" in r or "halbfinale" in r:
        return "SF"
    if "third" in r or "platz 3" in r:
        return "3rd Place"
    if "final" in r or "finale" in r:
        return "Finals"
    return "Match"

def event_title(m: Match) -> str:
    return f"FIFA {stage_code(m)} - {fixture_title(m)} - {display_stream(m.stream)}"

def event_duration(m: Match) -> timedelta:
    return timedelta(hours=3) if stage_code(m) in {"R32", "R16", "QF", "SF", "3rd Place", "Finals"} else timedelta(hours=2)

def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def row_to_match(row: dict[str, str], fallback_source: str = "") -> Match | None:
    try:
        no = int(clean(row.get("match_no") or row.get("matchNumber") or row.get("match_no.")))
    except ValueError:
        return None
    return Match(
        match_no=no,
        date=clean(row.get("date")),
        time=clean(row.get("time")),
        round=clean(row.get("round")),
        group=clean(row.get("group")),
        team_a=clean(row.get("team_a") or row.get("home") or row.get("home_team")),
        team_b=clean(row.get("team_b") or row.get("away") or row.get("away_team")),
        stream=normalize_stream(clean(row.get("stream") or row.get("broadcaster"))),
        source_url=clean(row.get("source_url")) or fallback_source,
        notes=clean(row.get("notes")),
        include=clean(row.get("include")),
    )

def read_manual_fixtures() -> list[Match]:
    out = []
    for row in read_csv(MANUAL_FIXTURES_CSV):
        m = row_to_match(row, FIFA_FIXTURES_URL)
        if m:
            out.append(m)
    return sorted(out, key=lambda m: m.match_no)

def apply_broadcaster_seed(matches: list[Match]) -> list[Match]:
    mapping = {}
    for row in read_csv(BROADCASTERS_CSV):
        try:
            no = int(clean(row.get("match_no")))
        except ValueError:
            continue
        stream = normalize_stream(clean(row.get("stream")))
        if stream:
            mapping[no] = stream
    for m in matches:
        if m.match_no in mapping:
            m.stream = mapping[m.match_no]
    return matches

def merge_matches(base: list[Match], updates: list[Match]) -> list[Match]:
    by_no = {m.match_no: m for m in base}
    for u in updates:
        current = by_no.get(u.match_no)
        if current is None:
            by_no[u.match_no] = u
            continue
        for field in ["date", "time", "round", "group", "team_a", "team_b", "stream", "source_url"]:
            value = clean(getattr(u, field))
            if value:
                setattr(current, field, value)
        if clean(u.notes):
            current.notes = (clean(current.notes) + " | " + clean(u.notes)).strip(" |")
    return sorted(by_no.values(), key=lambda m: m.match_no)

def apply_overrides(matches: list[Match]) -> list[Match]:
    by_no = {m.match_no: m for m in matches}
    for row in read_csv(OVERRIDES_CSV):
        try:
            no = int(clean(row.get("match_no")))
        except ValueError:
            continue
        m = by_no.get(no) or Match(no, "", "", "", "", "", "", "TBC", "data/overrides.csv")
        for field in ["date", "time", "round", "group", "team_a", "team_b", "notes", "include"]:
            if clean(row.get(field)):
                setattr(m, field, clean(row.get(field)))
        if clean(row.get("stream")):
            m.stream = normalize_stream(row.get("stream"))
        if clean(row.get("source_url")):
            m.source_url = clean(row.get("source_url"))
        by_no[no] = m
    return sorted(by_no.values(), key=lambda m: m.match_no)

def fetch_url(url: str, debug_path: Path) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; WC2026CalendarBot/4.0; +https://github.com/)",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    debug_path.write_text(r.text[:2_000_000], encoding="utf-8")
    return r.text

def html_to_text(html_text: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>", " ", html_text)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", "\n", text)
    text = html.unescape(text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

MONTHS_DE = {
    "januar": "01", "februar": "02", "märz": "03", "maerz": "03", "april": "04",
    "mai": "05", "juni": "06", "juli": "07", "august": "08", "september": "09",
    "oktober": "10", "november": "11", "dezember": "12"
}

TEAM_DE_TO_EN = {
    "Südafrika": "South Africa", "Kanada": "Canada", "Brasilien": "Brazil",
    "Japan": "Japan", "Deutschland": "Germany", "Paraguay": "Paraguay",
    "Niederlande": "Netherlands", "Marokko": "Morocco",
    "Elfenbeinküste": "Ivory Coast", "Norwegen": "Norway",
    "Frankreich": "France", "Schweden": "Sweden", "Mexiko": "Mexico",
    "Ecuador": "Ecuador", "England": "England", "DR Kongo": "DR Congo",
    "Belgien": "Belgium", "Senegal": "Senegal", "Sénégal": "Senegal",
    "USA": "USA", "Bosnien-Herzegowina": "Bosnia-Herzegovina",
    "Spanien": "Spain", "Österreich": "Austria", "Portugal": "Portugal",
    "Kroatien": "Croatia", "Schweiz": "Switzerland", "Algerien": "Algeria",
    "Australien": "Australia", "Ägypten": "Egypt", "Argentinien": "Argentina",
    "Kap Verde": "Cape Verde", "Kolumbien": "Colombia", "Ghana": "Ghana"
}

def normalize_team(name: str) -> str:
    return TEAM_DE_TO_EN.get(clean(name), clean(name))

def parse_german_date(text: str) -> str:
    s = clean(text)
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.", s)
    if m:
        return f"2026-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})\.?\s+([A-Za-zÄÖÜäöüß]+)", s)
    if m:
        mon = MONTHS_DE.get(m.group(2).lower())
        if mon:
            return f"2026-{mon}-{int(m.group(1)):02d}"
    return ""

def infer_round(context: str) -> str:
    low = context.lower()
    choices = [
        ("spiel um platz drei", "Third-place match"),
        ("halbfinale", "Semi-final"),
        ("viertelfinale", "Quarter-final"),
        ("achtelfinale", "Round of 16"),
        ("sechzehntelfinale", "Round of 32"),
        ("vorrunde", "Group Match"),
        ("finale", "Final"),
    ]
    pos, label = -1, ""
    for needle, lab in choices:
        p = low.rfind(needle)
        if p > pos:
            pos, label = p, lab
    return label

def stream_from_trail(trail: str) -> str:
    t = clean(trail)
    if re.search(r"ZDF\s+oder\s+Magenta", t, re.I):
        return "ZDF/Magenta TBC"
    if re.search(r"ARD\s+oder\s+Magenta", t, re.I):
        return "ARD/Magenta TBC"
    if re.search(r"Das Erste|\bARD\b", t, re.I):
        return "ARD"
    if re.search(r"\bZDF\b", t, re.I):
        return "ZDF"
    if re.search(r"\bMagenta\b", t, re.I):
        return "MagentaTV only"
    return "TBC"

def parse_schedule_text(text: str, source_url: str) -> list[Match]:
    updates = {}
    semi_counter = 0

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    context_so_far = ""

    # Main rows with match number.
    row_re = re.compile(
        r"(?P<date>\d{1,2}\.\d{1,2}\.|\d{1,2}\.?\s+[A-Za-zÄÖÜäöüß]+)\s+"
        r"(?P<time>\d{1,2}:\d{2})\s+"
        r"(?P<a>.+?)\s*[-–]\s*(?P<b>.+?)\s*"
        r"\(Spiel\s+(?P<no>\d+)\)\s*(?P<trail>.*)$",
        re.I
    )

    # Rows without match number for semi/final sections.
    row_no_no = re.compile(
        r"(?P<date>\d{1,2}\.\d{1,2}\.|\d{1,2}\.?\s+[A-Za-zÄÖÜäöüß]+)\s+"
        r"(?P<time>\d{1,2}:\d{2})\s+"
        r"(?P<a>.+?)\s*[-–]\s*(?P<b>.+?)(?:\s+(?P<trail>ARD|ZDF|Magenta|Das Erste|ZDF oder Magenta|ARD oder Magenta))?$",
        re.I
    )

    for line in lines:
        if any(h in line.lower() for h in ["sechzehntelfinale", "achtelfinale", "viertelfinale", "halbfinale", "spiel um platz drei", "finale", "vorrunde"]):
            context_so_far += "\n" + line

        m = row_re.search(line)
        if m:
            no = int(m.group("no"))
            date_s = parse_german_date(m.group("date"))
            if not date_s:
                continue
            round_s = infer_round(context_so_far)
            updates[no] = Match(
                match_no=no,
                date=date_s,
                time=f"{int(m.group('time').split(':')[0]):02d}:{m.group('time').split(':')[1]}",
                round=round_s,
                group="",
                team_a=normalize_team(m.group("a")),
                team_b=normalize_team(m.group("b")),
                stream=stream_from_trail(m.group("trail")),
                source_url=source_url,
                notes=f"Updated from live source: {source_url}",
            )
            continue

        # Handle semi/final rows without explicit (Spiel N).
        stage = infer_round(context_so_far)
        if stage in {"Semi-final", "Third-place match", "Final"}:
            m2 = row_no_no.search(line)
            if m2:
                if stage == "Semi-final":
                    semi_counter += 1
                    no = 100 + semi_counter
                elif stage == "Third-place match":
                    no = 103
                else:
                    no = 104
                date_s = parse_german_date(m2.group("date"))
                if not date_s:
                    continue
                updates[no] = Match(
                    match_no=no,
                    date=date_s,
                    time=f"{int(m2.group('time').split(':')[0]):02d}:{m2.group('time').split(':')[1]}",
                    round=stage,
                    group="",
                    team_a=normalize_team(m2.group("a")),
                    team_b=normalize_team(m2.group("b")),
                    stream=stream_from_trail(m2.group("trail") or ""),
                    source_url=source_url,
                    notes=f"Updated from live source without explicit match number: {source_url}",
                )

        context_so_far += "\n" + line

    return sorted(updates.values(), key=lambda x: x.match_no)

def fetch_source_updates(url: str, debug_path: Path) -> list[Match]:
    try:
        text = html_to_text(fetch_url(url, debug_path))
        return parse_schedule_text(text, url)
    except Exception as exc:
        print(f"[WARN] fetch/parse failed for {url}: {exc}")
        return []

def valid_datetime(m: Match) -> bool:
    try:
        datetime.strptime(m.date, "%Y-%m-%d")
        datetime.strptime(m.time, "%H:%M")
        return True
    except ValueError:
        return False

def match_date(m: Match) -> date | None:
    try:
        return datetime.strptime(m.date, "%Y-%m-%d").date()
    except ValueError:
        return None

def included_matches(matches: list[Match], start_date: date) -> tuple[list[Match], list[dict]]:
    included, audit = [], []
    for m in sorted(matches, key=lambda x: x.match_no):
        md = match_date(m)
        if clean(m.include).lower() == "no":
            decision = "excluded by override include=no"
        elif not valid_datetime(m) or md is None:
            decision = "excluded invalid date/time"
        elif ONLY_FROM_TODAY_ONWARDS and md < start_date:
            decision = f"excluded before start date {start_date}"
        elif clean(m.include).lower() == "yes":
            included.append(m); decision = "included by override include=yes"
        elif is_magenta_only(m.stream):
            decision = "excluded confirmed MagentaTV-only"
        elif is_confirmed_free_tv(m.stream):
            included.append(m); decision = "included confirmed ARD/ZDF"
        elif INCLUDE_UNKNOWN_BROADCASTER_AS_TBD and is_unknown_stream_candidate(m.stream):
            included.append(m); decision = "included as TBD broadcaster candidate"
        else:
            decision = f"excluded stream not eligible: {m.stream}"
        audit.append({
            "match_no": m.match_no, "date": m.date, "time": m.time,
            "calendar_title": event_title(m), "raw_stream": m.stream,
            "raw_fixture": f"{m.team_a} vs {m.team_b}", "decision": decision
        })
    return sorted(included, key=lambda m: (m.date, m.time, m.match_no)), audit

def ics_escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")

def fold_ics_line(line: str, limit: int = 75) -> str:
    cur, cur_len, folded = "", 0, []
    for ch in line:
        bl = len(ch.encode("utf-8"))
        if cur_len + bl > limit:
            folded.append(cur)
            cur, cur_len = " " + ch, 1 + bl
        else:
            cur += ch
            cur_len += bl
    folded.append(cur)
    return "\r\n".join(folded)

def write_ics(matches: list[Match]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Damanjit Singh//WC2026 Robust Planning Calendar V2//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{CALENDAR_NAME}", "X-WR-TIMEZONE:Europe/Berlin",
    ]
    for m in matches:
        start_local = datetime.strptime(f"{m.date} {m.time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        end_local = start_local + event_duration(m)
        description = (
            f"Match No.: {m.match_no}\\n"
            f"Stage: {stage_code(m)}\\n"
            f"Teams: {fixture_title(m)}\\n"
            f"Raw slot: {m.team_a} vs {m.team_b}\\n"
            f"Broadcaster shown: {display_stream(m.stream)}\\n"
            f"Raw broadcaster: {m.stream}\\n"
            f"Kickoff Germany: {start_local.strftime('%d.%m.%Y %H:%M')}\\n"
            f"Source: {m.source_url}\\n"
            f"Notes: {m.notes}"
        )
        # Stable UID is critical: same match updates instead of duplicates.
        uid = f"wc2026-match-{m.match_no}@wc2026-calendar"
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{ics_escape(event_title(m))}",
            f"DESCRIPTION:{ics_escape(description)}",
            f"LAST-MODIFIED:{stamp}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    OUT_ICS.write_bytes(("\r\n".join(fold_ics_line(l) for l in lines) + "\r\n").encode("utf-8"))

def write_status(included: list[Match], audit: list[dict], start_date: date, source_counts: dict) -> None:
    OUT_STATUS.write_text(json.dumps({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "calendar_name": CALENDAR_NAME,
        "start_date_europe_berlin": start_date.isoformat(),
        "rules": {
            "include_unknown_broadcaster_as_tbd": INCLUDE_UNKNOWN_BROADCASTER_AS_TBD,
            "exclude_confirmed_magenta_only": True,
            "stable_uid_per_match": True,
        },
        "source_counts": source_counts,
        "included_count": len(included),
        "included_matches": [asdict(m) | {"calendar_title": event_title(m)} for m in included],
        "audit": audit,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

def write_index(included: list[Match], start_date: date, source_counts: dict) -> None:
    rows = "\n".join(
        f"<tr><td>{m.match_no}</td><td>{html.escape(m.date)}</td><td>{html.escape(m.time)}</td><td>{html.escape(event_title(m))}</td><td>{html.escape(m.source_url)}</td></tr>"
        for m in included
    )
    OUT_INDEX.write_text(f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{html.escape(CALENDAR_NAME)}</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:32px;line-height:1.5}}table{{border-collapse:collapse;width:100%;max-width:1200px}}th,td{{border:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}}th{{background:#f5f5f5}}</style>
</head>
<body>
<h1>{html.escape(CALENDAR_NAME)}</h1>
<p><strong>Last generated:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
<p><strong>Start date Europe/Berlin:</strong> {start_date.isoformat()}</p>
<p><strong>Included events:</strong> {len(included)}</p>
<p><strong>Source counts:</strong> {html.escape(json.dumps(source_counts))}</p>
<p><a href="wc2026.ics">Open/download wc2026.ics</a> | <a href="status.json">status.json</a></p>
<table><thead><tr><th>Match</th><th>Date</th><th>Time</th><th>Calendar title</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>""", encoding="utf-8")

def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    start_date = berlin_today()

    matches = read_manual_fixtures()
    matches = apply_broadcaster_seed(matches)

    sportschau_updates = fetch_source_updates(SPORTSCHAU_SCHEDULE_URL, SPORTSCHAU_RAW_DEBUG)
    zdf_updates = fetch_source_updates(ZDF_SCHEDULE_URL, ZDF_RAW_DEBUG)

    matches = merge_matches(matches, sportschau_updates)
    matches = merge_matches(matches, zdf_updates)
    matches = apply_overrides(matches)

    included, audit = included_matches(matches, start_date)

    source_counts = {
        "manual_fixtures": len(read_manual_fixtures()),
        "sportschau_updates": len(sportschau_updates),
        "zdf_updates": len(zdf_updates),
    }
    write_ics(included)
    write_status(included, audit, start_date, source_counts)
    write_index(included, start_date, source_counts)

    print(f"Start date Europe/Berlin: {start_date.isoformat()}")
    print(f"Source counts: {source_counts}")
    print(f"Included events: {len(included)}")
    print(f"Wrote {OUT_ICS}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
