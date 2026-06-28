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
import uuid

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
RAW_DEBUG = DATA_DIR / "fifa_raw_debug.html"

FIFA_FIXTURES_URL = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures"

TZ = ZoneInfo("Europe/Berlin")
CALENDAR_NAME = "FIFA World Cup 2026 - ARD/ZDF"

# Calendar behavior
INCLUDE_UNRESOLVED = False
EXCLUDE_01_TO_12 = False

# New requirement:
# Keep only matches from today's Europe/Berlin date onward.
# This updates automatically every time GitHub Actions runs.
ONLY_FROM_TODAY_ONWARDS = True

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

def berlin_today() -> date:
    """
    Returns today's date in Europe/Berlin.
    Optional environment variable START_DATE_OVERRIDE=YYYY-MM-DD is supported for testing only.
    Do not set START_DATE_OVERRIDE in GitHub Actions if you want the calendar to stay dynamic.
    """
    override = os.environ.get("START_DATE_OVERRIDE", "").strip()
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    return datetime.now(TZ).date()

def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()

def normalize_stream(value: str) -> str:
    text = clean(value)
    upper = text.upper()
    lower = text.lower()

    if "TBC" in upper:
        return "TBC"

    if "magenta" in lower and "ARD" not in upper and "ZDF" not in upper:
        return "MagentaTV only"
    if "ARD" in upper and "ZDF" in upper:
        return "ARD/ZDF"
    if "ARD" in upper:
        return "ARD"
    if "ZDF" in upper:
        return "ZDF"
    if not text:
        return "TBC"
    return text

def is_ard_zdf(stream: str) -> bool:
    return normalize_stream(stream) in {"ARD", "ZDF", "ARD/ZDF"}

def unresolved(text: str) -> bool:
    lower = clean(text).lower()
    terms = [
        "winner", "runner-up", "runner up", "1st group", "2nd group",
        "3rd group", "third", "best third", "best 3rd", "match "
    ]
    return any(term in lower for term in terms)

def is_match_resolved(m: Match) -> bool:
    return bool(m.team_a and m.team_b) and not unresolved(m.team_a) and not unresolved(m.team_b)

def excluded_time_window(time_hhmm: str) -> bool:
    if not EXCLUDE_01_TO_12:
        return False
    t = datetime.strptime(time_hhmm, "%H:%M").time()
    return (
        (t.hour > 1 or (t.hour == 1 and t.minute >= 0))
        and
        (t.hour < 12 or (t.hour == 12 and t.minute == 0))
    )

def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def row_to_match(row: dict[str, str], fallback_source: str = "") -> Match | None:
    try:
        match_no = int(clean(row.get("match_no") or row.get("matchNumber") or row.get("match_no.")))
    except ValueError:
        return None

    return Match(
        match_no=match_no,
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
    matches = []
    for row in read_csv(MANUAL_FIXTURES_CSV):
        match = row_to_match(row, FIFA_FIXTURES_URL)
        if match:
            matches.append(match)
    return matches

def maybe_parse_date_time(value: str) -> tuple[str, str] | None:
    text = clean(value)
    if not text:
        return None

    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text.replace("Z", "+00:00"))

    for cand in candidates:
        try:
            dt = datetime.fromisoformat(cand)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            local = dt.astimezone(TZ)
            return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")
        except ValueError:
            pass

    m = re.search(r"(\d{4}-\d{2}-\d{2}).{0,10}(\d{1,2}):(\d{2})", text)
    if m:
        return m.group(1), f"{int(m.group(2)):02d}:{m.group(3)}"

    return None

def dict_find_first(d: dict, keys: list[str]) -> object:
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return ""

def team_name(value: object) -> str:
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, dict):
        for key in ["name", "shortName", "displayName", "countryName", "teamName", "abbreviation"]:
            if value.get(key):
                return clean(value[key])
    return ""

def stream_from_object(obj: object) -> str:
    text = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    return normalize_stream(text)

def walk_json(obj: object):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_json(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_json(item)

def extract_json_candidates(html_text: str) -> list[object]:
    candidates = []

    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.DOTALL)
    if m:
        try:
            candidates.append(json.loads(html.unescape(m.group(1))))
        except json.JSONDecodeError:
            pass

    for script_body in re.findall(r'<script[^>]+type=["\']application/(?:ld\+)?json["\'][^>]*>(.*?)</script>', html_text, re.DOTALL):
        try:
            candidates.append(json.loads(html.unescape(script_body)))
        except json.JSONDecodeError:
            pass

    return candidates

