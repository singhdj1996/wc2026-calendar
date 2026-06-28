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
SPORTSCHAU_STREAMS_URL = "https://www.sportschau.de/fussball/fifa-wm-2026/alle-livestreams-zur-wm-2026%2Cstream-uebersicht-100.html"
ZDF_SCHEDULE_URL = "https://www.zdf.de/fussball-wm-spielplan-ergebnisse-live-100"

TZ = ZoneInfo("Europe/Berlin")
CALENDAR_NAME = "FIFA World Cup 2026 - ARD/ZDF Planning"

# Current/future only.
ONLY_FROM_TODAY_ONWARDS = True

# Key planning behavior:
# - confirmed ARD/ZDF: included
# - unknown/TBC broadcaster: included as TBD
# - known MagentaTV only: excluded
INCLUDE_BROADCASTER_UNKNOWN_AS_TBD = True

# Key planning behavior:
# unresolved teams stay visible as TBD vs TBD.
INCLUDE_UNKNOWN_TEAMS_AS_TBD = True

# Old morning filter intentionally disabled.
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

def is_unknown_or_candidate_stream(stream: str) -> bool:
    norm = normalize_stream(stream)
    return norm in {"TBC", "ARD/ZDF TBC", "ARD TBC", "ZDF TBC", "ZDF/Magenta TBC", "ARD/Magenta TBC"}

def display_stream(stream: str) -> str:
    norm = normalize_stream(stream)
    if norm in {"ARD", "ZDF", "ARD/ZDF"}:
        return norm
    return "TBD"

def unresolved_text(text: str) -> bool:
    lower = clean(text).lower()
    terms = [
        "winner", "loser", "runner-up", "runner up",
        "1st group", "2nd group", "3rd group",
        "best third", "best 3rd",
        "sieger", "verlierer", "match ", "spiel "
    ]
    return any(term in lower for term in terms)

def display_team(text: str) -> str:
    if not clean(text) or unresolved_text(text):
        return "TBD"
    return clean(text)

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
    if stage_code(m) in {"R32", "R16", "QF", "SF", "3rd Place", "Finals"}:
        return timedelta(hours=3)
    return timedelta(hours=2)

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
    matches = []
    for row in read_csv(MANUAL_FIXTURES_CSV):
        m = row_to_match(row, FIFA_FIXTURES_URL)
        if m:
            matches.append(m)
    return sorted(matches, key=lambda m: m.match_no)

def merge_matches(base: list[Match], updates: list[Match], label: str) -> list[Match]:
    by_no = {m.match_no: m for m in base}
    for u in updates:
        existing = by_no.get(u.match_no)
        if existing is None:
            by_no[u.match_no] = u
            continue

        # Source updates override fallback values only when non-empty.
        for field in ["date", "time", "round", "group", "team_a", "team_b", "stream", "source_url"]:
            value = clean(getattr(u, field))
            if value:
                setattr(existing, field, value)

        note = clean(u.notes) or label
        existing.notes = (clean(existing.notes) + f" | {note}").strip(" |")
    return sorted(by_no.values(), key=lambda m: m.match_no)

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

def apply_overrides(matches: list[Match]) -> list[Match]:
    by_no = {m.match_no: m for m in matches}

    for row in read_csv(OVERRIDES_CSV):
        try:
            no = int(clean(row.get("match_no")))
        except ValueError:
            continue

        existing = by_no.get(no)
        if existing is None:
            existing = Match(no, "", "", "", "", "", "", "TBC", "data/overrides.csv", "Created by override")
            by_no[no] = existing

        for field in ["date", "time", "round", "group", "team_a", "team_b", "notes", "include"]:
            value = clean(row.get(field))
            if value:
                setattr(existing, field, value)

        if clean(row.get("stream")):
            existing.stream = normalize_stream(row.get("stream"))

        if clean(row.get("source_url")):
            existing.source_url = clean(row.get("source_url"))

    return sorted(by_no.values(), key=lambda m: m.match_no)

