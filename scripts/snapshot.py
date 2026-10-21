"""Fetch Kalshi + Polymarket public data and write data/kalshi.json for the static site.
Runs in GitHub Actions (open network). The HTML apps use it when the browser can't call Kalshi directly."""
import json, time, urllib.request, urllib.parse, os, sys

K = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
UA = {"User-Agent": "sports-models-snapshot/1.0"}

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print("retry", i, url[:90], e, file=sys.stderr); time.sleep(2 + 2*i)
    return None

def paged(path, key, params, max_pages=40):
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
        time.sleep(0.25)
    return out

MK_FIELDS = ["ticker","event_ticker","title","subtitle","yes_sub_title","status","result","close_time",
             "yes_ask","yes_bid","no_ask","no_bid","last_price","yes_ask_dollars","yes_bid_dollars","no_ask_dollars",
             "no_bid_dollars","last_price_dollars","volume","open_interest","strike_type","floor_strike","cap_strike"]
EV_FIELDS = ["event_ticker","series_ticker","title","sub_title","category","mutually_exclusive"]

def trim(d, fields): return {k: d.get(k) for k in fields if d.get(k) is not None}

def main():
    t0 = time.time()
    events = paged("/events", "events", {"status": "open", "limit": 200})
    markets = paged("/markets", "markets", {"status": "open", "limit": 1000})
    since = int(time.time()) - 4*86400
    settled = paged("/markets", "markets", {"status": "settled", "limit": 1000, "min_close_ts": since}, max_pages=15)
    poly = []
    for off in range(0, 3000, 500):
        j = get(f"{GAMMA}/markets?closed=false&active=true&limit=500&offset={off}")
        if not j: break
        poly += [{k: m.get(k) for k in ("id","question","endDate","outcomes","outcomePrices","clobTokenIds","volume") if m.get(k) is not None} for m in j]
        if len(j) < 500: break
    snap = {
        "ts": int(time.time()*1000),
        "events": [trim(e, EV_FIELDS) for e in events],
        "markets": [trim(m, MK_FIELDS) for m in markets],
        "settled": [trim(m, ["ticker","result","last_price","last_price_dollars","close_time"]) for m in settled],
        "poly": poly,
    }
    os.makedirs("data", exist_ok=True)
    with open("data/kalshi.json", "w") as f: json.dump(snap, f, separators=(",", ":"))
    meta = {"ts": snap["ts"], "events": len(events), "markets": len(markets), "settled": len(settled), "poly": len(poly),
            "sample_market": snap["markets"][0] if snap["markets"] else None,
            "sample_event": snap["events"][0] if snap["events"] else None,
            "market_statuses": sorted({str(m.get("status")) for m in markets})[:10]}
    with open("data/meta.json", "w") as f: json.dump(meta, f, indent=1)
    print(f"events {len(events)} markets {len(markets)} settled {len(settled)} poly {len(poly)} in {time.time()-t0:.0f}s, "
          f"{os.path.getsize('data/kalshi.json')/1e6:.1f} MB")

if __name__ == "__main__":
    main()