def object_to_match(d: dict) -> Match | None:
    match_no_raw = dict_find_first(d, ["matchNumber", "matchNo", "match_no", "matchIndex", "number"])
    if not match_no_raw:
        return None

    try:
        match_no = int(re.search(r"\d+", str(match_no_raw)).group())
    except Exception:
        return None

    home = team_name(dict_find_first(d, ["homeTeam", "home", "teamA", "contestantHome", "homeContestant"]))
    away = team_name(dict_find_first(d, ["awayTeam", "away", "teamB", "contestantAway", "awayContestant"]))

    if not home:
        home = clean(dict_find_first(d, ["homeTeamName", "homeName", "teamAName"]))
    if not away:
        away = clean(dict_find_first(d, ["awayTeamName", "awayName", "teamBName"]))

    dt_raw = dict_find_first(d, ["date", "startDate", "kickoff", "kickOff", "kickOffTime", "utcDate", "matchDate"])
    parsed = maybe_parse_date_time(clean(dt_raw))
    if not parsed:
        return None

    date_s, time_s = parsed

    round_s = clean(dict_find_first(d, ["round", "stage", "phase", "competitionStage"]))
    group_s = clean(dict_find_first(d, ["group", "groupName", "pool"]))

    stream = "TBC"
    for key in ["broadcasters", "broadcasts", "whereToWatch", "channels", "tvChannels", "media"]:
        if key in d:
            stream = stream_from_object(d[key])
            break

    return Match(
        match_no=match_no,
        date=date_s,
        time=time_s,
        round=round_s,
        group=group_s,
        team_a=home,
        team_b=away,
        stream=stream,
        source_url=FIFA_FIXTURES_URL,
        notes="Parsed from FIFA page",
    )

def fetch_fifa_matches() -> list[Match]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; WC2026CalendarBot/1.0; +https://github.com/)",
        "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    }

    try:
        response = requests.get(FIFA_FIXTURES_URL, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        print(f"[WARN] Could not fetch FIFA fixtures page: {exc}")
        return []

    html_text = response.text
    RAW_DEBUG.write_text(html_text[:2_000_000], encoding="utf-8")

    candidates = extract_json_candidates(html_text)
    matches_by_no = {}

    for candidate in candidates:
        for d in walk_json(candidate):
            match = object_to_match(d)
            if match:
                matches_by_no[match.match_no] = match

    matches = list(matches_by_no.values())
    matches.sort(key=lambda m: m.match_no)

    if not matches:
        print("[WARN] FIFA page fetched, but no matches could be parsed automatically.")
        print("[WARN] The script will use data/manual_fixtures.csv as fallback.")

    return matches

def apply_broadcaster_mapping(matches: list[Match]) -> list[Match]:
    mapping = {}
    for row in read_csv(BROADCASTERS_CSV):
        try:
            no = int(clean(row.get("match_no")))
        except ValueError:
            continue
        stream = normalize_stream(clean(row.get("stream")))
        if stream:
            mapping[no] = stream

    for match in matches:
        if match.match_no in mapping:
            match.stream = mapping[match.match_no]
    return matches

def apply_overrides(matches: list[Match]) -> list[Match]:
    by_no = {m.match_no: m for m in matches}

    for row in read_csv(OVERRIDES_CSV):
        try:
            no = int(clean(row.get("match_no")))
        except ValueError:
            continue

        existing = by_no.get(no)
        if existing is None:
            existing = Match(
                match_no=no,
                date="",
                time="",
                round="",
                group="",
                team_a="",
                team_b="",
                stream="TBC",
                source_url="data/overrides.csv",
                notes="Created by override",
            )
            by_no[no] = existing

        for field in ["date", "time", "team_a", "team_b", "round", "group", "notes", "include"]:
            value = clean(row.get(field))
            if value:
                setattr(existing, field, value)

        stream_value = clean(row.get("stream"))
        if stream_value:
            existing.stream = normalize_stream(stream_value)

        source_value = clean(row.get("source_url"))
        if source_value:
            existing.source_url = source_value

    return sorted(by_no.values(), key=lambda m: m.match_no)

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
    included = []
    audit = []

    for m in matches:
        reason = ""
        m_date = match_date(m)

        if clean(m.include).lower() == "no":
            reason = "excluded by override include=no"
        elif ONLY_FROM_TODAY_ONWARDS and m_date is not None and m_date < start_date:
            reason = f"excluded because match date {m.date} is before start date {start_date.isoformat()}"
        elif clean(m.include).lower() == "yes":
            if valid_datetime(m):
                included.append(m)
                reason = "included by override include=yes"
            else:
                reason = "include=yes but missing/invalid date or time"
        elif not is_ard_zdf(m.stream):
            reason = f"excluded because stream is not ARD/ZDF: {m.stream or 'blank'}"
        elif not INCLUDE_UNRESOLVED and not is_match_resolved(m):
            reason = "excluded because fixture is unresolved"
        elif excluded_time_window(m.time):
            reason = "excluded by 01:00-12:00 time filter"
        elif not valid_datetime(m):
            reason = "excluded because date/time is invalid"
        else:
            included.append(m)
            reason = "included"

        audit.append({
            "match_no": m.match_no,
            "date": m.date,
            "fixture": f"{m.team_a} vs {m.team_b}",
            "stream": m.stream,
            "decision": reason,
        })

    return sorted(included, key=lambda m: (m.date, m.time, m.match_no)), audit

def event_duration(m: Match) -> timedelta:
    r = m.round.lower()
    if any(k in r for k in ["round of", "quarter", "semi", "final", "third"]):
        return timedelta(hours=3)
    return timedelta(hours=2)

def ics_escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )

