# WC2026 Robust Planning Calendar V2

This version fixes the previous problem where future matches stayed `TBD vs TBD - TBD` even though Sportschau already had the schedule.

## Key behavior

- Runs every 6 hours via GitHub Actions.
- Keeps future planning slots.
- Updates known teams from Sportschau/ZDF pages.
- Updates broadcaster if ARD/ZDF becomes known.
- Excludes only confirmed MagentaTV-only slots.
- Unknown broadcaster is shown as `TBD`.
- Unknown teams are shown as `TBD vs TBD`.
- Uses stable UIDs per match number so Apple Calendar updates existing events.

## Event title examples

```text
FIFA R32 - South Africa vs Canada - ARD
FIFA R32 - France vs Sweden - TBD
FIFA R16 - TBD vs TBD - TBD
FIFA Finals - TBD vs TBD - ZDF
```

## Files to upload

Replace your repo with the files in this package, especially:

```text
generate_calendar.py
requirements.txt
README.md
data/manual_fixtures.csv
data/broadcasters.csv
data/overrides.csv
.github/workflows/build-calendar.yml
```

Then run:

```text
GitHub → Actions → Build WC2026 calendar → Run workflow
```

Your iPhone subscription URL stays the same.
