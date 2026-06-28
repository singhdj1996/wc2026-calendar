# WC2026 Dynamic Calendar - Today Onwards Version

This is the updated GitHub package for your requirement:

- One-time setup on laptop
- Update later from iPhone if required
- Calendar keeps only matches from today onward
- Date logic uses Europe/Berlin time
- Calendar includes only matches streamed in Germany on ARD, ZDF, or ARD/ZDF
- Event title format: `FIFA Mxx - Team A vs Team B`

## What changed in this version

The generator now has:

```python
ONLY_FROM_TODAY_ONWARDS = True
```

Every time GitHub Actions runs, it calculates today's date in Europe/Berlin and excludes earlier matches.

Example:
If today is 2026-06-28, matches dated before 2026-06-28 are removed from the generated calendar.

## Files you normally upload/replace

Replace these in your GitHub repository:

```text
generate_calendar.py
data/manual_fixtures.csv
data/broadcasters.csv
data/overrides.csv
.github/workflows/build-calendar.yml
requirements.txt
README.md
```

The generated files in `docs/` are included too, but GitHub Actions will regenerate them after you run the workflow.

## How to update from iPhone later

Edit only:

```text
data/overrides.csv
```

Example:

```csv
match_no,date,time,team_a,team_b,stream,include,notes,source_url
73,2026-06-28,21:00,Germany,Brazil,ZDF,yes,Knockout team confirmed,
```

Then commit the change in GitHub. The workflow will rebuild the calendar.

## How to run after uploading

1. Go to your GitHub repository.
2. Open **Actions**.
3. Open **Build WC2026 calendar**.
4. Click **Run workflow**.
5. Wait for the green tick.
6. Open your GitHub Pages calendar page again.

## Calendar URL

Your subscription URL remains:

```text
https://YOUR_USERNAME.github.io/wc2026-calendar/wc2026.ics
```

You do not need to re-subscribe if you already subscribed to this URL.
