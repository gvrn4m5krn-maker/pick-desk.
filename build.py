"""Pulls odds, finds value bets and arbitrage, writes docs/index.html.
Usage: ODDS_API_KEY=xxx python3 build.py        (live)
       python3 build.py --sample                (test with sample_odds.json)"""
import json, os, sys, html, datetime, urllib.request, urllib.parse

# ---- Settings you can edit -------------------------------------------------
SPORTS = {"americanfootball_nfl": "NFL", "americanfootball_ncaaf": "College football",
          "soccer_epl": "Premier League", "soccer_usa_mls": "MLS", "baseball_mlb": "MLB",
          "icehockey_nhl": "NHL", "basketball_nba": "NBA"}
REGIONS = "us"        # check your data provider's docs for the regions that cover your books
BOOKS = []            # e.g. ["draftkings", "fanduel"]; empty = every book returned. Set to apps you can use in Ontario.
SHARP = ["pinnacle"]  # if present, its no-vig prices are treated as the true chance
MIN_EDGE = 3.0        # points of edge needed to flag a value bet
MIN_PROB = 0.65       # "high-chance" plays need at least this fair win chance...
MIN_EDGE_SAFE = 0.5   # ...and a price at or better than fair (edge in points)
AUTO_DISCOVER = True  # True = check every sport in season, False = only SPORTS above
MAX_SPORTS = 12       # cap on sports checked per run (each one uses data-plan credits)
# ---------------------------------------------------------------------------

def dec(o): return 1 + o / 100 if o > 0 else 1 + 100 / -o
def imp(o): return 1 / dec(o)
def am(p):
    p = min(.97, max(.03, p))
    return round(-100 * p / (1 - p)) if p >= .5 else round(100 * (1 - p) / p)
def fa(o): return ("+" if o > 0 else "") + str(o)

