"""Pulls odds, finds value bets and arbitrage, writes docs/index.html.
Usage: ODDS_API_KEY=xxx python3 build.py        (live)
       python3 build.py --sample                (test with sample_odds.json)"""
import json, os, sys, html, datetime, urllib.request, urllib.parse

# ---- Settings you can edit -----------------------------------------------
SPORTS = {"americanfootball_nfl": "NFL", "americanfootball_ncaaf": "College football",
          "soccer_epl": "Premier League", "soccer_usa_mls": "MLS",
          "baseball_mlb": "MLB", "icehockey_nhl": "NHL", "basketball_nba": "NBA"}
REGIONS = "us"        # check your data provider's docs for the regions that cover your books
BOOKS = []            # e.g. ["draftkings", "fanduel"]; empty = every book returned
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
def e(s): return html.escape(str(s))


def devig(prices):
    t = sum(imp(p) for p in prices.values())
    return {k: imp(p) / t for k, p in prices.items()}


def fetch(sport, key):
    q = urllib.parse.urlencode({"regions": REGIONS, "markets": "h2h",
                                "oddsFormat": "american", "apiKey": key})
    with urllib.request.urlopen(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?{q}",
                                timeout=30) as r:
        return json.load(r)


def discover(key):
    q = urllib.parse.urlencode({"apiKey": key})
    with urllib.request.urlopen(f"https://api.the-odds-api.com/v4/sports/?{q}", timeout=30) as r:
        found = [x for x in json.load(r) if x.get("active") and not x.get("has_outrights")]
    pref = [x for x in found if x["key"] in SPORTS] + [x for x in found if x["key"] not in SPORTS]
    return {x["key"]: x["title"] for x in pref[:MAX_SPORTS]}


def analyze(game, now):
    if game.get("commence_time", "") <= now:
        return None
    books = {}
    for b in game.get("bookmakers", []):
        if BOOKS and b["key"] not in BOOKS and b["key"] not in SHARP:
            continue
        for m in b.get("markets", []):
            if m["key"] == "h2h" and len(m["outcomes"]) >= 2:
                books[b["key"]] = {o["name"]: o["price"] for o in m["outcomes"]}
    if len(books) < 2:
        return None

    sharp = next((k for k in SHARP if k in books), None)
    names = list(next(iter(books.values())).keys())
    if sharp:
        fair = devig(books[sharp])
    else:
        ds = [devig(p) for p in books.values() if set(p) == set(names)]
        if not ds:
            return None
        fair = {n: sum(d[n] for d in ds) / len(ds) for n in names}

    bet_books = {k: v for k, v in books.items() if not BOOKS or k in BOOKS or k not in SHARP}
    outs = []
    for n in names:
        pr = [(b, p[n]) for b, p in bet_books.items() if n in p]
        if not pr:
            continue
        bk, best = max(pr, key=lambda x: dec(x[1]))
        outs.append({"name": n, "book": bk, "best": best, "fair": fair[n],
                     "fair_odds": am(fair[n]), "edge": (fair[n] - imp(best)) * 100})
    if len(outs) < len(names):
        return None

    s = sum(imp(o["best"]) for o in outs)
    return {"game": f'{game["away_team"]} at {game["home_team"]}',
            "start": game["commence_time"],
            "ref": sharp or "average of books",
            "outs": outs,
            "arb": (1 / s - 1) * 100 if s < 1 else 0}


# ---- Page design -----------------------------------------------------------
CSS = """
:root{--bg:#f3f5f7;--card:#fff;--ink:#14212b;--mute:#5d6b76;--line:#dde3e8;--ok:#0b7a3b;--pill:#e3f5ea;--pilltext:#0b7a3b}
@media (prefers-color-scheme:dark){:root{--bg:#0e1418;--card:#18222b;--ink:#e9eff4;--mute:#9bacb9;--line:#2b3a46;--ok:#55d68d;--pill:#16352a;--pilltext:#7fe6aa}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:640px;margin:0 auto;padding:18px 16px 40px}
h1{font-size:28px;margin:6px 0 4px}
h2{font-size:20px;margin:26px 0 8px}
.meta,.n,small{color:var(--mute);font-size:14px}
small{display:block;margin-top:2px}
.note{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;color:var(--mute);font-size:14px;margin:12px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin:12px 0}
.gt{font-size:18px;font-weight:700;line-height:1.3;margin-bottom:4px}
.row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 0;border-top:1px solid var(--line)}
.row b{font-size:17px}
.r{text-align:right}
.pos{color:var(--ok);font-weight:700}
.neg{color:var(--mute)}
.pill{display:inline-block;background:var(--pill);color:var(--pilltext);border-radius:999px;padding:2px 10px;font-size:14px;font-weight:700}
details{margin:12px 0}
summary{font-size:19px;font-weight:700;cursor:pointer;padding:10px 0}
summary small{display:inline;font-weight:400}
"""

JS = """
(function(){
 var s=document.getElementById('s');
 if(s){
  var t=Date.parse(s.getAttribute('data-t'));
  if(!isNaN(t)){
   s.textContent='Updated '+new Date(t).toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
   if(Date.now()-t>6*36e5){
    var w=document.createElement('p');w.className='note';
    w.textContent='This data may be out of date. The page refreshes about every 3 hours.';
    s.after(w);
   }
  }
 }
 document.querySelectorAll('time[data-t]').forEach(function(el){
  var d=new Date(el.getAttribute('data-t'));
  if(!isNaN(d)) el.textContent=d.toLocaleString([],{weekday:'short',hour:'numeric',minute:'2-digit'});
 });
})();
"""


