# WC2026 FIFA Dynamic Calendar

This project creates a subscribable `.ics` calendar feed for the FIFA World Cup 2026.

Target workflow:

- One-time setup on your MacBook
- Calendar is hosted through GitHub Pages
- GitHub Actions updates the calendar regularly
- You can make small manual fixes from your iPhone by editing `data/overrides.csv`
- Apple Calendar subscribes to the generated `docs/wc2026.ics`

## Important source reality

The script treats FIFA as the primary source for fixtures.

Official FIFA pages currently provide the official match schedule and "where to watch" context, but German match-level ARD/ZDF assignment may not always be exposed in a clean machine-readable way. Therefore the pipeline has this priority:

1. Try to fetch/parse the official FIFA schedule page.
2. Apply local broadcaster mapping from `data/broadcasters.csv`.
3. Apply your phone-editable fixes from `data/overrides.csv`.
4. Generate `docs/wc2026.ics`.

This means the setup is dynamic for fixture/team updates when FIFA data is parseable, and still safe because manual overrides always win.

## Calendar event title format

`FIFA M01 - Team A vs Team B`

Examples:

`FIFA M01 - Mexico vs South Africa`

`FIFA M104 - Winner SF1 vs Winner SF2`

By default unresolved placeholders are skipped, because you asked for team names as teams advance.

## Files

```text
.github/workflows/build-calendar.yml   GitHub automation
data/manual_fixtures.csv               fallback schedule data
data/broadcasters.csv                  ARD/ZDF/Magenta mapping
data/overrides.csv                     phone-editable corrections
docs/wc2026.ics                        generated calendar feed
docs/index.html                        simple public status page
generate_calendar.py                   generator script
requirements.txt                       Python dependency list
README.md                              this guide
```

## Step-by-step setup on MacBook

### 1. Create GitHub account / sign in

Go to GitHub and sign in.

### 2. Create a new repository

Create a repository named:

```text
wc2026-calendar
```

Recommended:

- Visibility: Public
- Add README: No, because this package already includes one

### 3. Download this starter package

Unzip it on your MacBook.

You should see:

```text
.github/
data/
docs/
generate_calendar.py
requirements.txt
README.md
.gitignore
```

### 4. Upload files to GitHub

Option A: easiest through browser

1. Open your GitHub repo.
2. Click **Add file**.
3. Click **Upload files**.
4. Drag all unzipped files/folders into the browser.
5. Commit changes.

Important: the `.github` folder must be uploaded too. If macOS hides dot-folders, press:

```text
Command + Shift + .
```

inside Finder to show hidden files.

### 5. Enable GitHub Pages

1. Open your repository on GitHub.
2. Go to **Settings**.
3. Go to **Pages**.
4. Under **Build and deployment**:
   - Source: **Deploy from a branch**
   - Branch: **main**
   - Folder: **/docs**
5. Click **Save**.

After a few minutes, your site will be available at:

```text
https://YOUR_USERNAME.github.io/wc2026-calendar/
```

Your calendar subscription URL will be:

```text
https://YOUR_USERNAME.github.io/wc2026-calendar/wc2026.ics
```

### 6. Run the GitHub Action once

1. In your repository, click **Actions**.
2. Click **Build WC2026 calendar**.
3. Click **Run workflow**.
4. Wait until it shows a green tick.

This generates/updates:

```text
docs/wc2026.ics
docs/index.html
docs/status.json
```

### 7. Test the calendar URL

Open this in Safari:

```text
https://YOUR_USERNAME.github.io/wc2026-calendar/
```

You should see a status page and a link to `wc2026.ics`.

### 8. Subscribe on iPhone

On iPhone:

1. Open **Calendar**
2. Tap **Calendars**
3. Tap **Add Calendar**
4. Tap **Add Subscription Calendar**
5. Paste:

```text
https://YOUR_USERNAME.github.io/wc2026-calendar/wc2026.ics
```

6. Tap **Subscribe**
7. Name it `FIFA WC 2026`
8. Choose iCloud as location
9. Save

## Updating from iPhone later

For simple corrections, edit only:

```text
data/overrides.csv
```

Example:

```csv
match_no,date,time,team_a,team_b,stream,include,notes
73,2026-06-28,21:00,Germany,Brazil,ZDF,yes,Knockout team update
```

How to edit from iPhone:

1. Open GitHub app or GitHub in Safari.
2. Open your repo.
3. Open `data/overrides.csv`.
4. Tap edit pencil.
5. Add/change rows.
6. Commit changes.

GitHub Actions runs automatically and updates the calendar feed.

## CSV rules

### `data/broadcasters.csv`

Use this for broadcaster mapping:

```csv
match_no,stream,source_url,notes
1,ZDF,https://www.fifa.com/,Official or confirmed source
2,MagentaTV,https://www.fifa.com/,Magenta only
3,ARD,https://www.fifa.com/,Official or confirmed source
```

Allowed stream values:

```text
ARD
ZDF
ARD/ZDF
MagentaTV
MagentaTV only
TBC
```

Only rows with `ARD`, `ZDF`, or `ARD/ZDF` are included.

### `data/overrides.csv`

This file wins over everything else.

Use it for:

- confirmed knockout teams
- corrected kickoff times
- broadcaster corrections
- forcing a match in/out

Columns:

```text
match_no,date,time,team_a,team_b,stream,include,notes
```

`include` can be:

```text
yes
no
```

Leave a cell empty if you do not want to override that field.

## Local testing on MacBook

Optional but useful.

Install Python 3 if needed, then in Terminal:

```bash
cd path/to/wc2026-calendar
python3 -m pip install -r requirements.txt
python3 generate_calendar.py
```

Then open:

```text
docs/index.html
```

or import:

```text
docs/wc2026.ics
```

## Configuration

At the top of `generate_calendar.py`, you can change:

```python
INCLUDE_UNRESOLVED = False
CALENDAR_NAME = "FIFA World Cup 2026 - ARD/ZDF"
```

Leave `INCLUDE_UNRESOLVED = False` if you only want real team names.

## Limitations

- FIFA may change website structure. If that happens, automatic parsing may fail.
- If FIFA does not expose ARD/ZDF match-level assignment, use `data/broadcasters.csv` or `data/overrides.csv`.
- iPhone subscribed calendars refresh on Apple's schedule; updates may not appear instantly.
