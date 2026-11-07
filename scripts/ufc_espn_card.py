"""Backup source for the next UFC card when UFCStats blocks the scrape.

Run from inside the fuzzy-happiness checkout:
    python ../scripts/ufc_espn_card.py [DEBUG_JSON_PATH]

Reads ESPN's public UFC scoreboard for the next five weeks, takes the soonest
card that hasn't happened yet, matches the fighters to the model's fight
history by name and saves it to data/upcoming.csv with the model's own helpers.
"""
import datetime as dt
import json
import os
import sys

import requests

sys.path.insert(0, os.getcwd())
from ufc_predictor import pipeline  # noqa: E402

today = dt.date.today()

# Nothing to do if the UFCStats scrape already found a card that hasn't happened.
try:
    import csv
    with open("data/upcoming.csv", encoding="utf-8") as f:
        if any(r.get("event_date", "")[:10] >= today.isoformat() for r in csv.DictReader(f)):
            print("Upcoming card already on file, ESPN backup not needed")
            sys.exit(0)
except FileNotFoundError:
    pass
end = today + dt.timedelta(days=35)
url = ("https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
       f"?dates={today:%Y%m%d}-{end:%Y%m%d}&limit=50")
data = requests.get(url, timeout=30, headers={"User-Agent": "sports-models-ufc"}).json()
if len(sys.argv) > 1:
    json.dump(data, open(sys.argv[1], "w"), indent=1)

events = data.get("events") or []


def day(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(
            dt.timezone(dt.timedelta(hours=-5))).date()
    except Exception:
        return None


events = [e for e in events if day(e.get("date", "")) and day(e["date"]) >= today]
events.sort(key=lambda e: e["date"])
if not events:
    sys.exit("ESPN: no upcoming UFC card found")
ev = events[0]
name, date = ev.get("name") or ev.get("shortName") or "UFC", day(ev["date"])

bouts = []
for i, c in enumerate(ev.get("competitions") or []):
    comp = sorted(c.get("competitors") or [], key=lambda x: x.get("order", 0))
    names = [(x.get("athlete") or {}).get("displayName") or (x.get("athlete") or {}).get("fullName") for x in comp]
    if len(names) != 2 or not all(names):
        continue
    rounds = ((c.get("format") or {}).get("regulation") or {}).get("periods")
    when = c.get("date") or c.get("startDate") or ""
    bouts.append((when, i, names, rounds))

# ESPN lists the early prelims first and the main event last.
bouts.sort(key=lambda b: (b[0], b[1]), reverse=True)
lines = []
for _, _, (a, b), rounds in bouts:
    lines.append(f"{a} vs {b}" + (" (5)" if rounds == 5 else ""))
if not lines:
    sys.exit(f"ESPN: {name} has no bouts listed yet")

card, notes = pipeline.card_from_text("\n".join(lines), name, date)
for n in notes:
    print("  ", n)
if card.empty:
    sys.exit(f"ESPN: none of the {len(lines)} bouts on {name} matched the fight history")
pipeline.save_manual_card(card)
print(f"ESPN card saved: {name} ({date}), {len(card)} of {len(lines)} bouts matched")