def page(body):
    return ("<!DOCTYPE html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<meta name=color-scheme content='light dark'>"
            "<title>Pick Desk Auto</title><style>" + CSS + "</style></head>"
            "<body><main>" + body + "</main><script>" + JS + "</script></body></html>")


def fmt_edge(v): return f"{v:+.1f} pts"


def leg_row(o):
    return (f'<div class=row><div><b>{e(o["name"])}</b><small>{e(o["book"])}</small></div>'
            f'<div class=r><b>{fa(o["best"])}</b></div></div>')


def outcome_row(o):
    cls = "pos" if o["edge"] > 0 else "neg"
    return (f'<div class=row><div><b>{e(o["name"])}</b><small>{e(o["book"])}</small></div>'
            f'<div class=r><b>{fa(o["best"])}</b>'
            f'<small>fair {fa(o["fair_odds"])} | <span class={cls}>{fmt_edge(o["edge"])}</span></small></div></div>')


def game_head(g):
    return (f'<div class=gt>{e(g["game"])}</div>'
            f'<small><time data-t="{e(g["start"])}">{e(g["start"])}</time></small>')


def card(inner):
    return f"<section class=card>{inner}</section>"


def render(sections, errors, stamp):
    games = [(sp, g) for sp, gs in sections.items() for g in gs]
    hp = sorted([(sp, g, o) for sp, g in games for o in g["outs"]
                 if o["fair"] >= MIN_PROB and o["edge"] >= MIN_EDGE_SAFE],
                key=lambda x: (-x[2]["fair"], -x[2]["edge"]))
    value = sorted([(sp, g, o) for sp, g in games for o in g["outs"] if o["edge"] >= MIN_EDGE],
                   key=lambda x: -x[2]["edge"])
    arbs = sorted([(sp, g) for sp, g in games if g["arb"] > 0], key=lambda x: -x[1]["arb"])

    out = [f'<h2>High-chance plays</h2>'
           f'<p class=n>Fair win chance {MIN_PROB * 100:.0f}%+ with a price at or better than fair. '
           f'Most days there are few or none.</p>']
    if not hp:
        out.append('<p class=n>No plays meet the criteria right now.</p>')
    for sp, g, o in hp:
        out.append(card(f'<div class=gt>{e(o["name"])} <span class=pill>{o["fair"] * 100:.0f}% to win</span></div>'
                        f'<small>{e(g["game"])} | {e(sp)}</small>'
                        f'<div class=row><div>Best price <small>{e(o["book"])}</small></div>'
                        f'<div class=r><b>{fa(o["best"])}</b></div></div>'
                        f'<small>Fair odds {fa(o["fair_odds"])} from {e(g["ref"])}</small>'))

    out.append('<h2>Value bets</h2>')
    if not value:
        out.append('<p class=n>No value bets right now.</p>')
    for sp, g, o in value:
        out.append(card(f'<div class=gt>{e(g["game"])}</div>'
                        f'<small>{e(sp)} | fair from {e(g["ref"])}</small>' + outcome_row(o)))

    out.append('<h2>Arbitrage</h2>')
    if not arbs:
        out.append('<p class=n>No arbitrage right now.</p>')
    for sp, g in arbs:
        out.append(card(f'<div class=gt><span class=pill>{g["arb"]:.1f}% locked</span></div>'
                        f'<div class=gt>{e(g["game"])}</div><small>{e(sp)}</small>'
                        + "".join(leg_row(o) for o in g["outs"])
                        + '<small>Prices move fast. Confirm both sides before betting.</small>'))

    out.append('<h2>All games</h2>')
    shown = False
    for sp, gs in sections.items():
        if not gs:
            continue
        shown = True
        cards = "".join(card(game_head(g) + "".join(outcome_row(o) for o in g["outs"])
                             + f'<small>Fair odds from {e(g["ref"])}</small>') for g in gs)
        out.append(f'<details><summary>{e(sp)} <small>({len(gs)} games)</small></summary>{cards}</details>')
    if not shown:
        out.append('<p class=n>No upcoming games found.</p>')

    err = "".join(f'<p class=note>Could not load {e(x)}.</p>' for x in errors)
    top = (f'<h1>Pick Desk Auto</h1>'
           f'<p class=meta id=s data-t="{e(stamp)}">Updated {e(stamp)}</p>'
           f'<p class=note>Odds data is informational only. Bet responsibly. '
           f'Even the best plays lose often, so keep stakes small.</p>')
    foot = ('<p class=note>Betting should stay fun. If it stops being fun, reach out to a local '
            'problem-gambling helpline.</p>')
    return page(top + err + "".join(out) + foot)


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    nowkey = stamp
    sample = "--sample" in sys.argv
    key = os.environ.get("ODDS_API_KEY")
    if not sample and not key:
        sys.exit("Set ODDS_API_KEY or run with --sample")

    sections, errors = {}, []
    if sample:
        with open("sample_odds.json", encoding="utf-8") as f:
            data = json.load(f)
        nowkey = "2000-01-01T00:00:00Z"
        sections = {"Sample": [a for a in (analyze(g, nowkey) for g in data) if a]}
    else:
        todo = SPORTS
        if AUTO_DISCOVER:
            try:
                todo = discover(key)
            except Exception as ex:
                errors.append(f"sport list ({ex})")
        for sk, name in todo.items():
            try:
                games = fetch(sk, key)
                sections[name] = [a for a in (analyze(g, nowkey) for g in games) if a]
            except Exception as ex:
                errors.append(f"{name} ({ex})")
        if not sections and errors:
            sys.exit("All requests failed; keeping the last good page.")

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(render(sections, errors, stamp))
    print("Wrote docs/index.html:", {k: len(v) for k, v in sections.items()}, errors)


if __name__ == "__main__":
    main()