def html_to_text(html_text: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>", " ", html_text)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", "\n", text)
    text = html.unescape(text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def fetch_url(url: str, debug_path: Path) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; WC2026CalendarBot/3.0; +https://github.com/)",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    debug_path.write_text(response.text[:2_000_000], encoding="utf-8")
    return response.text

def parse_iso_datetime(value: str) -> tuple[str, str] | None:
    text = clean(value)
    if not text:
        return None
    candidates = [text, text.replace("Z", "+00:00") if text.endswith("Z") else text]
    for cand in candidates:
        try:
            dt = datetime.fromisoformat(cand)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            local = dt.astimezone(TZ)
            return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")
        except ValueError:
            pass
    return None

def walk_json(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk_json(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from walk_json(x)

def extract_json_candidates(html_text: str) -> list[object]:
    out = []
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.DOTALL)
    if m:
        try:
            out.append(json.loads(html.unescape(m.group(1))))
        except json.JSONDecodeError:
            pass
    for body in re.findall(r'<script[^>]+type=["\']application/(?:ld\+)?json["\'][^>]*>(.*?)</script>', html_text, re.DOTALL):
        try:
            out.append(json.loads(html.unescape(body)))
        except json.JSONDecodeError:
            pass
    return out

def first_dict_value(d: dict, keys: list[str]):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return ""

def team_name(obj) -> str:
    if isinstance(obj, str):
        return clean(obj)
    if isinstance(obj, dict):
        for k in ["name", "shortName", "displayName", "countryName", "teamName", "abbreviation"]:
            if obj.get(k):
                return clean(obj[k])
    return ""

def fifa_object_to_match(d: dict) -> Match | None:
    raw_no = first_dict_value(d, ["matchNumber", "matchNo", "match_no", "matchIndex", "number"])
    if not raw_no:
        return None
    try:
        no = int(re.search(r"\d+", str(raw_no)).group())
    except Exception:
        return None

    parsed_dt = None
    for k in ["date", "startDate", "kickoff", "kickOff", "kickOffTime", "utcDate", "matchDate"]:
        parsed_dt = parse_iso_datetime(clean(d.get(k)))
        if parsed_dt:
            break
    if not parsed_dt:
        return None

    home = team_name(first_dict_value(d, ["homeTeam", "home", "teamA", "contestantHome", "homeContestant"]))
    away = team_name(first_dict_value(d, ["awayTeam", "away", "teamB", "contestantAway", "awayContestant"]))
    home = home or clean(first_dict_value(d, ["homeTeamName", "homeName", "teamAName"]))
    away = away or clean(first_dict_value(d, ["awayTeamName", "awayName", "teamBName"]))

    stream = "TBC"
    for k in ["broadcasters", "broadcasts", "whereToWatch", "channels", "tvChannels", "media"]:
        if k in d:
            stream = normalize_stream(json.dumps(d[k], ensure_ascii=False))
            break

    return Match(
        match_no=no,
        date=parsed_dt[0],
        time=parsed_dt[1],
        round=clean(first_dict_value(d, ["round", "stage", "phase", "competitionStage"])),
        group=clean(first_dict_value(d, ["group", "groupName", "pool"])),
        team_a=home,
        team_b=away,
        stream=stream,
        source_url=FIFA_FIXTURES_URL,
        notes="Updated from FIFA",
    )

def fetch_fifa_updates() -> list[Match]:
    try:
        html_text = fetch_url(FIFA_FIXTURES_URL, FIFA_RAW_DEBUG)
    except Exception as exc:
        print(f"[WARN] FIFA fetch failed: {exc}")
        return []

    matches = {}
    for candidate in extract_json_candidates(html_text):
        for d in walk_json(candidate):
            m = fifa_object_to_match(d)
            if m:
                matches[m.match_no] = m
    return sorted(matches.values(), key=lambda m: m.match_no)

MONTHS_DE = {
    "januar": "01", "februar": "02", "märz": "03", "maerz": "03", "april": "04",
    "mai": "05", "juni": "06", "juli": "07", "august": "08", "september": "09",
    "oktober": "10", "november": "11", "dezember": "12",
}

def parse_german_date(text: str) -> str:
    s = clean(text)
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.", s)
    if m:
        return f"2026-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})\.?\s+([A-Za-zÄÖÜäöüß]+)", s)
    if m:
        month = MONTHS_DE.get(m.group(2).lower())
        if month:
            return f"2026-{month}-{int(m.group(1)):02d}"
    return ""

TEAM_DE_TO_EN = {
    "Südafrika": "South Africa", "Kanada": "Canada", "Deutschland": "Germany",
    "Brasilien": "Brazil", "Japan": "Japan", "Paraguay": "Paraguay",
    "Niederlande": "Netherlands", "Marokko": "Morocco",
    "Elfenbeinküste": "Ivory Coast", "Norwegen": "Norway",
    "Frankreich": "France", "Schweden": "Sweden", "Mexiko": "Mexico",
    "Ecuador": "Ecuador", "England": "England", "DR Kongo": "DR Congo",
    "Belgien": "Belgium", "Senegal": "Senegal", "Sénégal": "Senegal",
    "USA": "USA", "Bosnien-Herzegowina": "Bosnia-Herzegovina",
    "Spanien": "Spain", "Österreich": "Austria", "Portugal": "Portugal",
    "Kroatien": "Croatia", "Schweiz": "Switzerland", "Algerien": "Algeria",
    "Australien": "Australia", "Ägypten": "Egypt", "Argentinien": "Argentina",
    "Kap Verde": "Cape Verde", "Kolumbien": "Colombia", "Ghana": "Ghana",
}

def normalize_team_name(name: str) -> str:
    return TEAM_DE_TO_EN.get(clean(name), clean(name))

def infer_round_from_context(before_text: str) -> str:
    lower = before_text.lower()
    choices = [
        ("spiel um platz drei", "Third-place match"),
        ("halbfinale", "Semi-final"),
        ("viertelfinale", "Quarter-final"),
        ("achtelfinale", "Round of 16"),
        ("sechzehntelfinale", "Round of 32"),
        ("vorrunde", "Group Match"),
        ("finale", "Final"),
    ]
    best_pos, best_label = -1, ""
    for needle, label in choices:
        pos = lower.rfind(needle)
        if pos > best_pos:
            best_pos, best_label = pos, label
    return best_label

def parse_sportschau_like_text(text: str, source_url: str) -> list[Match]:
    """
    Best-effort parser for German public broadcaster schedule pages.
    It is intentionally broad, because these pages may change their HTML layout.
    """
    matches = {}

    # Example row patterns:
    # 28.06. 21:00 Südafrika - Kanada (Spiel 73) ARD
    # 30. Juni 18:00 Elfenbeinküste - Norwegen (Spiel 81) ZDF
    pattern = re.compile(
        r"(?P<date>(?:\d{1,2}\.\d{1,2}\.|(?:\d{1,2}\.?\s+[A-Za-zÄÖÜäöüß]+)))\s+"
        r"(?P<time>\d{1,2}:\d{2})\s+"
        r"(?P<a>[^\\n()]{2,60}?)\s*[-–]\s*(?P<b>[^\\n()]{2,60}?)\s*"
        r"\(Spiel\s+(?P<no>\d+)\)"
        r"(?P<trail>[^\\n]{0,120})",
        re.IGNORECASE
    )

    for m in pattern.finditer(text):
        no = int(m.group("no"))
        date_s = parse_german_date(m.group("date"))
        if not date_s:
            continue
        trail = m.group("trail")
        stream = normalize_stream(trail)
        if stream == "TBC":
            if re.search(r"\bARD\b|Das Erste", trail, re.IGNORECASE):
                stream = "ARD"
            elif re.search(r"\bZDF\b", trail, re.IGNORECASE):
                stream = "ZDF"

        matches[no] = Match(
            match_no=no,
            date=date_s,
            time=f"{int(m.group('time').split(':')[0]):02d}:{m.group('time').split(':')[1]}",
            round=infer_round_from_context(text[:m.start()]),
            group="",
            team_a=normalize_team_name(m.group("a")),
            team_b=normalize_team_name(m.group("b")),
            stream=stream,
            source_url=source_url,
            notes=f"Updated from {source_url}",
        )

    return sorted(matches.values(), key=lambda m: m.match_no)

def fetch_sportschau_updates() -> list[Match]:
    updates = []
    for url, debug in [(SPORTSCHAU_SCHEDULE_URL, SPORTSCHAU_RAW_DEBUG), (SPORTSCHAU_STREAMS_URL, SPORTSCHAU_RAW_DEBUG)]:
        try:
            html_text = fetch_url(url, debug)
            text = html_to_text(html_text)
            updates.extend(parse_sportschau_like_text(text, url))
        except Exception as exc:
            print(f"[WARN] Sportschau fetch/parse failed for {url}: {exc}")

    by_no = {}
    for m in updates:
        by_no[m.match_no] = m
    return sorted(by_no.values(), key=lambda m: m.match_no)

def fetch_zdf_updates() -> list[Match]:
    try:
        html_text = fetch_url(ZDF_SCHEDULE_URL, ZDF_RAW_DEBUG)
        text = html_to_text(html_text)
        return parse_sportschau_like_text(text, ZDF_SCHEDULE_URL)
    except Exception as exc:
        print(f"[WARN] ZDF fetch/parse failed: {exc}")
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

def excluded_time_window(time_hhmm: str) -> bool:
    if not EXCLUDE_01_TO_12:
        return False
    t = datetime.strptime(time_hhmm, "%H:%M").time()
    return (
        (t.hour > 1 or (t.hour == 1 and t.minute >= 0))
        and
        (t.hour < 12 or (t.hour == 12 and t.minute == 0))
    )

def included_matches(matches: list[Match], start_date: date) -> tuple[list[Match], list[dict]]:
    included = []
    audit = []

    for m in sorted(matches, key=lambda x: x.match_no):
        decision = ""
        md = match_date(m)

        if clean(m.include).lower() == "no":
            decision = "excluded by include=no override"
        elif md is None or not valid_datetime(m):
            decision = "excluded because date/time invalid"
        elif ONLY_FROM_TODAY_ONWARDS and md < start_date:
            decision = f"excluded because {m.date} is before {start_date.isoformat()}"
        elif excluded_time_window(m.time):
            decision = "excluded by time filter"
        elif clean(m.include).lower() == "yes":
            included.append(m)
            decision = "included by include=yes override"
        elif is_magenta_only(m.stream):
            decision = "excluded because confirmed MagentaTV only"
        elif is_confirmed_free_tv(m.stream):
            included.append(m)
            decision = "included because confirmed ARD/ZDF"
        elif INCLUDE_BROADCASTER_UNKNOWN_AS_TBD and is_unknown_or_candidate_stream(m.stream):
            included.append(m)
            decision = "included as broadcaster TBD/free-TV candidate"
        else:
            decision = f"excluded because stream not eligible: {m.stream}"

        audit.append({
            "match_no": m.match_no,
            "date": m.date,
            "time": m.time,
            "title": event_title(m),
            "raw_fixture": f"{m.team_a} vs {m.team_b}",
            "raw_stream": m.stream,
            "decision": decision,
        })

    return sorted(included, key=lambda m: (m.date, m.time, m.match_no)), audit

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
        "PRODID:-//Damanjit Singh//WC2026 Robust Planning Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{CALENDAR_NAME}",
        "X-WR-TIMEZONE:Europe/Berlin",
    ]

    for m in matches:
        start_local = datetime.strptime(f"{m.date} {m.time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        end_local = start_local + event_duration(m)

        title = event_title(m)
        description = (
            f"Match No.: {m.match_no}\\n"
            f"Stage: {stage_code(m)}\\n"
            f"Teams: {fixture_title(m)}\\n"
            f"Raw teams/source slot: {m.team_a} vs {m.team_b}\\n"
            f"Broadcaster: {display_stream(m.stream)}\\n"
            f"Raw broadcaster value: {m.stream}\\n"
            f"Kickoff Germany: {start_local.strftime('%d.%m.%Y %H:%M')}\\n"
            f"Source: {m.source_url}\\n"
            f"Notes: {m.notes}"
        )

        # Stable UID per match number. This is important so Apple updates existing events.
        uid = f"wc2026-match-{m.match_no}@singhdj1996.github.io"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{ics_escape(title)}",
            f"DESCRIPTION:{ics_escape(description)}",
            f"LAST-MODIFIED:{stamp}",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")

    text = "\r\n".join(fold_ics_line(line) for line in lines) + "\r\n"
    OUT_ICS.write_bytes(text.encode("utf-8"))

def write_status(included: list[Match], audit: list[dict], start_date: date, source_counts: dict) -> None:
    status = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "calendar_name": CALENDAR_NAME,
        "start_date_europe_berlin": start_date.isoformat(),
        "rules": {
            "only_from_today_onwards": ONLY_FROM_TODAY_ONWARDS,
            "include_broadcaster_unknown_as_tbd": INCLUDE_BROADCASTER_UNKNOWN_AS_TBD,
            "include_unknown_teams_as_tbd": INCLUDE_UNKNOWN_TEAMS_AS_TBD,
            "exclude_magenta_only": True,
            "stable_uid_per_match": True,
        },
        "source_counts": source_counts,
        "included_count": len(included),
        "included_matches": [asdict(m) | {"calendar_title": event_title(m)} for m in included],
        "audit": audit,
    }
    OUT_STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

