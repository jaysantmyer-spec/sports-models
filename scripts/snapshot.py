"""Fetch Kalshi + Polymarket public data and write per-category JSON files under data/ for the static site.
Runs in GitHub Actions (open network). The HTML apps use these when the browser can't call Kalshi directly.

Files:
  data/index.json        {ts, categories:{name:{file,events,markets,kb}}, settled, poly}
  data/cat/<slug>.json   {ts, category, events:[...], markets:[...]}
  data/settled.json      {ts, settled:[{ticker,result,last_price}]}
  data/poly.json         {ts, poly:[...]}
"""
import json, time, urllib.request, urllib.parse, os, sys, re, shutil

K = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
UA = {"User-Agent": "sports-models-snapshot/1.0"}
SKIP_CATEGORIES = {"Sports"}            # sports has its own apps; it is ~90% of Kalshi's market count
KEEP_ALL_CATEGORIES = {"Climate and Weather"}   # weather brackets are needed even at zero volume
MIN_VOL = 100                           # contracts traded or open; weather exempt
WEATHER_SERIES = ["KXHIGHNY", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHLAX", "KXHIGHDEN", "KXHIGHAUS", "KXHIGHPHIL", "KXHIGHDAL"]

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except Exception as e:
            print("retry", i, url[:90], e, file=sys.stderr); time.sleep(2 + 2*i)
    return None

def paged(path, key, params, max_pages=400):
    out, cursor = [], ""
    for _ in range(max_pages):
        q = dict(params)
        if cursor: q["cursor"] = cursor
        j = get(f"{K}{path}?{urllib.parse.urlencode(q)}")
        if not j: break
        items = j.get(key) or []
        out += items
        cursor = j.get("cursor")
        if not cursor or not items: break
        time.sleep(0.2)
    return out

MK_FIELDS = ["ticker","event_ticker","yes_sub_title","result","close_time",
             "yes_ask","yes_bid","no_ask","last_price","volume","open_interest","strike_type","floor_strike","cap_strike"]
EV_FIELDS = ["event_ticker","series_ticker","title","sub_title","category","mutually_exclusive"]

def trim(d, fields): return {k: d.get(k) for k in fields if d.get(k) is not None}
def slug(c): return re.sub(r"[^a-z0-9]+", "-", (c or "other").lower()).strip("-") or "other"

def main():
    t0 = time.time(); ts = int(time.time()*1000)
    raw_events = paged("/events", "events", {"status": "open", "limit": 200, "with_nested_markets": "true"})
    bycat, skipped = {}, 0
    for e in raw_events:
        cat = e.get("category") or "Other"
        if cat in SKIP_CATEGORIES:
            skipped += 1; continue
        keep_all = cat in KEEP_ALL_CATEGORIES
        kept = []
        for m in e.get("markets") or []:
            for k in ("volume","open_interest"):
                if m.get(k) is None and m.get(k+"_fp") is not None:
                    try: m[k] = int(float(m[k+"_fp"]))
                    except Exception: pass
            for k in ("yes_ask","yes_bid","no_ask","last_price"):
                if m.get(k) is None and m.get(k+"_dollars") is not None:
                    try: m[k] = round(float(m[k+"_dollars"])*100)
                    except Exception: pass
            if m.get("subtitle") and not m.get("yes_sub_title"): m["yes_sub_title"] = m["subtitle"]
            if not keep_all and not ((m.get("volume") or 0) >= MIN_VOL or (m.get("open_interest") or 0) >= MIN_VOL): continue
            m.setdefault("event_ticker", e.get("event_ticker"))
            kept.append(trim(m, MK_FIELDS))
        if not kept: continue
        b = bycat.setdefault(cat, {"events": [], "markets": []})
        b["events"].append(trim(e, EV_FIELDS)); b["markets"] += kept

    since = int(time.time()) - 2*86400
    settled = [trim(m, ["ticker","result","last_price"]) for m in
               paged("/markets", "markets", {"status": "settled", "limit": 1000, "min_close_ts": since}, max_pages=12) if m.get("result")]
    # Weather brackets are a drop in the ocean of settled sports markets, so the generic query above misses them:
    # pull each weather series' settled markets directly (last 14 days) so the edge tracker can grade its picks.
    seen = {m["ticker"] for m in settled}
    for series in WEATHER_SERIES:
        for m in paged("/markets", "markets", {"series_ticker": series, "status": "settled", "limit": 200,
                                               "min_close_ts": int(time.time()) - 14*86400}, max_pages=5):
            if m.get("result") and m["ticker"] not in seen:
                for k in ("last_price",):
                    if m.get(k) is None and m.get(k+"_dollars") is not None:
                        try: m[k] = round(float(m[k+"_dollars"])*100)
                        except Exception: pass
                settled.append(trim(m, ["ticker","result","last_price"])); seen.add(m["ticker"])
        time.sleep(0.2)
    poly = []
    for off in range(0, 4000, 100):
        j = get(f"{GAMMA}/markets?closed=false&active=true&limit=100&offset={off}&order=volume24hr&ascending=false")
        if not j: break
        poly += [{k: m.get(k) for k in ("id","question","endDate","outcomes","outcomePrices","clobTokenIds","volume") if m.get(k) is not None} for m in j]
        if len(j) < 100: break
        time.sleep(0.1)

    shutil.rmtree("data", ignore_errors=True); os.makedirs("data/cat", exist_ok=True)
    index = {"ts": ts, "categories": {}, "settled": len(settled), "settled_weather": sum(1 for m in settled if m["ticker"].startswith("KXHIGH")),
             "poly": len(poly), "events_skipped_sports": skipped}
    for cat, b in sorted(bycat.items()):
        fn = f"cat/{slug(cat)}.json"
        with open("data/"+fn, "w") as f: json.dump({"ts": ts, "category": cat, **b}, f, separators=(",", ":"))
        index["categories"][cat] = {"file": fn, "events": len(b["events"]), "markets": len(b["markets"]),
                                    "kb": round(os.path.getsize("data/"+fn)/1024)}
    with open("data/settled.json", "w") as f: json.dump({"ts": ts, "settled": settled}, f, separators=(",", ":"))
    with open("data/poly.json", "w") as f: json.dump({"ts": ts, "poly": poly}, f, separators=(",", ":"))
    index["seconds"] = round(time.time()-t0)
    with open("data/index.json", "w") as f: json.dump(index, f, indent=1)
    print(json.dumps(index))

if __name__ == "__main__":
    main()