def fold_ics_line(line: str, limit: int = 75) -> str:
    current = ""
    current_len = 0
    folded = []
    for ch in line:
        ch_len = len(ch.encode("utf-8"))
        if current_len + ch_len > limit:
            folded.append(current)
            current = " " + ch
            current_len = 1 + ch_len
        else:
            current += ch
            current_len += ch_len
    folded.append(current)
    return "\r\n".join(folded)

def write_ics(matches: list[Match]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Damanjit Singh//WC2026 Dynamic Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{CALENDAR_NAME}",
    ]

    for m in matches:
        start_local = datetime.strptime(f"{m.date} {m.time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        end_local = start_local + event_duration(m)

        summary = f"FIFA M{m.match_no:02d} - {m.team_a} vs {m.team_b}"
        description = (
            f"{m.team_a} vs {m.team_b}\\n"
            f"Match No.: {m.match_no}\\n"
            f"Round: {m.round}\\n"
            f"Group: {m.group}\\n"
            f"Stream: {normalize_stream(m.stream)}\\n"
            f"Germany kickoff: {start_local.strftime('%d.%m.%Y %H:%M')}\\n"
            f"Source: {m.source_url}"
        )

        uid = f"wc2026-m{m.match_no}-{uuid.uuid4().hex[:8]}@wc2026-calendar"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{ics_escape(summary)}",
            f"DESCRIPTION:{ics_escape(description)}",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    text = "\r\n".join(fold_ics_line(line) for line in lines) + "\r\n"
    OUT_ICS.write_bytes(text.encode("utf-8"))

def write_status(included: list[Match], audit: list[dict], source_used: str, start_date: date) -> None:
    status = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "calendar_name": CALENDAR_NAME,
        "source_used": source_used,
        "start_date_europe_berlin": start_date.isoformat(),
        "only_from_today_onwards": ONLY_FROM_TODAY_ONWARDS,
        "included_count": len(included),
        "included_matches": [asdict(m) for m in included],
        "audit": audit,
    }
    OUT_STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

def write_index(included: list[Match], source_used: str, start_date: date) -> None:
    rows = "\n".join(
        f"<tr><td>{m.match_no}</td><td>{html.escape(m.date)}</td><td>{html.escape(m.time)}</td>"
        f"<td>{html.escape(m.team_a)} vs {html.escape(m.team_b)}</td><td>{html.escape(normalize_stream(m.stream))}</td></tr>"
        for m in included
    )

    OUT_INDEX.write_text(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(CALENDAR_NAME)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 1100px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
  </style>
</head>
<body>
  <h1>{html.escape(CALENDAR_NAME)}</h1>
  <p><strong>Last generated:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
  <p><strong>Source used:</strong> {html.escape(source_used)}</p>
  <p><strong>Start date Europe/Berlin:</strong> {start_date.isoformat()}</p>
  <p><strong>Included matches:</strong> {len(included)}</p>
  <p><a href="wc2026.ics">Open/download wc2026.ics</a></p>
  <h2>Included events</h2>
  <table>
    <thead><tr><th>Match</th><th>Date</th><th>Time</th><th>Fixture</th><th>Stream</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <h2>Debug</h2>
  <p><a href="status.json">status.json</a></p>
</body>
</html>
""", encoding="utf-8")

def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    start_date = berlin_today()

    fifa_matches = fetch_fifa_matches()
    if fifa_matches:
        matches = fifa_matches
        source_used = "FIFA automatic parser"
    else:
        matches = read_manual_fixtures()
        source_used = "manual_fixtures.csv fallback"

    matches = apply_broadcaster_mapping(matches)
    matches = apply_overrides(matches)
    included, audit = included_matches(matches, start_date)

    write_ics(included)
    write_status(included, audit, source_used, start_date)
    write_index(included, source_used, start_date)

    print(f"Source used: {source_used}")
    print(f"Start date Europe/Berlin: {start_date.isoformat()}")
    print(f"Total matches after source + overrides: {len(matches)}")
    print(f"Included ARD/ZDF resolved matches from start date onward: {len(included)}")
    print(f"Wrote: {OUT_ICS}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