def write_index(included: list[Match], start_date: date, source_counts: dict) -> None:
    rows = "\n".join(
        f"<tr><td>{m.match_no}</td><td>{html.escape(m.date)}</td><td>{html.escape(m.time)}</td>"
        f"<td>{html.escape(event_title(m))}</td><td>{html.escape(clean(m.source_url))}</td></tr>"
        for m in included
    )

    OUT_INDEX.write_text(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(CALENDAR_NAME)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 1200px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    code {{ background: #f4f4f4; padding: 2px 4px; }}
  </style>
</head>
<body>
  <h1>{html.escape(CALENDAR_NAME)}</h1>
  <p><strong>Last generated:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
  <p><strong>Start date Europe/Berlin:</strong> {start_date.isoformat()}</p>
  <p><strong>Included events:</strong> {len(included)}</p>
  <p><strong>Source counts:</strong> {html.escape(json.dumps(source_counts))}</p>
  <p><a href="wc2026.ics">Open/download wc2026.ics</a></p>
  <p><a href="status.json">Open status.json</a></p>
  <h2>Calendar events</h2>
  <table>
    <thead><tr><th>Match</th><th>Date</th><th>Time</th><th>Calendar title</th><th>Source</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
""", encoding="utf-8")

def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    start_date = berlin_today()

    matches = read_manual_fixtures()
    source_counts = {"manual_fixtures": len(matches)}

    # Seed local broadcaster values first.
    matches = apply_broadcaster_seed(matches)

    # Live sources override fallback values when parseable.
    fifa = fetch_fifa_updates()
    sportschau = fetch_sportschau_updates()
    zdf = fetch_zdf_updates()

    source_counts.update({
        "fifa_updates": len(fifa),
        "sportschau_updates": len(sportschau),
        "zdf_updates": len(zdf),
    })

    # Priority: fallback -> FIFA -> Sportschau -> ZDF -> manual overrides.
    matches = merge_matches(matches, fifa, "FIFA")
    matches = merge_matches(matches, sportschau, "Sportschau")
    matches = merge_matches(matches, zdf, "ZDF")
    matches = apply_overrides(matches)

    included, audit = included_matches(matches, start_date)

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