def fetch(sport, key):
    q = urllib.parse.urlencode({"regions": REGIONS, "markets": "h2h", "oddsFormat": "american", "apiKey": key})
    with urllib.request.urlopen(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?{q}", timeout=30) as r:
        return json.load(r)

def discover(key):
    q = urllib.parse.urlencode({"apiKey": key})
    with urllib.request.urlopen(f"https://api.the-odds-api.com/v4/sports/?{q}", timeout=30) as r:
        found = [x for x in json.load(r) if x.get("active") and not x.get("has_outrights")]
    pref = [x for x in found if x["key"] in SPORTS] + [x for x in found if x["key"] not in SPORTS]
    return {x["key"]: x["title"] for x in pref[:MAX_SPORTS]}

def analyze(game, now):
    if game.get("commence_time", "") <= now: return None
    books = {}
    for b in game.get("bookmakers", []):
        if BOOKS and b["key"] not in BOOKS and b["key"] not in SHARP: continue
        for m in b.get("markets", []):
            if m["key"] == "h2h" and len(m["outcomes"]) >= 2:
                books[b["key"]] = {o["name"]: o["price"] for o in m["outcomes"]}
    if len(books) < 2: return None
    def devig(prices):
        t = sum(imp(p) for p in prices.values()); return {k: imp(p) / t for k, p in prices.items()}
    sharp = next((k for k in SHARP if k in books), None)
    names = list(next(iter(books.values())).keys())
    if sharp: fair = devig(books[sharp])
    else:
        ds = [devig(p) for p in books.values() if set(p) == set(names)]
        fair = {n: sum(d[n] for d in ds) / len(ds) for n in names}
    outs, bet_books = [], {k: v for k, v in books.items() if k not in SHARP or not BOOKS or k in BOOKS}
    for n in names:
        pr = [(b, p[n]) for b, p in bet_books.items() if n in p]
        if not pr: continue
        bk, best = max(pr, key=lambda x: dec(x[1]))
        outs.append({"name": n, "book": bk, "best": best, "fair": fair[n], "fair_odds": am(fair[n]),
                     "edge": (fair[n] - imp(best)) * 100})
    if len(outs) < len(names): return None
    s = sum(imp(o["best"]) for o in outs)
    return {"game": f'{game["away_team"]} at {game["home_team"]}', "start": game["commence_time"],
            "ref": sharp or "average of books", "outs": outs, "arb": (1 / s - 1) * 100 if s < 1 else 0}

def render(sections, errors, stamp):
    e = html.escape
    value = [(sp, g, o) for sp, gs in sections.items() for g in gs for o in g["outs"] if o["edge"] >= MIN_EDGE]
    value.sort(key=lambda x: -x[2]["edge"])
    arbs = sorted([(sp, g) for sp, gs in sections.items() for g in gs if g["arb"] > 0], key=lambda x: -x[1]["arb"])
    out = []
    hp = [(sp, g, o) for sp, gs in sections.items() for g in gs for o in g["outs"] if o["fair"] >= MIN_PROB and o["edge"] >= MIN_EDGE_SAFE]
    hp.sort(key=lambda x: (-x[2]["fair"], -x[2]["edge"]))
    out.append(f"<h2>High-chance plays</h2><p class=n>Fair win chance {MIN_PROB*100:.0f}%+ and a price at or better than fair. Most days there are few or none.</p>")
    if not hp: out.append("<p class=n>None right now.</p>")
    for sp, g, o in hp:
        out.append(f'<div class=c><b>{e(o["name"])}</b> <span class=ok>{o["fair"]*100:.0f}% to win</span><br>{e(g["game"])} ({e(sp)})<br>'
                   f'Best price <b>{fa(o["best"])}</b> at {e(o["book"])}. Fair odds {fa(o["fair_odds"])}. Edge {o["edge"]:+.1f} pts.<br><small>Bet only at {fa(o["fair_odds"])} or better. Check the price is live.</small></div>')
    out.append("<h2>Value bets</h2>" if value else "<h2>Value bets</h2><p class=n>None right now. Skipping is a good bet.</p>")
    for sp, g, o in value:
        out.append(f'<div class=c><b>{e(o["name"])}</b> <span class=ok>+{o["edge"]:.1f} pts</span><br>{e(g["game"])} ({e(sp)})<br>'
                   f'Best price <b>{fa(o["best"])}</b> at {e(o["book"])}. Fair odds {fa(o["fair_odds"])}.<br><small>Fair chance from {e(g["ref"])}. Check the price is live in your app.</small></div>')
    out.append("<h2>Arbitrage</h2>" + ("" if arbs else "<p class=n>None right now.</p>"))
    for sp, g in arbs:
        legs = "; ".join(f'{e(o["name"])} {fa(o["best"])} at {e(o["book"])}' for o in g["outs"])
        out.append(f'<div class=c><b>{g["arb"]:.1f}% locked</b> {e(g["game"])} ({e(sp)})<br>{legs}<br><small>Prices move fast; confirm both before betting.</small></div>')
    out.append("<h2>All games</h2>")
    for sp, gs in sections.items():
        if not gs: continue
        out.append(f"<h3>{e(sp)}</h3>")
        for g in gs:
            rows = "".join(f'<tr><td>{e(o["name"])}</td><td>{fa(o["best"])} {e(o["book"])}</td><td>{fa(o["fair_odds"])}</td><td>{o["edge"]:+.1f}</td></tr>' for o in g["outs"])
            out.append(f'<div class=c><b>{e(g["game"])}</b><table><tr><th></th><th>Best</th><th>Fair</th><th>Edge</th></tr>{rows}</table></div>')
    err = "".join(f"<p class=n>Could not load {e(x)}.</p>" for x in errors)
    return f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Pick Desk Auto</title>
<style>:root{{--bg:#f2f5f7;--card:#fff;--ink:#14212b;--mute:#5d6b76;--line:#d9e0e5;--ok:#0f7b6c}}@media(prefers-color-scheme:dark){{:root{{--bg:#0e161c;--card:#16212a;--ink:#e8eef2;--mute:#92a1ac;--line:#263642;--ok:#4cc9b0}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,sans-serif;padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}}main{{max-width:600px;margin:auto;padding:16px}}
h1{{font-size:26px;margin:8px 0}}h2{{font-size:19px;margin:22px 0 8px}}h3{{font-size:15px;color:var(--mute);margin:14px 0 6px}}.c{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin-bottom:10px;overflow-x:auto}}
.ok{{color:var(--ok);font-weight:700}}.n,small{{color:var(--mute);font-size:13px}}table{{width:100%;border-collapse:collapse;margin-top:6px;font-size:14px}}td,th{{padding:4px 6px;border-top:1px solid var(--line);text-align:left}}</style></head><body><main>
<h1>Pick Desk Auto</h1><p class=n id=s>Updated {stamp}</p>{err}{"".join(out)}
<p class=n>Betting should stay fun. If it stops being fun, reach out to a local problem-gambling helpline. Edges are estimates and nothing is guaranteed.</p></main>
<script>var t=Date.parse("{stamp}");if(Date.now()-t>6*36e5)document.getElementById("s").textContent+=". This is over 6 hours old: the update job may have failed."</script></body></html>"""

def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp, nowkey = now.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sample = "--sample" in sys.argv
    key = os.environ.get("ODDS_API_KEY")
    if not sample and not key: sys.exit("Set ODDS_API_KEY or run with --sample")
    sections, errors = {}, []
    if sample:
        data = json.load(open("sample_odds.json")); nowkey = "2000-01-01T00:00:00Z"
        sections = {"Sample": [a for a in (analyze(g, nowkey) for g in data) if a]}
    else:
        todo = SPORTS
        if AUTO_DISCOVER:
            try: todo = discover(key)
            except Exception as ex: errors.append(f"sport list ({ex})")
        for sk, name in todo.items():
            try: sections[name] = [a for a in (analyze(g, nowkey) for g in fetch(sk, key)) if a]
            except Exception as ex: errors.append(f"{name} ({ex})")
        if not any(sections.values()) and errors: sys.exit("All requests failed; keeping the old page: " + "; ".join(errors))
    os.makedirs("docs", exist_ok=True)
    open("docs/index.html", "w").write(render(sections, errors, stamp))
    print("Wrote docs/index.html:", {k: len(v) for k, v in sections.items()}, errors)

if __name__ == "__main__": main()
