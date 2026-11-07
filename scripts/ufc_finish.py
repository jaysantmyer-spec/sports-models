"""Wrap the UFC Oracle report for the Sports Models site.

Usage: python scripts/ufc_finish.py REPORT_HTML UPCOMING_CSV STATUS

Adds a doctype, phone viewport, a link back to the index, when it was
built, and a warning banner when the card shown has already happened
(which means fresh data could not be scraped this run).
"""
import csv
import datetime as dt
import html
import sys

report, upcoming, status = sys.argv[1], sys.argv[2], sys.argv[3]
page = open(report, encoding="utf-8").read()

today = dt.date.today()
dates = []
try:
    with open(upcoming, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                dates.append(dt.date.fromisoformat(row["event_date"][:10]))
            except (KeyError, ValueError):
                pass
except FileNotFoundError:
    pass

future = [d for d in dates if d >= today]
built = dt.datetime.now(dt.timezone.utc).strftime("%b %d, %Y %H:%M UTC")

bar = (
    '<div style="max-width:960px;margin:0 auto;padding:10px 16px 0;'
    'font:14px/1.4 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">'
    '<a href="index.html" style="color:inherit;opacity:.75;text-decoration:none">'
    '&larr; Sports Models</a>'
    f'<span style="float:right;opacity:.6">Updated {html.escape(built)}</span></div>'
)
if not future:
    last = max(dates).isoformat() if dates else "unknown"
    bar += (
        '<div style="max-width:960px;margin:10px auto 0;padding:0 16px">'
        '<div style="background:#F7DDDD;color:#9B2C2C;border-radius:10px;padding:10px 14px;'
        'font:600 14px/1.4 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">'
        f'Old card: this event ({html.escape(last)}) has already happened. '
        'The next card could not be pulled from UFCStats on the last run '
        f'({html.escape(status)}). Do not bet off this page until it updates.'
        '</div></div>'
    )

head = (
    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
)
if "<!DOCTYPE" not in page[:200].upper() and "<!doctype" not in page[:200]:
    page = head + page
if "</style>" in page:
    page = page.replace("</style>", "</style>\n" + bar, 1)
else:
    page = bar + page

open(report, "w", encoding="utf-8").write(page)
print(f"finished {report}: {len(dates)} bouts listed, next card in future: {bool(future)}")
