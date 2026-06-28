# WC2026 Robust Planning Calendar

This is the planning-first version of the FIFA World Cup 2026 calendar.

It is designed to solve the earlier problem:

- Do not exclude knockout matches just because teams are unknown.
- Do not exclude future slots just because broadcaster is not confirmed yet.
- Exclude only matches confirmed as MagentaTV-only.
- Show placeholders as `TBD vs TBD`.
- Show broadcaster placeholders as `TBD`.
- Update every 6 hours through GitHub Actions.
- Use stable calendar event IDs so Apple Calendar updates existing events instead of duplicating them.

## Event title examples

```text
FIFA R16 - TBD vs TBD - ZDF
FIFA R32 - Canada vs RSA - ZDF
FIFA R16 - TBD vs TBD - TBD
FIFA Finals - TBD vs TBD - ZDF
```

## Data logic

Priority order:

```text
manual_fixtures.csv fallback
↓
FIFA parser updates
↓
Sportschau parser updates
↓
ZDF parser updates
↓
overrides.csv manual fixes
```

Rules:

```text
Confirmed ARD/ZDF        → included
Unknown broadcaster TBC  → included as TBD
Future unresolved teams  → included as TBD vs TBD
Confirmed Magenta-only   → excluded
Past matches             → excluded
```

## Upload instructions

Replace/upload the complete package to your GitHub repository.

Then run:

```text
GitHub → Actions → Build WC2026 calendar → Run workflow
```

Your subscribed iPhone calendar URL stays the same:

```text
https://YOUR_USERNAME.github.io/wc2026-calendar/wc2026.ics
```

## Updating from iPhone

Normally you should not need to update anything manually.

If a page layout changes or you want to force-correct a match, edit only:

```text
data/overrides.csv
```

Example:

```csv
match_no,date,time,round,group,team_a,team_b,stream,include,notes,source_url
73,2026-06-28,21:00,Round of 32,,South Africa,Canada,ARD,yes,Forced correction,https://www.sportschau.de/
```

## Important limitation

No scraper can be mathematically guaranteed forever because FIFA, ARD, Sportschau or ZDF can change their website structure. This setup is designed to be fail-safe: if live parsing fails, the fallback fixture slots remain in your calendar as planning placeholders unless they are known MagentaTV-only.
