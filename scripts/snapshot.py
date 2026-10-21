"""Fetch Kalshi + Polymarket public data and write data/kalshi.json for the static site.
Runs in GitHub Actions (open network). The HTML apps use it when the browser can't call Kalshi directly."""
import json, time, urllib.request, urllib.parse, os, sys

K = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
UA = {"User-Agent": "sports-models-snapshot/1.0"}
SKIP_CATEGORIES = {"Sports"}          # sports has its own apps; it is ~90% of Kalshi's market count

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
KEEP_ALL_CATEGORIES = {"Climate and Weather"}   # weather brackets are needed even at zero volume
EV_FIELDS = ["event_ticker","series_ticker","title","sub_title","category","mutually_exclusive"]

def trim(d, fields): return {k: d.get(k) for k in fields if d.get(k) is not None}

def main():
    t0 = time.time()
    raw_events = paged("/events", "events", {"status": "open", "limit": 200, "with_nested_markets": "true"})
    events, markets, skipped = [], [], 0
    for e in raw_events:
        if e.get("category") in SKIP_CATEGORIES:
            skipped += 1; continue
        ms = e.get("markets") or []
        keep_all = e.get("category") in KEEP_ALL_CATEGORIES
        kept = []
        for m in ms:
            # newer API reports fixed-point strings; normalise to numbers
            for k in ("volume","open_interest"):
                if m.get(k) is None and m.get(k+"_fp") is not None:
                    try: m[k] = int(float(m[k+"_fp"]))
                    except Exception: pass
            m.setdefault("event_ticker", e.get("event_ticker"))
            # prefer integer cents; fall back to dollars if cents absent
            for k in ("yes_ask","yes_bid","no_ask","last_price"):
                if m.get(k) is None and m.get(k+"_dollars") is not None:
                    try: m[k] = round(float(m[k+"_dollars"])*100)
                    except Exception: pass
            if m.get("subtitle") and not m.get("yes_sub_title"): m["yes_sub_title"] = m["subtitle"]
            ya, yb = m.get("yes_ask"), m.get("yes_bid")
            quoted = (yb or 0) > 0 or (ya is not None and 0 < ya < 100)
            if not keep_all and not (m.get("volume") or m.get("open_interest") or quoted): continue
            kept.append(trim(m, MK_FIELDS))
        if not kept: continue
        events.append(trim(e, EV_FIELDS)); markets += kept
    # weather series are their own events (category Climate and Weather) so they are already included
    since = int(time.time()) - 2*86400
    settled = paged("/markets", "markets", {"status": "settled", "limit": 1000, "min_close_ts": since}, max_pages=30)
    poly = []
    for off in range(0, 4000, 100):
        j = get(f"{GAMMA}/markets?closed=false&active=true&limit=100&offset={off}&order=volume24hr&ascending=false")
        if not j: break
        poly += [{k: m.get(k) for k in ("id","question","endDate","outcomes","outcomePrices","clobTokenIds","volume") if m.get(k) is not None} for m in j]
        if len(j) < 100: break
        time.sleep(0.1)
    snap = {"ts": int(time.time()*1000), "events": events, "markets": markets,
            "settled": [trim(m, ["ticker","result","last_price"]) for m in settled if m.get("result")],
            "poly": poly}
    os.makedirs("data", exist_ok=True)
    with open("data/kalshi.json", "w") as f: json.dump(snap, f, separators=(",", ":"))
    cats = {}
    for e in events: cats[e.get("category")] = cats.get(e.get("category"), 0) + 1
    meta = {"ts": snap["ts"], "events": len(events), "events_skipped_sports": skipped, "markets": len(markets),
            "settled": len(settled), "poly": len(poly), "categories": cats,
            "size_mb": round(os.path.getsize("data/kalshi.json")/1e6, 1), "seconds": round(time.time()-t0),
            "sample_market": markets[0] if markets else None}
    with open("data/meta.json", "w") as f: json.dump(meta, f, indent=1)
    print(json.dumps({k: v for k, v in meta.items() if k != "sample_market"}))

if __name__ == "__main__":
    main()
