"""
build_dashboard.py — builds the HTML dashboard from screener data
Called by screener.py
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import json


def fmt_pct(v):
    return ("+" if v >= 0 else "") + str(round(v, 2)) + "%"


STAGE_COL = {1: "#5a7a9a", 2: "#00d084", 3: "#ff9f43", 4: "#ff4757"}
STAGE_BG  = {1: "rgba(90,122,154,.1)", 2: "rgba(0,208,132,.1)", 3: "rgba(255,159,67,.1)", 4: "rgba(255,71,87,.1)"}
STAGE_BD  = {1: "rgba(90,122,154,.3)", 2: "rgba(0,208,132,.3)", 3: "rgba(255,159,67,.3)", 4: "rgba(255,71,87,.3)"}
STAGE_LBL = {1: "S1 Neglect", 2: "S2 Advancing", 3: "S3 Topping", 4: "S4 Declining"}


def build(data, source="Yahoo Finance (live)", min_cap=5_000_000_000):
    MELBOURNE = ZoneInfo("Australia/Melbourne")
    NEW_YORK  = ZoneInfo("America/New_York")
    _now      = datetime.now(MELBOURNE)
    _ny       = datetime.now(NEW_YORK)
    ny_str    = _ny.strftime("%a %d %b %Y, %I:%M %p %Z").replace(" 0", " ")
    today_str = _now.strftime("%d %b %Y")
    cap_str   = (f"${min_cap/1e9:g}B" if min_cap >= 1e9 else f"${min_cap/1e6:g}M")
    stamp_str = _now.strftime("%d %b %Y, %I:%M %p %Z").lstrip("0").replace(" 0", " ")

    def _jsafe(o):
        if hasattr(o, 'item'): return o.item()
        if hasattr(o, '__float__'): return float(o)
        raise TypeError(repr(o))

    def _clean(obj):
        if isinstance(obj, float) and obj != obj:  # NaN -> null (valid JSON)
            return None
        if isinstance(obj, str):  return obj.encode('utf-8', errors='replace').decode('utf-8')
        if isinstance(obj, dict): return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [_clean(v) for v in obj]
        return obj
    data = [_clean(r) for r in data]
    for r in data:  # drop any candle with a missing value so charts/maths never see null
        r["ohlcv"] = [c for c in (r.get("ohlcv") or []) if all(v is not None for v in c)]
    json_data = json.dumps(data, default=_jsafe)

    n        = len(data)
    breakouts = [r for r in data if r["status"] == "breakout"]
    pivots    = [r for r in data if r["status"] == "near-pivot"]
    watching  = [r for r in data if r["status"] == "watch"]
    ipos      = [r for r in data if r.get("ipo")]
    stage1    = [r for r in data if r.get("stage") == 1]
    stage2    = [r for r in data if r.get("stage") == 2]
    stage3    = [r for r in data if r.get("stage") == 3]
    stage4    = [r for r in data if r.get("stage") == 4]
    sectors   = sorted(set(r["sector"] for r in data if r["sector"]))
    sector_opts = "".join(f'<option value="{s}">{s}</option>' for s in sectors)

    top = sorted(
        breakouts + [r for r in pivots if r["sepaScore"] >= 5],
        key=lambda x: (x["sepaScore"], x["vcpScore"], x["volRatio"]),
        reverse=True
    )[:10]

    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    top_html = ""
    for i, r in enumerate(top):
        sc    = r["sepaScore"]
        pips  = "".join(f'<div class="pip {"pg" if j<sc else "po"}"></div>' for j in range(7))
        vpips = "".join(f'<div class="vp {"von" if j<r["vcpScore"] else "voff"}"></div>' for j in range(4))
        col   = "#00d084" if r["status"] == "breakout" else "#3b82f6"
        p250c = "#00d084" if r["chg250d"] >= 0 else "#ff4757"
        badge_label = "BREAKOUT" if r["status"] == "breakout" else "NEAR PIVOT"
        stg   = r.get("stage", 2)
        stg_c = STAGE_COL[stg]
        stg_l = STAGE_LBL[stg]
        ev_html = ""
        nl = r.get("nextEventLabel")
        if nl:
            ev_col = "#ffd700" if "\u26a1" in nl else "#3b82f6"
            ev_bg  = "rgba(255,215,0,.1)" if "\u26a1" in nl else "rgba(59,130,246,.1)"
            ev_bd  = "rgba(255,215,0,.3)" if "\u26a1" in nl else "rgba(59,130,246,.3)"
            ev_html += (f'<div style="margin-top:5px;font-size:10px;font-weight:700;'
                        f'color:{ev_col};background:{ev_bg};border:1px solid {ev_bd};'
                        f'border-radius:4px;padding:2px 7px;display:inline-block">{nl}</div>')
        rt = r.get("revTrend")
        if rt in ("accelerating", "growing"):
            rt_col = "#00d084" if rt == "accelerating" else "#8bc34a"
            rt_lbl = "\u21911\u2191 Rev Accelerating" if rt == "accelerating" else "\u2191 Rev Growing"
            ev_html += (f'<div style="margin-top:4px;font-size:10px;font-weight:700;'
                        f'color:{rt_col};background:rgba(0,208,132,.07);border:1px solid rgba(0,208,132,.2);'
                        f'border-radius:4px;padding:2px 7px;display:inline-block">{rt_lbl}</div>')

        top_html += f'''<div class="tc" onclick="jmp('{r["ticker"]}')" >
<span class="tc-rank">{medals[i]}</span>
<div class="tc-body">
  <div class="tc-head">
    <span class="tc-ticker">{r["ticker"]}</span>
    <span class="badge-status" style="color:{col};border-color:{col}44">{badge_label}</span>
    <span class="stage-mini" style="color:{stg_c};border-color:{stg_c}44;background:{stg_c}0d">{stg_l}</span>
  </div>
  <div class="tc-name">{r["name"]}</div>
  <div style="display:flex;gap:5px;margin-bottom:6px"><div class="pips">{pips}</div><div class="vpips">{vpips}</div></div>
  <div class="tc-stats">
    <span style="color:#e8f0fe;font-weight:700">${r["price"]}</span>
    <span style="color:{p250c}">{fmt_pct(r["chg250d"])} 12M</span>
    <span style="color:{"#00d084" if r["volRatio"]>=1.5 else "#ff9f43"}">{r["volRatio"]}x vol</span>
  </div>
  <div class="tc-sig">{r["shortSignal"]}</div>
  {ev_html}
</div>
</div>'''

    tmpl = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SEPA+VCP US Screener \u2014 {today_str}</title>
<meta name="description" content="Minervini SEPA + VCP US stock screener (NYSE, NASDAQ, NYSE American) with stage analysis, candlestick charts, and fundamental data. Updated daily.">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
/* \u2500\u2500 Reset \u2500\u2500 */
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080c14;--bg2:#0d1421;--bg3:#131c2e;--bg4:#1a2540;
  --border:#1e2d45;--border2:#243350;
  --text:#e8f0fe;--muted:#5a7a9a;--muted2:#3d5a78;
  --green:#00d084;--green2:#00a86b;
  --blue:#3b82f6;--cyan:#00b4d8;
  --amber:#ff9f43;--red:#ff4757;--gold:#ffd700;
  --s1:#5a7a9a;--s2:#00d084;--s3:#ff9f43;--s4:#ff4757;
}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.5}

/* \u2500\u2500 Nav \u2500\u2500 */
nav{
  background:rgba(8,12,20,.96);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  border-bottom:1px solid var(--border);padding:10px 24px;
  display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:100;gap:12px;flex-wrap:wrap
}
.nlogo{font-weight:800;font-size:15px;color:#fff;display:flex;align-items:center;gap:8px;letter-spacing:-.3px}
.ndot{width:8px;height:8px;background:var(--green);border-radius:50%;animation:pulse 2s infinite;box-shadow:0 0 8px var(--green)}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.75)}}
.nlinks{display:flex;gap:18px}.nlinks a{color:var(--muted);font-size:12px;text-decoration:none;transition:color .15s}.nlinks a:hover{color:var(--text)}
.nbadge{background:rgba(0,208,132,.1);color:var(--green);border:1px solid rgba(0,208,132,.25);border-radius:20px;padding:3px 11px;font-size:11px;font-weight:600;white-space:nowrap}

/* \u2500\u2500 Hero \u2500\u2500 */
.hero{
  background:linear-gradient(160deg,#070a12 0%,#0c1628 55%,#070a12 100%);
  padding:52px 24px 36px;text-align:center;border-bottom:1px solid var(--border);
  position:relative;overflow:hidden
}
.hero::before{
  content:'';position:absolute;top:-30%;left:50%;transform:translateX(-50%);
  width:700px;height:400px;
  background:radial-gradient(ellipse,rgba(0,208,132,.07) 0%,transparent 65%);
  pointer-events:none
}
.hero h1{font-size:36px;font-weight:800;color:#fff;letter-spacing:-1.5px;line-height:1.1;margin-bottom:10px}
.hero h1 span{background:linear-gradient(90deg,var(--green),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{font-size:14px;color:var(--muted);margin:0 auto;max-width:560px;line-height:1.7}
.hero-stats{
  display:flex;justify-content:center;gap:0;margin-top:28px;flex-wrap:wrap;
  border:1px solid var(--border);border-radius:12px;overflow:hidden;
  max-width:580px;margin-left:auto;margin-right:auto;background:var(--bg2)
}
.hs{text-align:center;padding:15px 22px;flex:1;border-right:1px solid var(--border)}
.hs:last-child{border-right:none}
.hs-n{font-size:28px;font-weight:800;font-family:'JetBrains Mono'}
.hs-l{font-size:9px;color:var(--muted);margin-top:2px;text-transform:uppercase;letter-spacing:.7px}
.stage-row{display:flex;justify-content:center;gap:8px;margin-top:16px;flex-wrap:wrap}
.stage-pill{
  display:flex;align-items:center;gap:5px;padding:5px 13px;border-radius:20px;
  font-size:11px;font-weight:700;border:1px solid;cursor:pointer;transition:all .15s;user-select:none
}
.stage-pill:hover{filter:brightness(1.15);transform:translateY(-1px)}

/* \u2500\u2500 Top picks \u2500\u2500 */
.section{padding:40px 24px;border-bottom:1px solid var(--border)}
.stitle{font-size:20px;font-weight:800;color:#fff;margin-bottom:4px;letter-spacing:-.3px}
.ssub{font-size:13px;color:var(--muted);margin-bottom:22px}
.picks-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(225px,1fr));gap:10px}
.tc{
  background:var(--bg2);border:1px solid var(--border);border-radius:12px;
  padding:13px;cursor:pointer;transition:all .18s;display:flex;gap:9px;
  position:relative;overflow:hidden
}
.tc::after{
  content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,var(--green),var(--cyan));
  opacity:0;transition:opacity .18s
}
.tc:hover{border-color:rgba(0,208,132,.28);transform:translateY(-2px);box-shadow:0 6px 24px rgba(0,208,132,.07)}
.tc:hover::after{opacity:1}
.tc-rank{font-size:18px;flex-shrink:0;margin-top:1px}
.tc-body{flex:1;min-width:0}
.tc-head{display:flex;align-items:center;gap:5px;margin-bottom:2px;flex-wrap:wrap}
.tc-ticker{font-weight:800;font-size:14px;font-family:'JetBrains Mono';color:#fff;letter-spacing:.5px}
.badge-status{padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:.5px;border:1px solid;background:transparent}
.stage-mini{padding:1px 5px;border-radius:3px;font-size:8px;font-weight:700;letter-spacing:.3px;border:1px solid}
.tc-name{font-size:10px;color:var(--muted);margin-bottom:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tc-stats{display:flex;gap:7px;font-size:11px;font-family:'JetBrains Mono';flex-wrap:wrap}
.tc-sig{font-size:10px;color:var(--muted2);margin-top:3px;line-height:1.4}

/* \u2500\u2500 Pips \u2500\u2500 */
.pips,.vpips{display:flex;gap:2px}
.pip{width:8px;height:8px;border-radius:2px}
.pg{background:var(--green)}.pa{background:var(--amber)}.pr{background:var(--red)}
.po{background:var(--bg4);border:1px solid var(--border)}
.vp{width:9px;height:9px;border-radius:2px}.von{background:var(--blue)}.voff{background:var(--bg4);border:1px solid var(--border)}
.fpip{width:9px;height:9px;border-radius:2px}.fon{background:var(--amber)}.foff{background:var(--bg4);border:1px solid var(--border)}

/* \u2500\u2500 Toolbar \u2500\u2500 */
.toolbar{
  padding:8px 24px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;
  background:rgba(8,12,20,.94);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--border);position:sticky;top:49px;z-index:90
}
.fbtn{
  padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;
  border:1px solid var(--border);background:var(--bg3);color:var(--muted);
  transition:all .12s;white-space:nowrap;user-select:none
}
.fbtn.on{border-color:var(--green);background:rgba(0,208,132,.1);color:var(--green)}
.fbtn:hover:not(.on){border-color:var(--muted2);color:var(--text)}
.fbtn.s1.on{border-color:var(--s1);background:rgba(90,122,154,.1);color:var(--s1)}
.fbtn.s2.on{border-color:var(--s2);background:rgba(0,208,132,.1);color:var(--s2)}
.fbtn.s3.on{border-color:var(--s3);background:rgba(255,159,67,.1);color:var(--s3)}
.fbtn.s4.on{border-color:var(--s4);background:rgba(255,71,87,.1);color:var(--s4)}
.tsep{width:1px;height:20px;background:var(--border);margin:0 2px;flex-shrink:0}
input.srch,select{
  background:var(--bg3);border:1px solid var(--border);color:var(--text);
  border-radius:6px;padding:5px 9px;font-size:11px;outline:none;font-family:'Inter'
}
input.srch{width:150px}input.srch::placeholder{color:var(--muted)}
input.srch:focus,select:focus{border-color:var(--green)}
.cnt{font-size:11px;color:var(--muted);margin-left:auto;white-space:nowrap}

/* \u2500\u2500 Table \u2500\u2500 */
.twrap{margin:0 24px 28px;border:1px solid var(--border);border-radius:12px;overflow:hidden;overflow-x:auto}
.twrap>table{width:100%;border-collapse:collapse;min-width:1060px}
thead th{
  background:var(--bg2);padding:9px 10px;text-align:left;
  font-size:9px;font-weight:700;color:var(--muted);text-transform:uppercase;
  letter-spacing:.7px;border-bottom:1px solid var(--border);white-space:nowrap
}
tbody tr.main-row{border-bottom:1px solid rgba(30,45,69,.5);cursor:pointer;transition:background .08s}
tbody tr.main-row:hover{background:rgba(13,20,33,.85)}
tbody tr.main-row.expanded{background:var(--bg2);border-bottom:none}
tbody td{padding:8px 10px;vertical-align:middle}
.tkr{font-weight:800;font-size:13px;font-family:'JetBrains Mono';color:#fff;letter-spacing:.3px}
.co{font-size:10px;color:var(--muted);margin-top:1px;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.badge{display:inline-flex;padding:2px 7px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:.4px}
.bb{background:rgba(0,208,132,.1);color:var(--green);border:1px solid rgba(0,208,132,.3)}
.bp{background:rgba(59,130,246,.1);color:var(--blue);border:1px solid rgba(59,130,246,.3)}
.bw{background:rgba(255,159,67,.1);color:var(--amber);border:1px solid rgba(255,159,67,.3)}
.bb-pulse{animation:bdgpulse 2.5s infinite}
@keyframes bdgpulse{0%,100%{box-shadow:0 0 0 0 rgba(0,208,132,.5)}50%{box-shadow:0 0 0 5px rgba(0,208,132,0)}}
.stage-badge{display:inline-flex;padding:2px 7px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:.3px;white-space:nowrap}
.pv{font-family:'JetBrains Mono';font-size:12px;font-weight:600}
.gn{color:var(--green)}.rd{color:var(--red)}.gy{color:var(--muted)}
.vhigh{color:var(--green);font-weight:700}.vmed{color:var(--amber);font-weight:600}.vlow{color:var(--muted)}
.pvg{color:var(--green);font-weight:600}.pvo{color:var(--amber)}.pvw{color:var(--muted)}
.sec{font-size:10px;color:#4a6a8a;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mc{font-family:'JetBrains Mono';font-size:11px;color:#4a6a8a}
.vol-wrap{display:flex;align-items:center;gap:5px}
.vol-track{width:32px;height:4px;background:var(--bg4);border-radius:2px;overflow:hidden}
.vol-fill{height:100%;border-radius:2px}

/* \u2500\u2500 Detail panel \u2500\u2500 */
.drow td{padding:0;background:#050810}
.dpanel{
  padding:18px 18px 20px 48px;
  display:grid;
  grid-template-columns:minmax(310px,2.4fr) minmax(140px,1.1fr) minmax(140px,1.1fr) minmax(160px,1.2fr) minmax(130px,1fr) minmax(160px,1.2fr);
  gap:16px;border-top:1px solid var(--border)
}
.dh{font-size:9px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:9px}
.cl{display:flex;flex-direction:column;gap:3px}
.cr{display:flex;align-items:flex-start;gap:5px;font-size:11px;line-height:1.5}
.cr.ok{color:var(--green)}.cr.no{color:#253550}
.ci{width:12px;flex-shrink:0;font-size:10px;margin-top:1px}
.mat{width:100%;min-width:0;border-collapse:collapse;font-size:11px;table-layout:auto}
.mat td{padding:3px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mlb{color:var(--muted);width:auto;white-space:nowrap}.mbar{padding:2px 6px;width:88px}
.mbw{height:5px;background:var(--bg4);border-radius:3px;overflow:hidden}
.mbi{height:100%;border-radius:3px}.mvl{font-family:'JetBrains Mono';color:#4a6a8a;text-align:right;width:54px}
.mgv{font-family:'JetBrains Mono';font-size:11px;font-weight:700;text-align:right;white-space:nowrap}
.rev-bars{display:flex;align-items:flex-end;gap:3px;height:48px;margin:6px 0}
.rev-bar-wrap{display:flex;flex-direction:column;align-items:center;gap:2px;flex:0 0 24px}
.rev-bar{width:16px;border-radius:2px 2px 0 0;min-height:2px}
.rev-bar-lbl{font-size:8px;color:var(--muted)}
.abox{background:var(--bg2);border-radius:8px;padding:11px;border-left:3px solid var(--border);font-size:11px;color:#4a6a8a;line-height:1.8}
.aact{margin-top:8px;font-weight:700;font-size:11px;padding:6px 10px;border-radius:6px}
.abuy{color:var(--green);background:rgba(0,208,132,.06);border:1px solid rgba(0,208,132,.2)}
.awch{color:var(--blue);background:rgba(59,130,246,.06);border:1px solid rgba(59,130,246,.2)}
.ahld{color:var(--amber);background:rgba(255,159,67,.06);border:1px solid rgba(255,159,67,.2)}
.pg2{display:flex;flex-direction:column;gap:0;font-size:10px;margin-top:8px}
.pi{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid var(--border)}
.pi:last-child{border:none}.pk{color:var(--muted);flex-shrink:0;margin-right:5px}
.pv2{font-family:'JetBrains Mono';font-size:10px;font-weight:600;text-align:right}
.ev-hot{display:inline-block;padding:4px 9px;border-radius:5px;font-size:11px;font-weight:800;background:rgba(255,215,0,.1);color:var(--gold);border:1px solid rgba(255,215,0,.3);margin-top:6px}
.ev-soon{display:inline-block;padding:4px 9px;border-radius:5px;font-size:11px;font-weight:700;background:rgba(59,130,246,.1);color:var(--blue);border:1px solid rgba(59,130,246,.3);margin-top:6px}
.ev-div{font-size:10px;color:var(--amber);margin-top:5px}
.ev-none{font-size:10px;color:#253550;margin-top:6px}
.trend-chip{display:inline-block;font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;margin-bottom:7px}
.trend-acc{background:rgba(0,208,132,.1);color:var(--green);border:1px solid rgba(0,208,132,.25)}
.trend-grow{background:rgba(139,195,74,.08);color:#8bc34a;border:1px solid rgba(139,195,74,.2)}
.trend-flat{background:rgba(255,159,67,.08);color:var(--amber);border:1px solid rgba(255,159,67,.2)}
.trend-dec{background:rgba(255,71,87,.08);color:var(--red);border:1px solid rgba(255,71,87,.2)}
.fpips{display:flex;gap:2px}
.tl-box{background:var(--bg2);border:1.5px solid rgba(0,208,132,.35);border-radius:8px;padding:10px 12px;margin-bottom:9px}
.tl-title{font-size:10px;font-weight:700;color:var(--text);letter-spacing:.06em;margin-bottom:8px}
.tl-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.tl-cell{border-radius:5px;padding:6px 8px;text-align:center}
.tl-lbl{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:3px}
.tl-val{font-size:14px;font-weight:700;font-family:'JetBrains Mono'}
.stage-info-box{border-radius:7px;padding:9px 11px;font-size:11px;line-height:1.6;margin-bottom:10px;border:1px solid}
.empty{text-align:center;padding:50px;color:var(--muted)}
footer{background:#040710;border-top:1px solid var(--border);padding:18px 24px;text-align:center;font-size:11px;color:var(--muted)}
@media(max-width:1300px){.dpanel{grid-template-columns:1.5fr 1fr 1fr 1fr!important}}
@media(max-width:1000px){.dpanel{grid-template-columns:1fr 1fr!important}}
@media(max-width:600px){.dpanel{grid-template-columns:1fr!important}.hero h1{font-size:26px}}
</style>
</head>
<body>
<nav>
  <div class="nlogo"><div class="ndot"></div>SEPA+VCP US Screener</div>
  <div class="nlinks"><a href="#picks">Top Picks</a><a href="#screener">Screener</a></div>
  <span class="nbadge">&#x25cf; Live &mdash; {stamp_str}</span>
</nav>

<div class="hero">
  <h1>US Stock Screener<br><span>SEPA &middot; VCP &middot; Minervini Stages</span></h1>
  <p>Minervini's Stage 2 Trend Template with VCP analysis, net revenue trend, EPS growth, Minervini lifecycle stage classification (1&ndash;4), and 60-day candlestick charts &mdash; applied to every NYSE, NASDAQ and NYSE American common stock over {cap_str} market cap.</p>
  <div class="hero-stats">
    <div class="hs"><div class="hs-n" style="color:var(--green)">{len(breakouts)}</div><div class="hs-l">Breakouts</div></div>
    <div class="hs"><div class="hs-n" style="color:var(--blue)">{len(pivots)}</div><div class="hs-l">Near Pivot</div></div>
    <div class="hs"><div class="hs-n" style="color:var(--amber)">{len(watching)}</div><div class="hs-l">On Watch</div></div>
    <div class="hs"><div class="hs-n" style="color:var(--text)">{n}</div><div class="hs-l">Screened</div></div>
  </div>
  <div class="stage-row">
    <div class="stage-pill" style="color:var(--s1);border-color:rgba(90,122,154,.3);background:rgba(90,122,154,.08)" onclick="setStageHero(1,this)">
      &#x25cf; S1 Neglect <strong>&nbsp;{len(stage1)}</strong>
    </div>
    <div class="stage-pill" style="color:var(--s2);border-color:rgba(0,208,132,.3);background:rgba(0,208,132,.08)" onclick="setStageHero(2,this)">
      &#x25cf; S2 Advancing <strong>&nbsp;{len(stage2)}</strong>
    </div>
    <div class="stage-pill" style="color:var(--s3);border-color:rgba(255,159,67,.3);background:rgba(255,159,67,.08)" onclick="setStageHero(3,this)">
      &#x25cf; S3 Topping <strong>&nbsp;{len(stage3)}</strong>
    </div>
    <div class="stage-pill" style="color:var(--s4);border-color:rgba(255,71,87,.3);background:rgba(255,71,87,.08)" onclick="setStageHero(4,this)">
      &#x25cf; S4 Declining <strong>&nbsp;{len(stage4)}</strong>
    </div>
  </div>
</div>

<div class="section" id="picks">
  <div class="stitle">&#x1F3C6; Top 10 US Picks Today</div>
  <div class="ssub">Highest-conviction SEPA + VCP + Stage 2 setups &mdash; ranked by combined score. Click any card to jump to full analysis with 60-day candlestick chart.</div>
  <div class="picks-grid">{top_html}</div>
  <p style="font-size:11px;color:var(--muted);margin-top:16px;line-height:1.7">
    <strong style="color:#c9d1d9">How to read:</strong> Green pips = SEPA score (7 max). Blue pips = VCP score (4 max).
    <strong style="color:var(--green)">S2 Advancing</strong> = the only safe buying stage.
    Breakouts: enter at market, stop below MA50. Near Pivot: set alert at pivot high, enter on breakout with vol &gt;1.5x. Always risk 1&ndash;2% max per trade.
  </p>
</div>

<div id="screener">
<div class="toolbar">
  <button class="fbtn on" id="btn-all" onclick="setF('all',this)">All ({n})</button>
  <button class="fbtn" onclick="setF('breakout',this)">&#x1F7E2; Breakout ({len(breakouts)})</button>
  <button class="fbtn" onclick="setF('near-pivot',this)">&#x1F535; Near Pivot ({len(pivots)})</button>
  <button class="fbtn" onclick="setF('watch',this)">&#x1F7E1; Watch ({len(watching)})</button>
  <button class="fbtn" onclick="setF('ipo',this)" title="Listed less than 200 sessions ago">&#x1F195; Recent IPOs ({len(ipos)})</button>
  <div class="tsep"></div>
  <button class="fbtn s2" id="tb-s2" onclick="setStageFilter(2,this)">S2 Advancing ({len(stage2)})</button>
  <button class="fbtn s1" id="tb-s1" onclick="setStageFilter(1,this)">S1 Neglect ({len(stage1)})</button>
  <button class="fbtn s3" id="tb-s3" onclick="setStageFilter(3,this)">S3 Topping ({len(stage3)})</button>
  <button class="fbtn s4" id="tb-s4" onclick="setStageFilter(4,this)">S4 Declining ({len(stage4)})</button>
  <div class="tsep"></div>
  <input class="srch" id="srch" placeholder="&#x1F50D; Ticker or name..." oninput="render()">
  <select id="srt" onchange="render()">
    <option value="sepa">&#x2193; SEPA Score</option>
    <option value="vcp">&#x2193; VCP Score</option>
    <option value="vol">&#x2193; Volume Ratio</option>
    <option value="pvr">&#x2193; PVR</option>
    <option value="fund">&#x2193; Fund Score</option>
    <option value="p250">&#x2193; 12M Perf</option>
    <option value="mc">&#x2193; Mkt Cap</option>
    <option value="stage">&#x2191; Stage (1 first)</option>
  </select>
  <select id="sec" onchange="render()"><option value="">All Sectors</option>{sector_opts}</select>
  <span class="cnt" id="cnt"></span>
</div>
<div class="twrap"><table>
  <thead><tr>
    <th>#</th><th>Ticker</th><th>Stage</th><th>Signal</th>
    <th>SEPA /7</th><th>VCP /4</th>
    <th>Price</th><th>Today</th><th>Rel.Vol</th><th>PVR</th>
    <th>Fund /3</th><th>Net Revenue</th><th>Catalyst</th>
    <th>12M</th><th>Mkt Cap</th><th>Sector</th>
  </tr></thead>
  <tbody id="tbody"></tbody>
</table></div>
</div>

<footer>
  <strong>SEPA + VCP US Screener</strong> &middot; Data: Yahoo Finance, Nasdaq &middot; Generated {stamp_str} (Melbourne time) &middot; {ny_str} (New York)<br>
  <span style="font-size:10px;opacity:.55">&#x26A0;&#xFE0F; For educational and research purposes only. Not financial advice. Always conduct your own due diligence and consult a licensed financial adviser before making investment decisions. All prices in USD.</span>
</footer>

<script>

var SLBL = {1: 'S1 Neglect', 2: 'S2 Advancing', 3: 'S3 Topping', 4: 'S4 Declining'};
var SDESC = {
  1: 'Stock is basing after a long downtrend. Wait for Stage 2.',
  2: 'Uptrend confirmed. Institutions are buying. Target entry.',
  3: 'Momentum slowing. Heavy volume on down days. Sell/Reduce.',
  4: 'Downtrend in progress. Avoid or Short.'
};
const D={json_data};
let filt='all', stageFilt=0;
const CUR=String.fromCharCode(36);
const SCOL={1:'#5a7a9a',2:'#00d084',3:'#ff9f43',4:'#ff4757'};

function setF(f,el){
  filt=f;
  document.querySelectorAll('.fbtn').forEach(b=>b.classList.remove('on'));
  el.classList.add('on');
  render();
}

function setStageHero(s,el){
  stageFilt = stageFilt===s ? 0 : s;
  ['tb-s1','tb-s2','tb-s3','tb-s4'].forEach(id=>{
    const b=document.getElementById(id); if(b)b.classList.remove('on');
  });
  if(stageFilt){
    const b=document.getElementById('tb-s'+s); if(b)b.classList.add('on');
  }
  document.getElementById('screener').scrollIntoView({behavior:'smooth'});
  render();
}

function setStageFilter(s,el){
  stageFilt = stageFilt===s ? 0 : s;
  document.querySelectorAll('.fbtn.s1,.fbtn.s2,.fbtn.s3,.fbtn.s4').forEach(b=>b.classList.remove('on'));
  if(stageFilt===s) el.classList.add('on');
  render();
}

function jmp(t){
  document.getElementById('screener').scrollIntoView({behavior:'smooth'});
  document.getElementById('srch').value=t;
  setTimeout(()=>{render();const r=document.querySelector('#tbody tr.main-row');if(r)r.click();},400);
}

function fmtGrowth(v,hi,med){
  hi=hi===undefined?20:hi; med=med===undefined?5:med;
  if(v===null||v===undefined)return '<span style="color:#253550">N/A</span>';
  var col=v>=hi?'#00d084':v>=med?'#ff9f43':v>=0?'#5a7a9a':'#ff4757';
  var arrow=v>0?'\u2191 ':v<0?'\u2193 ':'';
  return '<span style="color:'+col+';font-weight:700">'+arrow+(v>=0?'+':'')+v+'%</span>';
}

function revTrendChip(trend){
  if(!trend)return'';
  var map={'accelerating':['trend-chip trend-acc','\u21911\u2191 Accelerating'],'growing':['trend-chip trend-grow','\u2191 Growing'],'flat':['trend-chip trend-flat','\u2192 Flat'],'declining':['trend-chip trend-dec','\u2193 Declining']};
  var e=map[trend]||['',''];
  return e[0]?'<div class="'+e[0]+'">'+e[1]+'</div>':'';
}

function _num(v){return typeof v==='number'&&isFinite(v);}
function _pc(v,d){if(!_num(v))return '<span style="color:#3d5a78">n/a</span>';var c=v>=0?'#00d084':'#ff4757';return '<span style="color:'+c+'">'+(v>=0?'+':'')+v.toFixed(d===undefined?1:d)+'%</span>';}
function _kv(l,v){return '<tr><td class="mlb">'+l+'</td><td class="mgv">'+v+'</td></tr>';}
function _barRow(lbl,v,scale){
  if(!_num(v))return '';
  var w=Math.min(Math.abs(v)/scale*50,50),c=v>=0?'#00d084':'#ff4757';
  var bar='<div style="position:relative;height:5px;background:var(--bg4);border-radius:3px;margin-top:3px">'+
    '<div style="position:absolute;left:50%;top:-2px;width:1px;height:9px;background:#3d5a78"></div>'+
    '<div style="position:absolute;top:0;height:5px;border-radius:3px;background:'+c+';'+(v>=0?'left:50%':'right:50%')+';width:'+w+'%"></div></div>';
  return '<div style="margin-bottom:7px"><div style="display:flex;justify-content:space-between;font-size:10px"><span style="color:var(--muted)">'+lbl+'</span><strong style="font-family:JetBrains Mono">'+_pc(v)+'</strong></div>'+bar+'</div>';
}
function _tag(txt,c){return '<span style="font-size:8.5px;font-weight:700;color:'+c+';border:1px solid '+c+'55;background:'+c+'14;border-radius:3px;padding:0 4px;margin-left:5px">'+txt+'</span>';}
function _gauge(v,lo,hi){
  if(!_num(v))return '';
  var p=Math.max(0,Math.min(100,v));
  return '<div style="position:relative;height:5px;border-radius:3px;margin:3px 0 7px;background:linear-gradient(90deg,#00d084 0,#00d084 '+lo+'%,#1e2d45 '+lo+'%,#1e2d45 '+hi+'%,#ff4757 '+hi+'%,#ff4757 100%);opacity:.8">'+
    '<div style="position:absolute;left:calc('+p+'% - 1px);top:-3px;width:3px;height:11px;border-radius:1px;background:#e8f0fe"></div></div>';
}
function _trow(lbl,val,tag){return '<div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;margin-top:5px"><span style="color:var(--muted)">'+lbl+'</span><span style="font-family:JetBrains Mono;font-weight:700;color:#e8f0fe;white-space:nowrap">'+val+(tag||'')+'</span></div>';}
function techHTML(r){
  var t=r.tech||{}; if(!Object.keys(t).length)return '';
  var G='#00d084',A='#ff9f43',R='#ff4757',B='#3b82f6',M='#5a7a9a';
  var o='<div class="mv"><div class="dh" style="margin-top:14px">Technical Indicators</div>';
  if(_num(t.rsi)){
    var rt=t.rsi>=70?_tag('OVERBOUGHT',R):t.rsi<=30?_tag('OVERSOLD',G):t.rsi>=50?_tag('BULLISH',G):_tag('WEAK',A);
    o+=_trow('RSI (14)',t.rsi.toFixed(1),rt)+_gauge(t.rsi,30,70);
  }
  if(_num(t.stochK)){
    var st=t.stochK>=80?_tag('OVERBOUGHT',R):t.stochK<=20?_tag('OVERSOLD',G):(_num(t.stochD)&&t.stochK>t.stochD?_tag('RISING',G):_tag('FALLING',A));
    o+=_trow('Stoch %K / %D',t.stochK.toFixed(0)+' / '+(_num(t.stochD)?t.stochD.toFixed(0):'-'),st)+_gauge(t.stochK,20,80);
  }
  if(_num(t.macdHist)){
    var mt=t.macdHist>0?(t.macdHist>=(t.macdHistPrev||0)?_tag('BULL RISING',G):_tag('BULL FADING',A)):(t.macdHist<=(t.macdHistPrev||0)?_tag('BEAR FALLING',R):_tag('BEAR EASING',A));
    o+=_trow('MACD hist',(t.macdHist>=0?'+':'')+t.macdHist.toFixed(2),mt);
    o+=_trow('MACD / signal',t.macd.toFixed(2)+' / '+t.macdSignal.toFixed(2),t.macdCross?_tag(t.macdCross.toUpperCase(),t.macdCross.indexOf('bull')===0?G:R):'');
  }
  if(_num(t.adx)){
    var at=t.adx>=25?(t.plusDI>=t.minusDI?_tag('STRONG UP',G):_tag('STRONG DOWN',R)):_tag('NO TREND',M);
    o+=_trow('ADX (14)',t.adx.toFixed(0),at);
    if(_num(t.plusDI))o+=_trow('+DI / -DI','<span style="color:'+G+'">'+t.plusDI.toFixed(0)+'</span> / <span style="color:'+R+'">'+t.minusDI.toFixed(0)+'</span>');
  }
  if(_num(t.atrPct))o+=_trow('ATR (14)',CUR+t.atr.toFixed(2)+' &middot; '+t.atrPct.toFixed(1)+'%',t.atrPct>5?_tag('VOLATILE',A):t.atrPct<2?_tag('QUIET',G):'');
  if(_num(t.bbPctB)){
    o+=_trow('Bollinger %B',t.bbPctB.toFixed(0)+'%',t.bbPctB>100?_tag('ABOVE BAND',A):t.bbPctB<0?_tag('BELOW BAND',R):'');
    if(_num(t.bbWidth)){
      var sq=_num(t.bbWidthPctile)&&t.bbWidthPctile<=20;
      o+=_trow('Band width',t.bbWidth.toFixed(1)+'%'+(_num(t.bbWidthPctile)?' <span style="color:'+M+';font-weight:400">p'+t.bbWidthPctile.toFixed(0)+'</span>':''),sq?_tag('SQUEEZE',B):'');
    }
  }
  o+='</div><div class="mv">';
  if(_num(t.rs3m)||_num(t.rs12m)){
    o+='<div class="dh" style="margin-top:14px">Relative Strength vs S&amp;P 500</div>';
    o+=_barRow('3 months',t.rs3m,40)+_barRow('6 months',t.rs6m,60)+_barRow('12 months',t.rs12m,100);
    if(t.rsLineHigh)o+='<div style="font-size:10px;color:'+G+';font-weight:700;margin-top:-2px">&#9650; RS line at a 52-week high</div>';
  }
  o+='<div style="font-size:9px;color:#3d5a78;margin-top:8px;line-height:1.5">Calculated from 1 year of daily closes. Tags are rules of thumb, not signals on their own.</div></div>';
  return o;
}
function tech2HTML(r){
  var t=r.tech||{}; if(!Object.keys(t).length)return '';
  var G='#00d084',A='#ff9f43',R='#ff4757',M='#5a7a9a',B='#3b82f6';
  var o='<div class="mv"><div class="abox" style="margin-top:10px;padding:10px;line-height:1.5">';
  var hd=function(x,top){return '<div style="font-weight:800;font-size:9px;color:var(--text);margin:'+(top?0:10)+'px 0 4px;letter-spacing:.5px">'+x+'</div>';};
  // Moving-average stack
  var m=t.mas||{},names=[['ema10','EMA 10'],['ema21','EMA 21'],['sma20','SMA 20'],['sma50','SMA 50'],['sma100','SMA 100'],['sma200','SMA 200']];
  var above=0,tot=0;
  o+=hd('MOVING AVERAGES',1);
  names.forEach(function(n){var x=m[n[0]];if(!x||!_num(x.v))return;tot++;if(x.d>=0)above++;
    var ar=_num(x.slope)?(x.slope>0?'<span style="color:'+G+'">&#9650;</span>':x.slope<0?'<span style="color:'+R+'">&#9660;</span>':''):'';
    o+=_trow(n[1]+' '+ar,CUR+x.v.toFixed(2)+' <span style="color:'+(x.d>=0?G:R)+';font-weight:400">'+(x.d>=0?'+':'')+x.d.toFixed(1)+'%</span>');});
  if(tot){var ok=_num((m.ema10||{}).v)&&_num((m.ema21||{}).v)&&_num((m.sma50||{}).v)&&m.ema10.v>m.ema21.v&&m.ema21.v>m.sma50.v;
    o+='<div style="font-size:9.5px;margin-top:4px;color:'+(above===tot?G:above>=tot/2?A:R)+'">Price above '+above+' of '+tot+(ok?' &middot; short MAs stacked bullish':'')+'</div>';}
  // Oscillators
  o+=hd('MOMENTUM');
  if(_num(t.willR))o+=_trow('Williams %R',t.willR.toFixed(0),t.willR>-20?_tag('OVERBOUGHT',R):t.willR<-80?_tag('OVERSOLD',G):'');
  if(_num(t.cci))o+=_trow('CCI (20)',t.cci.toFixed(0),t.cci>100?_tag('STRONG',G):t.cci<-100?_tag('WEAK',R):'');
  if(_num(t.roc10))o+=_trow('ROC 10 / 20',_pc(t.roc10)+' / '+_pc(t.roc20));
  // Volume-based
  o+='</div></div><div class="mv"><div class="abox" style="margin-top:10px;padding:10px;line-height:1.5">'+hd('MONEY FLOW',1);
  if(_num(t.mfi))o+=_trow('MFI (14)',t.mfi.toFixed(0),t.mfi>=80?_tag('OVERBOUGHT',R):t.mfi<=20?_tag('OVERSOLD',G):t.mfi>=50?_tag('INFLOW',G):_tag('OUTFLOW',A))+_gauge(t.mfi,20,80);
  if(_num(t.obvTrend))o+=_trow('OBV',(t.obvTrend>=0?'+':'')+t.obvTrend.toFixed(1)+'x',t.obvTrend>0?_tag('ACCUMULATING',G):_tag('DISTRIBUTING',R));
  // Trend tools
  o+=hd('TREND');
  if(_num(t.sar))o+=_trow('Parabolic SAR',CUR+t.sar.toFixed(2),t.sarBull?_tag('UP '+t.sarAge+'D',G):_tag('DOWN '+t.sarAge+'D',R));
  if(t.ichi)o+=_trow('Ichimoku cloud',t.ichi==='above'?'<span style="color:'+G+'">Above</span>':t.ichi==='below'?'<span style="color:'+R+'">Below</span>':'<span style="color:'+A+'">Inside</span>',t.tkCross==='bull'?_tag('TK BULL',G):_tag('TK BEAR',R));
  if(_num(t.keltPos))o+=_trow('Keltner position',t.keltPos.toFixed(0)+'%',t.keltPos>100?_tag('ABOVE',A):t.keltPos<0?_tag('BELOW',R):'');
  if(_num(t.donHi))o+=_trow('20D channel',CUR+t.donLo.toFixed(2)+' - '+CUR+t.donHi.toFixed(2),t.donBreak==='up'?_tag('NEW HIGH',G):t.donBreak==='down'?_tag('NEW LOW',R):'');
  // Overall tally
  var bu=0,be=0,f=function(c){if(c===true)bu++;else if(c===false)be++;};
  f(_num(t.rsi)?t.rsi>=50:null);f(_num(t.macdHist)?t.macdHist>0:null);f(_num(t.stochK)&&_num(t.stochD)?t.stochK>t.stochD:null);
  f(_num(t.plusDI)?t.plusDI>t.minusDI:null);f(_num(t.mfi)?t.mfi>=50:null);f(_num(t.obvTrend)?t.obvTrend>0:null);
  f(typeof t.sarBull==='boolean'?t.sarBull:null);f(t.ichi==='above'?true:t.ichi==='below'?false:null);f(_num(t.cci)?t.cci>0:null);
  f(tot?above>tot/2:null);
  var n=bu+be;
  if(n){var pct=bu/n*100,col=pct>=70?G:pct>=40?A:R,lbl=pct>=70?'MOSTLY BULLISH':pct>=40?'MIXED':'MOSTLY BEARISH';
    o+=hd('INDICATOR TALLY')+
      '<div style="display:flex;height:7px;border-radius:4px;overflow:hidden;background:#1e2d45"><div style="width:'+pct+'%;background:'+G+'"></div><div style="flex:1;background:'+R+'"></div></div>'+
      _trow('<span style="color:'+G+'">'+bu+' bullish</span> / <span style="color:'+R+'">'+be+' bearish</span>','',_tag(lbl,col));}
  o+='</div></div>';
  return o;
}
function _line(vals,w,hgt,col,mn,mx){
  var pts=[],n=vals.length;
  for(var i=0;i<n;i++){var v=vals[i];if(!_num(v))continue;pts.push((i/(n-1)*w).toFixed(1)+','+(hgt-(v-mn)/(mx-mn||1)*hgt).toFixed(1));}
  return '<polyline fill="none" stroke="'+col+'" stroke-width="1.4" points="'+pts.join(' ')+'"/>';
}
function _range(arrs){var mn=Infinity,mx=-Infinity;arrs.forEach(function(a){(a||[]).forEach(function(v){if(_num(v)){if(v<mn)mn=v;if(v>mx)mx=v;}});});return [mn,mx];}
function _pane(title,val,body,h){
  return '<div class="mv" style="margin-top:10px"><div style="display:flex;justify-content:space-between;font-size:9px;color:var(--muted);font-weight:700;letter-spacing:.6px;text-transform:uppercase;margin-bottom:3px"><span>'+title+'</span><span style="font-family:JetBrains Mono;text-transform:none">'+val+'</span></div>'+
    '<svg viewBox="0 0 500 '+h+'" preserveAspectRatio="none" style="width:100%;height:'+h+'px;display:block;background:#070c17;border:1px solid var(--border);border-radius:4px">'+body+'</svg></div>';
}
function indChartsHTML(r){
  var t=r.tech||{},W=500,o='';
  if(t.rsiS&&t.rsiS.length>5){
    var H=70,y=function(v){return (H-v/100*H).toFixed(1);};
    var b='<rect x="0" y="0" width="'+W+'" height="'+y(70)+'" fill="#ff475712"/><rect x="0" y="'+y(30)+'" width="'+W+'" height="'+(H-y(30))+'" fill="#00d08412"/>'+
      '<line x1="0" x2="'+W+'" y1="'+y(70)+'" y2="'+y(70)+'" stroke="#ff475766" stroke-dasharray="3,3"/><line x1="0" x2="'+W+'" y1="'+y(50)+'" y2="'+y(50)+'" stroke="#3d5a7844" stroke-dasharray="2,4"/><line x1="0" x2="'+W+'" y1="'+y(30)+'" y2="'+y(30)+'" stroke="#00d08466" stroke-dasharray="3,3"/>'+
      _line(t.rsiS,W,H,'#a78bfa',0,100);
    o+=_pane('RSI (14), 60D &middot; 70 / 30',_num(t.rsi)?t.rsi.toFixed(1):'',b,H);
  }
  if(t.histS&&t.histS.length>5){
    var H2=80,rg=_range([t.macdS,t.sigS,t.histS]),mx=Math.max(Math.abs(rg[0]),Math.abs(rg[1]))||1,mn=-mx;
    var yy=function(v){return H2-(v-mn)/(mx-mn)*H2;},n=t.histS.length,bw=W/n*0.7,b2='<line x1="0" x2="'+W+'" y1="'+yy(0)+'" y2="'+yy(0)+'" stroke="#3d5a78"/>';
    for(var i=0;i<n;i++){var v=t.histS[i];if(!_num(v))continue;var x=i/(n-1)*W-bw/2,y0=yy(0),y1=yy(v);
      var up=i>0&&_num(t.histS[i-1])?Math.abs(v)>=Math.abs(t.histS[i-1]):true;
      var col=v>=0?(up?'#00d084':'#00d08466'):(up?'#ff4757':'#ff475766');
      b2+='<rect x="'+x.toFixed(1)+'" y="'+Math.min(y0,y1).toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+Math.max(Math.abs(y1-y0),0.5).toFixed(1)+'" fill="'+col+'"/>';}
    b2+=_line(t.macdS,W,H2,'#3b82f6',mn,mx)+_line(t.sigS,W,H2,'#ff9f43',mn,mx);
    o+=_pane('MACD 60D &middot; <span style="color:#3b82f6">MACD</span> <span style="color:#ff9f43">signal</span>',_num(t.macdHist)?'hist '+(t.macdHist>=0?'+':'')+t.macdHist.toFixed(2):'',b2,H2);
  }
  if(t.rsS&&t.rsS.length>5){
    var H3=60,rg3=_range([t.rsS]),pad=(rg3[1]-rg3[0])*0.1||1,last=t.rsS[t.rsS.length-1];
    var b3='<line x1="0" x2="'+W+'" y1="'+(H3-(100-rg3[0]+pad)/(rg3[1]-rg3[0]+2*pad)*H3).toFixed(1)+'" y2="'+(H3-(100-rg3[0]+pad)/(rg3[1]-rg3[0]+2*pad)*H3).toFixed(1)+'" stroke="#3d5a78" stroke-dasharray="3,3"/>'+
      _line(t.rsS,W,H3,last>=100?'#00d084':'#ff4757',rg3[0]-pad,rg3[1]+pad);
    o+=_pane('RS line vs S&amp;P 500, 60D',_num(last)?last.toFixed(1):'',b3,H3);
  }
  return o;
}
function srHTML(r){
  var t=r.tech||{},px=r.price,G='#00d084',R='#ff4757',M='#5a7a9a';
  if(!_num(px))return '';
  var d=function(v){return '<span style="color:'+M+';font-weight:400">'+((v-px)/px*100>=0?'+':'')+((v-px)/px*100).toFixed(1)+'%</span>';};
  var o='<div class="mv"><div class="abox" style="margin-top:12px;padding:10px;line-height:1.5"><div style="font-weight:800;font-size:9px;color:var(--text);margin-bottom:4px;letter-spacing:.5px">SUPPORT &amp; RESISTANCE</div>';
  (t.res||[]).slice().reverse().forEach(function(x){o+=_trow('Resistance'+(x.n>1?' &times;'+x.n:''),'<span style="color:'+R+'">'+CUR+x.v.toFixed(2)+'</span> '+d(x.v));});
  o+='<div style="display:flex;justify-content:space-between;font-size:10px;margin:5px 0;padding:3px 0;border-top:1px dashed #3d5a78;border-bottom:1px dashed #3d5a78"><span style="color:#e8f0fe;font-weight:700">Price</span><span style="font-family:JetBrains Mono;font-weight:700;color:#e8f0fe">'+CUR+px.toFixed(2)+'</span></div>';
  (t.sup||[]).forEach(function(x){o+=_trow('Support'+(x.n>1?' &times;'+x.n:''),'<span style="color:'+G+'">'+CUR+x.v.toFixed(2)+'</span> '+d(x.v));});
  if(!(t.res||[]).length)o+='<div style="font-size:9.5px;color:'+G+';margin-top:4px">No swing resistance overhead in 6 months.</div>';
  o+='</div></div><div class="mv"><div class="abox" style="margin-top:12px;padding:10px;line-height:1.5">';
  if(t.fib){var f=t.fib;
    o+='<div style="font-weight:800;font-size:9px;color:var(--text);margin:0 0 4px;letter-spacing:.5px">FIBONACCI <span style="color:'+M+';font-weight:400">('+(f.up?'pullback of 60D rise':'bounce of 60D fall')+')</span></div>';
    ['0.236','0.382','0.5','0.618','0.786'].forEach(function(k){var v=f.lv[k];if(!_num(v))return;var near=Math.abs(v-px)/px<0.015;
      o+=_trow((parseFloat(k)*100).toFixed(1)+'%',(near?'<span style="color:#ff9f43">&#9679; </span>':'')+CUR+v.toFixed(2)+' '+d(v));});
  }
  if(t.pivots){var p=t.pivots;
    o+='<div style="font-weight:800;font-size:9px;color:var(--text);margin:10px 0 4px;letter-spacing:.5px">PIVOT POINTS <span style="color:'+M+';font-weight:400">(next session)</span></div>'+
      '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px;font-size:9.5px;font-family:JetBrains Mono;text-align:center">'+
      ['R3','R2','R1','S1','S2','S3'].map(function(k){return '<div style="background:#0a1120;border-radius:3px;padding:2px"><div style="color:'+M+';font-size:8px">'+k+'</div><div style="color:'+(k[0]==='R'?R:G)+'">'+(_num(p[k])?p[k].toFixed(2):'-')+'</div></div>';}).join('')+
      '</div>'+_trow('Pivot (P)',CUR+(_num(p.P)?p.P.toFixed(2):'-'),px>=p.P?_tag('ABOVE',G):_tag('BELOW',R));
  }
  return o+'</div></div>';
}
function volStatsHTML(r){
  var t=r.tech||{},G='#00d084',R='#ff4757',A='#ff9f43',M='#5a7a9a';
  if(!_num(t.hv20))return '';
  var o='<div class="mv"><div class="abox" style="margin-top:12px;padding:12px;font-size:11px;border-left-color:#3b82f6;line-height:1.5"><strong style="color:#3b82f6;display:block;margin-bottom:4px;font-size:10.5px">VOLATILITY &amp; RISK</strong>';
  var hvc=t.hv20<t.hv60*0.8?G:t.hv20>t.hv60*1.2?R:'#e8f0fe';
  o+=_trow('Hist. vol 20D / 60D / 1Y','<span style="color:'+hvc+'">'+t.hv20.toFixed(0)+'%</span> / '+t.hv60.toFixed(0)+'% / '+t.hv250.toFixed(0)+'%',t.hv20<t.hv60*0.8?_tag('CONTRACTING',G):t.hv20>t.hv60*1.2?_tag('EXPANDING',R):'');
  if(_num(t.adr20))o+=_trow('Avg daily range (20D)',t.adr20.toFixed(1)+'%');
  if(_num(t.beta))o+=_trow('Beta vs S&amp;P 500',t.beta.toFixed(2),t.beta>1.3?_tag('HIGH',A):t.beta<0.8?_tag('LOW',G):'');
  if(_num(t.corr))o+=_trow('Correlation to S&amp;P',t.corr.toFixed(2));
  if(_num(t.maxDD))o+=_trow('Max drawdown (1Y)','<span style="color:'+R+'">'+t.maxDD.toFixed(1)+'%</span>'+(_num(t.spyMaxDD)?' <span style="color:'+M+';font-weight:400">SPY '+t.spyMaxDD.toFixed(1)+'%</span>':''));
  if(_num(t.curDD))o+=_trow('Off 1Y peak','<span style="color:'+(t.curDD>-10?G:t.curDD>-25?A:R)+'">'+t.curDD.toFixed(1)+'%</span>');
  o+='</div></div><div class="mv"><div class="abox" style="margin-top:12px;padding:12px;font-size:11px;border-left-color:#3b82f6;line-height:1.5"><strong style="color:#3b82f6;display:block;margin-bottom:4px;font-size:10.5px">LAST 60 SESSIONS</strong>';
  if(_num(t.upDays60))o+=_trow('Up days',t.upDays60.toFixed(0)+'%',t.upDays60>=55?_tag('BUYERS',G):t.upDays60<=45?_tag('SELLERS',R):'');
  if(_num(t.bestDay60))o+=_trow('Best / worst day','<span style="color:'+G+'">+'+t.bestDay60.toFixed(1)+'%</span> / <span style="color:'+R+'">'+t.worstDay60.toFixed(1)+'%</span>');
  if(_num(t.gapUps))o+=_trow('Gaps over 2%','<span style="color:'+G+'">'+t.gapUps+' up</span> / <span style="color:'+R+'">'+t.gapDowns+' down</span>');
  if(_num(t.streak)&&t.streak!==0)o+=_trow('Current streak',Math.abs(t.streak)+' '+(t.streak>0?'up':'down')+' day'+(Math.abs(t.streak)>1?'s':''),t.streak>0?_tag('UP',G):_tag('DOWN',R));
  return o+'</div></div>';
}
function _card(title,val,tag,note){
  return '<div class="mv xc" style="margin-top:10px"><div class="abox" style="padding:9px 10px;line-height:1.45">'+
    '<div style="display:flex;justify-content:space-between;align-items:center"><span style="font-weight:800;font-size:9px;color:var(--text);letter-spacing:.5px;text-transform:uppercase">'+title+'</span>'+(tag||'')+'</div>'+
    '<div style="font-family:JetBrains Mono;font-weight:700;font-size:12px;color:#e8f0fe;margin-top:3px">'+val+'</div>'+
    (note?'<div style="font-size:9px;color:var(--muted);margin-top:2px">'+note+'</div>':'')+'</div></div>';
}
function extraCards(r){
  var e=(r.tech||{}).ex||{},G='#00d084',R='#ff4757',A='#ff9f43',M='#5a7a9a',c=[],px=r.price;
  var sp=function(v,col){return '<span style="color:'+col+'">'+v+'</span>';};
  if(_num(e.lrSlope))c.push(_card('Trend quality (50D)',(e.lrSlope>=0?'+':'')+e.lrSlope.toFixed(0)+'%/yr &middot; R&sup2; '+(_num(e.lrR2)?e.lrR2.toFixed(2):'-'),e.lrR2>=0.8?_tag(e.lrSlope>0?'SMOOTH UP':'SMOOTH DOWN',e.lrSlope>0?G:R):e.lrR2<0.4?_tag('CHOPPY',A):'','Log-price regression; R&sup2; near 1 = steady trend'));
  if(_num(e.aroonUp))c.push(_card('Aroon (25)',sp('Up '+e.aroonUp.toFixed(0),G)+' / '+sp('Down '+e.aroonDn.toFixed(0),R),e.aroonUp>=70&&e.aroonDn<=30?_tag('UPTREND',G):e.aroonDn>=70&&e.aroonUp<=30?_tag('DOWNTREND',R):_tag('RANGE',M),'Days since 25-day high / low, as %'));
  if(_num(e.viPlus))c.push(_card('Vortex (14)',sp('VI+ '+e.viPlus.toFixed(2),G)+' / '+sp('VI- '+e.viMinus.toFixed(2),R),e.viPlus>e.viMinus?_tag('BULL',G):_tag('BEAR',R),''));
  if(_num(e.uo))c.push(_card('Ultimate Oscillator',e.uo.toFixed(0),e.uo>70?_tag('OVERBOUGHT',R):e.uo<30?_tag('OVERSOLD',G):e.uo>=50?_tag('BULLISH',G):_tag('WEAK',A),'7 / 14 / 28-day buying pressure'));
  if(_num(e.cmo))c.push(_card('Chande Momentum (14)',(e.cmo>=0?'+':'')+e.cmo.toFixed(0),e.cmo>50?_tag('OVERBOUGHT',R):e.cmo<-50?_tag('OVERSOLD',G):'',''));
  if(_num(e.trix))c.push(_card('TRIX (15)',(e.trix>=0?'+':'')+e.trix.toFixed(3)+'% <span style="color:'+M+';font-weight:400;font-size:10px">sig '+e.trixSig.toFixed(3)+'</span>',e.trix>e.trixSig?_tag('RISING',G):_tag('FALLING',R),'Triple-smoothed momentum'));
  if(_num(e.ao))c.push(_card('Awesome Oscillator',(e.ao>=0?'+':'')+e.ao.toFixed(2)+'% of price',e.ao>=0?(e.aoUp?_tag('BULL RISING',G):_tag('BULL FADING',A)):(e.aoUp?_tag('BEAR EASING',A):_tag('BEAR FALLING',R)),'5 vs 34-day midpoint average'));
  if(_num(e.bullPow))c.push(_card('Elder Ray (13)',sp('Bull '+(e.bullPow>=0?'+':'')+e.bullPow.toFixed(2),e.bullPow>=0?G:R)+' / '+sp('Bear '+(e.bearPow>=0?'+':'')+e.bearPow.toFixed(2),e.bearPow>=0?G:R),e.bullPow>0&&e.bearPow<0?_tag('BALANCED',M):e.bearPow>=0?_tag('STRONG',G):e.bullPow<=0?_tag('WEAK',R):'','High and low vs 13-day EMA'));
  if(_num(e.cmf))c.push(_card('Chaikin Money Flow (20)',(e.cmf>=0?'+':'')+e.cmf.toFixed(3),e.cmf>0.1?_tag('ACCUMULATION',G):e.cmf<-0.1?_tag('DISTRIBUTION',R):_tag('NEUTRAL',M),''));
  if(_num(e.chaikinOsc))c.push(_card('Chaikin Oscillator',(e.chaikinOsc>=0?'+':'')+e.chaikinOsc.toFixed(2)+'x avg vol',e.chaikinOsc>0?_tag('INFLOW',G):_tag('OUTFLOW',R),'3 vs 10-day A/D line'));
  if(_num(e.force))c.push(_card('Force Index (13)',(e.force>=0?'+':'')+e.force.toFixed(2)+'%',e.force>0?_tag('BUYERS',G):_tag('SELLERS',R),'Price change x volume, vs avg $ volume'));
  if(_num(e.vwap20)&&_num(px))c.push(_card('Rolling VWAP',CUR+e.vwap20.toFixed(2)+' <span style="color:'+M+';font-weight:400;font-size:10px">20D</span> &middot; '+CUR+(_num(e.vwap50)?e.vwap50.toFixed(2):'-')+' <span style="color:'+M+';font-weight:400;font-size:10px">50D</span>',px>e.vwap20&&px>e.vwap50?_tag('ABOVE BOTH',G):px<e.vwap20&&px<e.vwap50?_tag('BELOW BOTH',R):_tag('MIXED',A),'Volume-weighted average price paid'));
  return c;
}
function fillGaps(panel,pool){
  if(!pool)return;
  var cards=Array.prototype.slice.call(pool.children),cols=Array.prototype.slice.call(panel.children).filter(function(c){return c!==pool&&c.offsetParent!==null;});
  for(var guard=0;guard<30&&cards.length;guard++){
    var rows={};cols.forEach(function(c){var k=Math.round(c.offsetTop);(rows[k]=rows[k]||[]).push(c);});
    var placed=false;
    Object.keys(rows).forEach(function(k){
      var g=rows[k];if(g.length<2||placed||!cards.length)return;
      var hs=g.map(function(c){return c.getBoundingClientRect().height;});
      var mx=Math.max.apply(null,hs),si=hs.indexOf(Math.min.apply(null,hs)),gap=mx-hs[si];
      if(gap<55)return;
      var card=cards.shift();g[si].appendChild(card);placed=true;
      if(g[si].getBoundingClientRect().height>mx+25)pool.appendChild(card);   // too tall for this gap: put it back, try the next card
    });
    if(!placed)break;
  }
}
function ipoNote(r){
  var t=r.tech||{},n=r.sessions||0;
  var off=_num(r.pctFromHigh)?r.pctFromHigh.toFixed(1)+'% below its post-listing high':'';
  return '<div class="abox" style="margin-bottom:10px;padding:10px;font-size:10.5px;line-height:1.5;border-left-color:#a78bfa;background:#a78bfa0f">'+
    '<strong style="color:#a78bfa;display:block;font-size:10px;letter-spacing:.5px;margin-bottom:3px">RECENT IPO &middot; LISTED '+(r.listDate||'')+'</strong>'+
    '<span style="color:var(--muted)">Only <strong style="color:#e8f0fe">'+n+' sessions</strong> of history. The MA150 / MA200 checks need 150-200 sessions, so they read as not met until then and the SEPA score understates it. '+
    'Minervini judges new issues on their first base after listing instead: a tight, orderly consolidation that holds above the IPO-day low.'+(off?' It is '+off+'.':'')+'</span></div>';
}
var BENCH='the S&amp;P 500';
function fullSummary(r,passed,testable){
  var t=r.tech||{},e=t.ex||{},m=t.mas||{},G='#00d084',R='#ff4757',A='#ff9f43',B='#3b82f6',M='#5a7a9a';
  var f2=function(v){return CUR+v.toFixed(2);},pc=function(v){return (v>=0?'+':'')+v.toFixed(1)+'%';};
  var px=r.price,sec=[],pos=0,neg=0;
  var add=function(ok,w){if(ok===true)pos+=(w||1);else if(ok===false)neg+=(w||1);};

  // ── Trend and stage
  var stg=r.stage||0,stName={1:'Stage 1 (basing / neglect)',2:'Stage 2 (advancing)',3:'Stage 3 (topping)',4:'Stage 4 (declining)'}[stg]||'an unclassified stage';
  var maN=0,maUp=0;['ema10','ema21','sma20','sma50','sma100','sma200'].forEach(function(k){if(m[k]&&_num(m[k].d)){maN++;if(m[k].d>=0)maUp++;}});
  var ma50dn=m.sma50&&_num(m.sma50.slope)&&m.sma50.slope<0, ma200up=m.sma200&&_num(m.sma200.slope)&&m.sma200.slope>0;
  var stacked=_num(r.ma50)&&_num(r.ma150)&&_num(r.ma200)&&r.ma50>r.ma150&&r.ma150>r.ma200;
  add(stg===2?true:null,2);add(stg===4?false:null,2);add(r.sepaScore>=6,2);if(r.sepaScore<=3)neg+=1;
  var tr='It sits in <b>'+stName+'</b> with a trend-template score of <b>'+r.sepaScore+'/7</b>'+(testable?' and '+passed+' of '+testable+' testable SEPA legs met':'')+'. ';
  if(maN)tr+='Price is above <b>'+maUp+' of '+maN+'</b> moving averages'+(stacked?' and the 50 / 150 / 200-day are stacked in uptrend order':' but the long averages are not yet stacked in uptrend order')+'. ';
  if(ma50dn)tr+='The 50-day is still sloping down, so the intermediate trend has not turned. ';
  else if(m.sma50&&_num(m.sma50.slope))tr+='The 50-day is rising. ';
  if(ma200up)tr+='The 200-day is rising, so the long-term trend is up. ';
  if(_num(e.lrSlope))tr+='Over 50 sessions the price has trended '+(e.lrSlope>=0?'up':'down')+' at about '+Math.abs(e.lrSlope).toFixed(0)+'% a year'+(_num(e.lrR2)?(e.lrR2>=0.7?', smoothly':e.lrR2<0.4?', in a choppy way':'')+'':'')+'. ';
  if(_num(t.adx))tr+=(t.adx>=25?'ADX '+t.adx.toFixed(0)+' shows a strong trend'+(t.plusDI>=t.minusDI?' with buyers in control.':' with sellers in control.'):'ADX '+t.adx.toFixed(0)+' says there is no strong trend right now.');
  add(maN?maUp/maN>=0.8:null);add(ma50dn?false:null);add(_num(t.adx)&&t.adx>=25?t.plusDI>=t.minusDI:null);
  sec.push(['Trend &amp; stage',tr]);

  // ── Momentum
  var mo='';
  if(_num(t.rsi))mo+='RSI '+t.rsi.toFixed(0)+(t.rsi>=70?' is overbought':t.rsi<=30?' is oversold':t.rsi>=50?' favours buyers':' favours sellers')+'. ';
  if(_num(t.macdHist))mo+='MACD is '+(t.macdHist>0?'positive':'negative')+' and '+((t.macdHist>=(t.macdHistPrev||0))===(t.macdHist>0)?'strengthening':'fading')+(t.macdCross?' (crossed '+t.macdCross+')':'')+'. ';
  var ob=[];if(_num(t.stochK)&&t.stochK>=80)ob.push('Stochastic '+t.stochK.toFixed(0));if(_num(t.willR)&&t.willR>-20)ob.push('Williams %R '+t.willR.toFixed(0));if(_num(t.bbPctB)&&t.bbPctB>=90)ob.push('Bollinger %B '+t.bbPctB.toFixed(0)+'%');
  if(ob.length)mo+='Short-term it is stretched ('+ob.join(', ')+'), so a pause or pullback would be normal before any further move. ';
  if(_num(t.roc20))mo+='The last 20 sessions returned '+pc(t.roc20)+'.';
  add(_num(t.rsi)?t.rsi>=50:null);add(_num(t.macdHist)?t.macdHist>0:null);
  if(mo)sec.push(['Momentum',mo]);

  // ── Volume
  var vo='',vPos=0,vNeg=0;
  if(_num(r.accDistRatio)){vo+='Over 60 sessions up-day volume is <b>'+r.accDistRatio.toFixed(2)+'x</b> down-day volume'+(r.accDistRatio>=1.2?' - institutions are accumulating':r.accDistRatio>=1?' - slightly more buying than selling':' - more stock has changed hands on down days, a sign of distribution')+'. ';r.accDistRatio>=1?vPos++:vNeg++;}
  if(_num(t.obvTrend)){vo+='On-balance volume is '+(t.obvTrend>0?'rising':'falling')+' over 20 days. ';t.obvTrend>0?vPos++:vNeg++;}
  if(_num(t.mfi)){vo+='Money Flow Index '+t.mfi.toFixed(0)+(t.mfi>=50?' shows net inflow':' shows net outflow')+'. ';t.mfi>=50?vPos++:vNeg++;}
  if(_num(e.cmf)){vo+='Chaikin Money Flow is '+(e.cmf>=0?'+':'')+e.cmf.toFixed(2)+'. ';e.cmf>=0?vPos++:vNeg++;}
  if(vPos+vNeg)vo+='<b>'+(vPos>vNeg+1?'Volume confirms the price action.':vNeg>vPos+1?'Volume does not confirm the price action - the move lacks institutional backing.':'Volume is mixed, so the move is not fully confirmed.')+'</b>';
  add(vPos+vNeg?vPos>vNeg:null,2);
  if(vo)sec.push(['Volume &amp; money flow',vo]);

  // ── Relative strength
  var rs='';
  if(_num(t.rs12m))rs+='Against '+BENCH+' it is '+pc(t.rs12m)+' over 12 months'+(_num(t.rs6m)?', '+pc(t.rs6m)+' over 6':'')+(_num(t.rs3m)?' and '+pc(t.rs3m)+' over 3':'')+'. ';
  if(t.rsLineHigh)rs+='The relative-strength line is at a 52-week high - a leadership trait Minervini looks for, often ahead of price. ';
  else if(_num(t.rs3m)&&_num(t.rs12m)&&t.rs3m<0&&t.rs12m>0)rs+='A long-term leader that has lagged recently; leadership needs to reassert itself. ';
  if(_num(t.beta))rs+='Beta '+t.beta.toFixed(2)+(t.beta>1.3?' - it amplifies market moves.':t.beta<0.8?' - it moves less than the market and mostly on its own news.':'.');
  add(_num(t.rs12m)?t.rs12m>0:null);add(_num(t.rs3m)?t.rs3m>0:null);if(t.rsLineHigh)pos++;
  if(rs)sec.push(['Relative strength',rs]);

  // ── Key levels
  var res=(t.res||[])[0],sup=(t.sup||[])[0],lv='',trigger=null,floor=null;
  var ceilings=[];if(res)ceilings.push(res.v);if(_num(t.donHi)&&t.donHi>px)ceilings.push(t.donHi);if(_num(t.sar)&&!t.sarBull&&t.sar>px)ceilings.push(t.sar);
  var near=ceilings.filter(function(v){return (v-px)/px<=0.04;});
  if(near.length)trigger=Math.max.apply(null,near);else if(ceilings.length)trigger=Math.min.apply(null,ceilings);
  if(res)lv+='Nearest resistance '+f2(res.v)+' ('+pc((res.v-px)/px*100)+(res.n>1?', tested '+res.n+' times':'')+'). ';
  else lv+='There is no swing resistance overhead in six months - clear air above. ';
  if(sup){lv+='Nearest support '+f2(sup.v)+' ('+pc((sup.v-px)/px*100)+(sup.n>1?', tested '+sup.n+' times':'')+'). ';floor=sup.v;}
  if(_num(t.donHi))lv+='The 20-day range is '+f2(t.donLo)+' to '+f2(t.donHi)+(t.donBreak==='up'?' and price just broke above it':'')+'. ';
  if(t.fib){var fk=null;['0.236','0.382','0.5','0.618','0.786'].forEach(function(k){var v=t.fib.lv[k];if(_num(v)&&Math.abs(v-px)/px<0.015)fk=k;});if(fk)lv+='Price is sitting on the '+(parseFloat(fk)*100).toFixed(1)+'% Fibonacci level of the 60-day '+(t.fib.up?'rise':'fall')+'. ';}
  if(near.length>=2)lv+='<b>Several ceilings cluster within 4% above ('+near.map(f2).join(', ')+'), making that zone the key hurdle.</b>';
  sec.push(['Key levels',lv]);

  // ── Risk
  var rk='';
  if(_num(t.atrPct))rk+='A typical day moves '+t.atrPct.toFixed(1)+'% ('+f2(t.atr)+'). ';
  if(_num(t.hv20)&&_num(t.hv60))rk+='Volatility is '+(t.hv20<t.hv60*0.8?'contracting - a constructive sign in a base':t.hv20>t.hv60*1.2?'expanding - wider swings than usual':'steady')+' ('+t.hv20.toFixed(0)+'% vs '+t.hv60.toFixed(0)+'% annualised). ';
  if(_num(r.ma50)&&r.ma50<px)rk+='A stop under the 50-day ('+f2(r.ma50)+') risks '+((px-r.ma50)/px*100).toFixed(1)+'%'+((px-r.ma50)/px*100>8?', wider than the 7-8% rule allows':'')+'. ';
  else if(_num(r.ma50))rk+='Price is below the 50-day, so there is no natural stop under it. ';
  if(_num(t.maxDD))rk+='Its worst fall in the past year was '+t.maxDD.toFixed(1)+'%.';
  if(rk)sec.push(['Risk',rk]);

  // ── Verdict
  var score=pos/(pos+neg||1),st=r.status;
  var vd,vc;
  if(stg===2&&score>=0.65&&(st==='breakout'||st==='near-pivot')&&vPos>=vNeg){vd=st==='breakout'?'ACTIONABLE BREAKOUT':'SETUP NEAR PIVOT';vc=G;}
  else if(stg===4||score<0.35){vd='AVOID - DOWNTREND';vc=R;}
  else if(stg===2||score>=0.6){vd='CONSTRUCTIVE - ON WATCH';vc=B;}
  else if(ma50dn&&_num(t.macdHist)&&t.macdHist>0){vd='BOUNCE, NOT YET A TREND';vc=A;}
  else {vd='MIXED - NO EDGE';vc=A;}

  // ── What to watch
  var wt='';
  if(vd==='ACTIONABLE BREAKOUT')wt='Follow-through above '+(trigger?f2(trigger):'the pivot')+' on above-average volume keeps it valid. A close back inside the base, or below the 50-day, says the breakout failed.';
  else if(trigger)wt='Bullish trigger: a close above <b>'+f2(trigger)+'</b> on volume at least 1.5x average'+(vNeg>vPos?' - which would also fix the weak volume picture':'')+'. '+(floor?'If it turns down instead, the first area for buyers is around <b>'+f2(floor)+'</b>'+(_num(r.ma50)&&r.ma50<px&&r.ma50>floor?' (the 50-day at '+f2(r.ma50)+' comes first)':'')+'.':'');
  else wt='No nearby trigger level - wait for a base to form.';
  var trendOK=stacked&&ma200up&&_num(r.ma200)&&px>r.ma200;
  if(stg!==2&&trendOK&&_num(r.accDistRatio)&&r.accDistRatio<1)wt+=' The price structure already meets Stage 2 (above a rising 200-day, averages stacked), but the stage model also needs up-day volume to beat down-day volume over 60 sessions - here it is '+r.accDistRatio.toFixed(2)+'x - so it stays out of Stage 2 until buyers show up in volume.';
  else if(stg!==2&&trendOK)wt+=' The price structure meets Stage 2, but the stage model is not yet convinced the advance is established - recheck after the next base.';
  else if(stg!==2)wt+=' For a SEPA entry it still needs to reach Stage 2: price above a rising 150- and 200-day with the 50-day above both, and up-day volume beating down-day volume.';
  if(r.ipo)wt+=' As a recent listing, judge it on its first orderly base rather than the 200-day rules.';

  var h='<div style=\"font-size:10px;color:var(--muted);line-height:1.55;padding:10px 12px;background:var(--bg3);border-radius:6px;border:1px solid var(--border);border-left:3px solid '+vc+'\">'+
    '<div style=\"display:flex;justify-content:space-between;align-items:center;margin-bottom:6px\"><strong style=\"color:#fff;font-size:10.5px;letter-spacing:.5px\">FULL READ</strong>'+
    '<span style=\"font-size:9px;font-weight:800;color:'+vc+';border:1px solid '+vc+'66;background:'+vc+'14;border-radius:3px;padding:1px 6px\">'+vd+'</span></div>'+
    '<div style=\"display:flex;height:5px;border-radius:3px;overflow:hidden;background:#1e2d45;margin-bottom:3px\"><div style=\"width:'+(score*100).toFixed(0)+'%;background:'+G+'\"></div><div style=\"flex:1;background:'+R+'\"></div></div>'+
    '<div style=\"font-size:9px;margin-bottom:8px\"><span style=\"color:'+G+'\">'+pos+' bullish</span> / <span style=\"color:'+R+'\">'+neg+' bearish</span> weighted signals across SEPA, trend, momentum, volume and relative strength</div>';
  sec.forEach(function(s){h+='<p style=\"margin:0 0 7px\"><strong style=\"color:var(--text)\">'+s[0]+'. </strong>'+s[1]+'</p>';});
  h+='<p style=\"margin:0 0 7px;padding-top:6px;border-top:1px solid var(--border)\"><strong style=\"color:'+vc+'\">What to watch. </strong>'+wt+'</p>';
  h+='<p style=\"margin:0;font-size:9px;color:#3d5a78\">The SEPA method buys strength already in motion and depends on cutting failures quickly; it assumes a trending broad market. Catalysts and the market backdrop are yours to judge. Not financial advice.</p></div>';
  return h;
}
function fillFund(r){
  var out='<div class="mv">';
  // Key stats
  var fwd=(_num(r.trailingEps)&&_num(r.forwardEps)&&r.trailingEps>0)?(r.forwardEps-r.trailingEps)/r.trailingEps*100:null;
  out+='<div class="dh" style="margin-top:14px">Key Stats</div><table class="mat">'+
    _kv('Mkt Cap',r.mktcapFmt||'n/a')+
    _kv('Net Margin',_num(r.netMargin)?_pc(r.netMargin):'<span style="color:#3d5a78">n/a</span>')+
    _kv('EPS (TTM)',_num(r.trailingEps)?CUR+r.trailingEps.toFixed(2):'n/a')+
    _kv('EPS (Fwd)',_num(r.forwardEps)?CUR+r.forwardEps.toFixed(2):'n/a')+
    _kv('Fwd EPS chg',_pc(fwd))+
    '</table>';
  if(r.sector)out+='<div style="font-size:10px;color:#4a6a8a;margin-top:4px">'+r.sector+'</div>';
  out+='</div><div class="mv">';
  // 52-week range
  if(_num(r.lo52)&&_num(r.hi52)&&r.hi52>r.lo52&&_num(r.price)){
    var pos=Math.max(0,Math.min(100,(r.price-r.lo52)/(r.hi52-r.lo52)*100));
    out+='<div class="dh" style="margin-top:14px">52-Week Range</div>'+
      '<div style="position:relative;height:6px;border-radius:3px;background:linear-gradient(90deg,#ff4757,#ff9f43,#00d084);opacity:.85"></div>'+
      '<div style="position:relative;height:10px"><div style="position:absolute;left:calc('+pos+'% - 5px);top:1px;width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:7px solid #e8f0fe"></div></div>'+
      '<div style="display:flex;justify-content:space-between;font-size:9.5px;font-family:JetBrains Mono;color:var(--muted)"><span>'+CUR+r.lo52.toFixed(2)+'</span><span style="color:#e8f0fe">'+CUR+r.price.toFixed(2)+'</span><span>'+CUR+r.hi52.toFixed(2)+'</span></div>'+
      '<table class="mat" style="margin-top:4px">'+
      _kv('Below high',_num(r.pctFromHigh)?'<span style="color:'+(r.pctFromHigh<=15?'#00d084':r.pctFromHigh<=25?'#ff9f43':'#ff4757')+'">'+r.pctFromHigh.toFixed(1)+'%</span>':'n/a')+
      _kv('Above low',_num(r.pctAboveLow)?'<span style="color:'+(r.pctAboveLow>=25?'#00d084':'#ff9f43')+'">'+r.pctAboveLow.toFixed(1)+'%</span>':'n/a')+
      '</table>';
  }
  out+='</div><div class="mv">';
  // Price vs moving averages
  if(_num(r.price)){
    var d=function(m){return _num(m)&&m>0?(r.price-m)/m*100:null;};
    out+='<div class="dh" style="margin-top:14px">Price vs Moving Avgs</div>'+
      _barRow('vs MA50',d(r.ma50),25)+_barRow('vs MA150',d(r.ma150),40)+_barRow('vs MA200',d(r.ma200),50);
  }
  out+='</div><div class="mv">';
  // Performance
  out+='<div class="dh" style="margin-top:14px">Performance</div>'+
    _barRow('Today',r.change,5)+_barRow('5 days',r.chg5d,15)+_barRow('60 days',r.chg60d,40)+_barRow('12 months',r.chg250d,100);
  // Accumulation
  if(_num(r.accDistRatio)){
    var a=r.accDistRatio,ac=a>=1.2?'#00d084':a>=1?'#8bc34a':'#ff4757';
    out+='<table class="mat" style="margin-top:2px">'+_kv('Up/Down vol (60D)','<span style="color:'+ac+'">'+a.toFixed(2)+'x</span>')+'</table>';
  }
  out+='</div>'+techHTML(r);
  return out;
}

function revBars(quarters){
  if(!quarters||!Array.isArray(quarters)||!quarters.length)return'<div style="color:#253550;font-size:10px">No quarterly data</div>';
  var vals=quarters.slice(-5);
  var maxV=1;
  for(var k=0;k<vals.length;k++){if(Math.abs(vals[k][1])>maxV)maxV=Math.abs(vals[k][1]);}
  var out='';
  for(var k=0;k<vals.length;k++){
    var lbl=vals[k][0],val=vals[k][1];
    var col=val>=0?'#00d084':'#ff4757';
    var h=Math.max(Math.round(Math.abs(val)/maxV*40),2);
    var av=Math.abs(val);
    var sign=val<0?'-':'';
    var avM = av / 1000000;
    var fmt=avM>=1000?sign+CUR+(avM/1000).toFixed(1)+'B':sign+CUR+avM.toFixed(0)+'M';
    out+='<div class="rev-bar-wrap">';
    out+='<div class="rev-bar" style="height:'+h+'px;background:'+col+'"></div>';
    out+='<div class="rev-bar-lbl">'+lbl+'</div>';
    out+='<div style="font-size:7px;color:#3d5a78">'+fmt+'</div>';
    out+='</div>';
  }
  return '<div class="rev-bars">'+out+'</div>';
}

function drawCandles(ohlcv,ma50v,price){
  if(!ohlcv||!ohlcv.length)return'<div style="color:#253550;font-size:11px;text-align:center;padding:24px 0">No price history available</div>';
  var W=520,H=188,VH=46,PAD={t:6,r:42,b:18,l:46};
  var cW=W-PAD.l-PAD.r,cH=H-PAD.t-PAD.b;
  var n=ohlcv.length;
  var pMin=Infinity,pMax=-Infinity,vMax=1,avgVol=0;
  for(var i=0;i<n;i++){
    if(ohlcv[i][2]<pMin)pMin=ohlcv[i][2];
    if(ohlcv[i][1]>pMax)pMax=ohlcv[i][1];
    if(ohlcv[i][4]>vMax)vMax=ohlcv[i][4];
    avgVol+=ohlcv[i][4];
  }
  pMin*=0.998; pMax*=1.002;
  avgVol/=n;
  var pRange=pMax-pMin;
  var bW=Math.max(1.5,(cW/n)*0.72);
  function px(i){return PAD.l+(i+0.5)*(cW/n);}
  function py(p){return PAD.t+cH-(p-pMin)/pRange*cH;}
  var s='<svg viewBox="0 0 '+W+' '+(H+VH+6)+'" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%">';
  s+='<defs><linearGradient id="gU" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#00d084" stop-opacity="0.9"/><stop offset="100%" stop-color="#00d084" stop-opacity="0.3"/></linearGradient>';
  s+='<linearGradient id="gD" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#ff4757" stop-opacity="0.9"/><stop offset="100%" stop-color="#ff4757" stop-opacity="0.3"/></linearGradient></defs>';
  s+='<rect x="'+PAD.l+'" y="'+PAD.t+'" width="'+cW+'" height="'+cH+'" fill="#050810" rx="3"/>';
  for(var g=1;g<=3;g++){
    var gy=PAD.t+cH*g/4;
    var gp=pMax-pRange*g/4;
    s+='<line x1="'+PAD.l+'" y1="'+gy+'" x2="'+(PAD.l+cW)+'" y2="'+gy+'" stroke="#1a2540" stroke-width="0.5"/>';
    s+='<text x="'+(PAD.l-3)+'" y="'+(gy+3)+'" text-anchor="end" fill="#3d5a78" font-size="8" font-family="monospace">'+gp.toFixed(2)+'</text>';
  }
  s+='<text x="'+(PAD.l-3)+'" y="'+(PAD.t+5)+'" text-anchor="end" fill="#3d5a78" font-size="8" font-family="monospace">'+pMax.toFixed(2)+'</text>';
  s+='<text x="'+(PAD.l-3)+'" y="'+(PAD.t+cH)+'" text-anchor="end" fill="#3d5a78" font-size="8" font-family="monospace">'+pMin.toFixed(2)+'</text>';
  if(ma50v>=pMin&&ma50v<=pMax){
    var my=py(ma50v);
    s+='<line x1="'+PAD.l+'" y1="'+my+'" x2="'+(PAD.l+cW)+'" y2="'+my+'" stroke="#ff9f43" stroke-width="1" stroke-dasharray="3,2" opacity="0.75"/>';
    s+='<text x="'+(PAD.l+cW+2)+'" y="'+(my+3)+'" fill="#ff9f43" font-size="7">MA50</text>';
  }
  for(var i=0;i<n;i++){
    var op=ohlcv[i][0],hi=ohlcv[i][1],lo=ohlcv[i][2],cl=ohlcv[i][3];
    var up=cl>=op;
    var col=up?'#00d084':'#ff4757';
    var x=px(i);
    var bTop=py(Math.max(op,cl));
    var bBot=py(Math.min(op,cl));
    var bH=Math.max(1,bBot-bTop);
    s+='<line x1="'+x+'" y1="'+py(hi)+'" x2="'+x+'" y2="'+py(lo)+'" stroke="'+col+'" stroke-width="0.8" opacity="0.45"/>';
    s+='<rect x="'+(x-bW/2)+'" y="'+bTop+'" width="'+bW+'" height="'+bH+'" fill="'+col+'" opacity="'+(up?'0.82':'0.92')+'"/>';
  }
  var cpy=py(price);
  if(cpy>=PAD.t&&cpy<=PAD.t+cH){
    s+='<line x1="'+PAD.l+'" y1="'+cpy+'" x2="'+(PAD.l+cW)+'" y2="'+cpy+'" stroke="#e8f0fe" stroke-width="0.6" stroke-dasharray="4,3" opacity="0.3"/>';
    s+='<text x="'+(PAD.l+cW+2)+'" y="'+(cpy+3)+'" fill="#5a7a9a" font-size="7">'+price+'</text>';
  }
  var li=[0,Math.floor(n/2),n-1];
  for(var k=0;k<li.length;k++){
    var daysAgo=n-1-li[k];
    s+='<text x="'+px(li[k])+'" y="'+(PAD.t+cH+14)+'" text-anchor="middle" fill="#2a3d55" font-size="7">'+(daysAgo===0?'today':daysAgo+'d ago')+'</text>';
  }
  var vTop=H+2;
  s+='<rect x="'+PAD.l+'" y="'+vTop+'" width="'+cW+'" height="'+VH+'" fill="#040710" rx="3"/>';
  s+='<text x="'+(PAD.l-3)+'" y="'+(vTop+9)+'" text-anchor="end" fill="#2a3d55" font-size="7">Vol</text>';
  for(var i=0;i<n;i++){
    var op=ohlcv[i][0],cl=ohlcv[i][3],vol=ohlcv[i][4];
    var up=cl>=op;
    var x=px(i);
    var vH2=Math.max(1,(vol/vMax)*(VH-4));
    var isHigh=vol>avgVol*1.4;
    s+='<rect x="'+(x-bW/2)+'" y="'+(vTop+VH-2-vH2)+'" width="'+bW+'" height="'+vH2+'" fill="'+(up?'url(#gU)':'url(#gD)')+'" opacity="'+(isHigh?'1':'0.5')+'"/>';
  }
  var avgH=(avgVol/vMax)*(VH-4);
  s+='<line x1="'+PAD.l+'" y1="'+(vTop+VH-2-avgH)+'" x2="'+(PAD.l+cW)+'" y2="'+(vTop+VH-2-avgH)+'" stroke="#ff9f43" stroke-width="0.5" stroke-dasharray="2,2" opacity="0.4"/>';
  s+='<text x="'+(PAD.l+cW/2)+'" y="'+(vTop+VH)+'" text-anchor="middle" fill="#1e2d45" font-size="7">VOLUME \u2014 bright bars = above-average (buying pressure)</text>';
  s+='</svg>';
  return s;
}

function render(){
  var srt=document.getElementById('srt').value,
      q=document.getElementById('srch').value.toLowerCase(),
      sec=document.getElementById('sec').value;
  var d=D.filter(function(r){
    if(filt==='ipo'){if(!r.ipo)return false;}
    else if(filt!=='all'&&r.status!==filt)return false;
    if(stageFilt&&r.stage!==stageFilt)return false;
    if(sec&&r.sector!==sec)return false;
    if(q&&!r.ticker.toLowerCase().includes(q)&&!r.name.toLowerCase().includes(q))return false;
    return true;
  });
  d.sort(function(a,b){
    if(srt==='sepa') return(b.sepaScore*10+b.vcpScore)-(a.sepaScore*10+a.vcpScore);
    if(srt==='vcp')  return b.vcpScore-a.vcpScore;
    if(srt==='vol')  return b.volRatio-a.volRatio;
    if(srt==='pvr')  return b.pvr-a.pvr;
    if(srt==='fund') return(b.fundScore||0)-(a.fundScore||0);
    if(srt==='p250') return b.chg250d-a.chg250d;
    if(srt==='mc')   return b.mktcap-a.mktcap;
    if(srt==='stage')return(a.stage||1)-(b.stage||1);
    return 0;
  });
  document.getElementById('cnt').textContent=d.length+' shown';
  if(!d.length){document.getElementById('tbody').innerHTML='<tr><td colspan="16"><div class="empty">No stocks match these filters</div></td></tr>';return;}
  document.getElementById('tbody').innerHTML=d.map(function(r,i){return row(r,i);}).join('');
}

function row(r,i){
  var sc=r.sepaScore,pc=sc>=6?'pg':sc>=4?'pa':'pr';
  var ps='';for(var j=0;j<7;j++)ps+='<div class="pip '+(j<sc?pc:'po')+'"></div>';
  var vs='';for(var j=0;j<4;j++)vs+='<div class="vp '+(j<r.vcpScore?'von':'voff')+'"></div>';
  var fs=r.fundScore||0;
  var fps='';for(var j=0;j<3;j++)fps+='<div class="fpip '+(j<fs?'fon':'foff')+'"></div>';
  var bdg=r.status==='breakout'?'<span class="badge bb bb-pulse">BREAKOUT</span>':r.status==='near-pivot'?'<span class="badge bp">NEAR PIVOT</span>':'<span class="badge bw">WATCH</span>';
  var cc=r.change>0?'gn':r.change<0?'rd':'gy';
  var vc=r.volRatio>=2?'vhigh':r.volRatio>=1.5?'vmed':'vlow';
  var p2=r.pvr>=1.5?'pvg':r.pvr>=1?'pvo':'pvw';
  var q2=r.chg250d>=0?'gn':'rd';
  var stg=r.stage||1;
  var sc2=SCOL[stg];
  var stageBdg='<span class="stage-badge" style="color:'+sc2+';background:'+sc2+'18;border:1px solid '+sc2+'40">'+SLBL[stg]+'</span>';
  var vPct=Math.min(100,r.volRatio/3*100);
  var vBc=r.volRatio>=2?'var(--green)':r.volRatio>=1.5?'var(--amber)':'#3d5a78';
  var volCell='<div class="vol-wrap"><span class="'+vc+'">'+r.volRatio+'x</span><div class="vol-track"><div class="vol-fill" style="width:'+vPct+'%;background:'+vBc+'"></div></div></div>';
  var revCell='<span style="color:#253550;font-size:10px">N/A</span>';
  if(r.revGrowth!==null&&r.revGrowth!==undefined){
    var tIco={'accelerating':'\u21911\u2191','growing':'\u2191','flat':'\u2192','declining':'\u2193'};
    var tCol={'accelerating':'#00d084','growing':'#8bc34a','flat':'#ff9f43','declining':'#ff4757'};
    var icon=tIco[r.revTrend]||'';
    var col2=tCol[r.revTrend]||(r.revGrowth>=0?'#5a7a9a':'#ff4757');
    revCell='<span style="color:'+col2+';font-weight:700;font-size:11px">'+icon+' '+(r.revGrowth>=0?'+':'')+r.revGrowth+'%</span>';
  }
  var evCell='<span style="color:#253550;font-size:10px">&mdash;</span>';
  if(r.nextEventLabel){
    var hot=r.nextEventLabel.includes('\u26a1');
    evCell='<span style="color:'+(hot?'var(--gold)':'var(--blue)')+';font-size:10px;font-weight:700">'+r.nextEventLabel+'</span>';
  }
  return '<tr class="main-row" onclick="tog('+i+')" id="mr'+i+'">'+
    '<td style="color:#253550;font-size:10px">'+(i+1)+'</td>'+
    '<td><div class="tkr">'+r.ticker+(r.ipo?'<span style="font-size:8px;font-weight:800;color:#a78bfa;border:1px solid #a78bfa66;background:#a78bfa14;border-radius:3px;padding:0 3px;margin-left:5px;vertical-align:middle" title="Listed '+r.listDate+' - '+r.sessions+' sessions">IPO</span>':'')+'</div><div class="co" title="'+r.name+'">'+r.name+'</div></td>'+
    '<td>'+stageBdg+'</td>'+
    '<td>'+bdg+'</td>'+
    '<td><div style="display:flex;align-items:center;gap:3px"><div class="pips">'+ps+'</div><span style="font-size:10px;color:var(--muted)">'+sc+'</span></div></td>'+
    '<td><div class="vpips">'+vs+'</div></td>'+
    '<td><span class="pv">'+CUR+r.price+'</span></td>'+
    '<td><span class="'+cc+'">'+(r.change>0?'+':'')+r.change+'%</span></td>'+
    '<td>'+volCell+'</td>'+
    '<td><span class="'+p2+'">'+r.pvr+'</span></td>'+
    '<td><div class="fpips" style="display:flex;gap:2px">'+fps+'</div><span style="font-size:9px;color:var(--muted);margin-left:3px">'+fs+'/3</span></td>'+
    '<td style="white-space:nowrap">'+revCell+'</td>'+
    '<td style="white-space:nowrap">'+evCell+'</td>'+
    '<td><span class="'+q2+'">'+(r.chg250d>=0?'+':'')+r.chg250d+'%</span></td>'+
    '<td class="mc">'+r.mktcapFmt+'</td>'+
    '<td class="sec" title="'+r.sector+'">'+r.sector+'</td>'+
    '</tr>'+
    '<tr class="drow" id="d'+i+'" style="display:none"><td colspan="16">'+det(r)+'</td></tr>';
}

function det(r){
  var c=r.checks;
  var stg=r.stage||1;
  var sc2=SCOL[stg];
  var crows=[[c.ma50,CUR+r.price+' > MA50 ('+CUR+(r.ma50?r.ma50.toFixed(2):'0')+')'],[c.ma150,'MA50 > MA150 ('+CUR+(r.ma150?r.ma150.toFixed(2):'0')+')'],[c.ma200,'MA150 > MA200 ('+CUR+(r.ma200?r.ma200.toFixed(2):'0')+')'],[c.trend,'200-day MA trending up (12M: '+(r.chg250d>=0?'+':'')+r.chg250d+'%)'],[c.high,'Within 25% of 52W high ('+r.pctFromHigh+'% below)'],[c.low,'25%+ above 52W low ('+r.pctAboveLow+'% above)'],[c.vol,'Volume breakout >=1.5x ('+r.volRatio+'x), PVR '+r.pvr]].map(function(p){return '<div class="cr '+(p[0]?'ok':'no')+'"><span class="ci">'+(p[0]?'\\u2713':'\\u2717')+'</span>'+p[1]+'</div>';}).join('');

  var stageBox='<div class="stage-info-box" style="color:'+sc2+';background:'+sc2+'0d;border-color:'+sc2+'33">'+
    '<strong>'+SLBL[stg]+'</strong> \u2014 '+SDESC[stg]+
    '</div>';
  
  var vd=['No contraction','Weak (1/4)','Moderate (2/4)','Good (3/4) \\u2014 VCP forming','Ideal (4/4) \\u2014 textbook base'][r.vcpScore];
  var ac=r.status==='breakout'?'abuy':r.status==='near-pivot'?'awch':'ahld';
  var at=r.status==='breakout'?'\\u2192 BUY ZONE: Consider entry. Stop-loss below MA50. Risk 1-2%.':r.status==='near-pivot'?'\\u2192 WATCHLIST: Alert at pivot high. Enter on breakout with vol >1.5x.':'\\u2192 MONITOR: Wait for VCP to tighten and volume to dry up.';
  var rg=r.revGrowth,eg=r.epsGrowth,nm=r.netMargin,te=r.trailingEps,fe=r.forwardEps,fs=r.fundScore||0;
  var fp2='';for(var j=0;j<3;j++)fp2+='<div class="fpip" style="display:inline-block;width:9px;height:9px;border-radius:2px;background:'+(j<fs?'#ff9f43':'#1a2540')+';border:1px solid '+(j<fs?'#ff9f43':'#1e2d45')+'"></div>&nbsp;';

  var fundCol='<div style="min-width:0">'+
    '<div class="dh">Net Revenue &nbsp;'+fp2+'</div>'+
    revTrendChip(r.revTrend)+
    revBars(r.revQuarters)+
    '<table class="mat">'+
    '<tr><td class="mlb">Rev YoY</td><td class="mgv">'+fmtGrowth(rg)+'</td></tr>'+
    '<tr><td class="mlb">EPS Grw</td><td class="mgv">'+fmtGrowth(eg,10,0)+'</td></tr>'+
    '</table>'+
    fillFund(r)+
    '</div>';
    
  var evHtml='<div class="ev-none">No upcoming events</div>';
  var evLines=[];
  if(r.nextEventLabel){
    var hot=r.nextEventLabel.includes('\\u26a1');
    evLines.push('<div class="'+(hot?'ev-hot':'ev-soon')+'">'+r.nextEventLabel+'</div>');
  }
  if(r.nextExDiv)evLines.push('<div class="ev-div">\\u1F4B0 Ex-Div: '+r.nextExDiv+'</div>');
  if(evLines.length)evHtml=evLines.join('');
  
  var entry=r.price,stop=r.ma50||(r.price*0.93),risk=entry-stop;
  var target=risk>0?(entry+2*risk).toFixed(2):null;
  var tlBox='<div class="tl-box" style="padding:10px 8px;margin-bottom:8px">'+
    '<div class="tl-title" style="font-size:9px;margin-bottom:6px">\\u26A1 TRADE LEVELS</div>'+
    '<div style="display:flex;flex-direction:column;gap:5px">'+
    '<div style="background:#081a0f;border:1px solid rgba(0,208,132,.25);border-radius:4px;padding:4px;text-align:center"><div style="font-size:7px;color:#5a7a9a;margin-bottom:2px">BUY ABOVE</div><div style="font-size:11px;font-weight:700;color:#00d084">'+CUR+entry.toFixed(2)+'</div></div>'+
    '<div style="background:#1a0809;border:1px solid rgba(255,71,87,.25);border-radius:4px;padding:4px;text-align:center"><div style="font-size:7px;color:#5a7a9a;margin-bottom:2px">STOP LOSS</div><div style="font-size:11px;font-weight:700;color:#ff4757">'+CUR+stop.toFixed(2)+'</div></div>'+
    '</div></div>';

  var _bp = (function(){
    var oc = r.ohlcv || [];
    if(oc.length < 30) return null;
    var hg = oc.map(function(x){return x[1];});
    var lo = oc.map(function(x){return x[2];});
    var n = hg.length;
    var dd = function(from,to){
      from = Math.max(0,from); to = Math.min(n,to);
      var peak=-1, worst=0;
      for(var i=from;i<to;i++){
        if(hg[i]>peak) peak=hg[i];
        if(peak>0){ var d=(peak-lo[i])/peak*100; if(d>worst) worst=d; }
      }
      return worst;
    };
    var w1=dd(n-60,n-25), w2=dd(n-25,n-10), w3=dd(n-10,n);
    var h5=Math.max.apply(null,hg.slice(-5)), l5=Math.min.apply(null,lo.slice(-5));
    var hi60=Math.max.apply(null,hg.slice(Math.max(0,n-60)));
    return { w1:w1, w2:w2, w3:w3,
             tight:(h5-l5)/r.price*100,
             hi60:hi60, fromHi:(hi60-r.price)/hi60*100,
             contracting:(w3<w2 && w2<w1) };
  })();

  var bpHTML='';
  if(_bp){
    var bpRow=function(lbl,val,col){
      return '<div style=\"display:flex;justify-content:space-between;padding:2px 0\"><span style=\"color:var(--muted)\">'+lbl+'</span><strong style=\"color:'+col+'\">'+val.toFixed(1)+'%</strong></div>';
    };
    bpHTML='<div style=\"margin-top:8px;padding-top:8px;border-top:1px solid var(--border);font-size:10px\">'+
      '<div style=\"color:var(--text);font-weight:700;margin-bottom:4px\">Measured pullbacks (deepest high-to-low)</div>'+
      bpRow('Sessions 60-25 ago', _bp.w1, '#5a7a9a')+
      bpRow('Sessions 25-10 ago', _bp.w2, '#8bc34a')+
      bpRow('Last 10 sessions', _bp.w3, '#00d084')+
      '<div style=\"color:'+(_bp.contracting?'#00d084':'#ff9f43')+';margin-top:5px;line-height:1.45\">'+
      (_bp.contracting ? 'Each window is tighter than the one before - a real contraction sequence, which is what the VCP pattern actually requires.' : 'The windows are not tightening in order, so this is not yet a true contraction sequence regardless of the score above.')+
      '</div>'+
      '<div style=\"color:var(--muted);margin-top:6px;line-height:1.45\">'+
      'Last 5 sessions traded in a '+_bp.tight.toFixed(1)+'% range'+(_bp.tight<4?' - tight closes, the classic sign a pivot is near':'')+'. Price is '+_bp.fromHi.toFixed(1)+'% below the 60-day high of '+CUR+_bp.hi60.toFixed(2)+'.'+
      '</div></div>';
  }

  var vcpPointers = ['Base is loose or trending down. Wait for a constructive base to form.', 'Early signs of contraction. Still too loose to buy.', 'Base is forming. Watch for tightening spreads on the right side.', 'Good VCP forming. Volume is drying up. Stalk entry near pivot high.', 'Textbook VCP. Extreme volatility contraction. Prime entry setup on volume breakout.'][r.vcpScore];

  var adr = (r.accDistRatio !== undefined) ? r.accDistRatio : 1.0;
  var vr  = r.volRatio || 0;
  var pv  = r.pvr || 0;

  var adrCol, adrTxt, adrWhy;
  if(adr >= 1.5){ adrCol='#00d084'; adrTxt='Strong Institutional Accumulation';
    adrWhy='Up-day volume is more than 1.5x down-day volume over 60 sessions. Buyers are firmly the aggressive side.'; }
  else if(adr >= 1.2){ adrCol='#8bc34a'; adrTxt='Healthy Buying Bias';
    adrWhy='Clearly more volume on green days than red days. Accumulation is real but not extreme.'; }
  else if(adr >= 1.0){ adrCol='#ff9f43'; adrTxt='Marginal Accumulation';
    adrWhy='Only slightly more volume on up days. The buying edge is thin - not yet convincing.'; }
  else { adrCol='#ff4757'; adrTxt='Distribution - Sellers In Control';
    adrWhy='More volume traded on down days than up days. Supply is dominant.'; }

  var vrCol, vrWhy;
  if(vr >= 1.5){ vrCol='#00d084';
    vrWhy='Well above normal turnover - institutional-size participation today.'; }
  else if(vr >= 0.8){ vrCol='#ff9f43';
    vrWhy='Roughly normal turnover. Nothing unusual in the current session.'; }
  else { vrCol='#8bc34a';
    vrWhy='Volume drying up - constructive if the stock is tightening into a VCP base.'; }

  var pvCol, pvWhy, pvShow;
  if(vr < 1.3){ pvCol='var(--muted)'; pvShow='n/a';
    pvWhy='Not meaningful today - volume is too close to average for this ratio to be stable.'; }
  else if(pv >= 1.1){ pvCol='#00d084'; pvShow=pv.toFixed(2);
    pvWhy='Efficient move - price travelled well for the extra volume. Demand outweighed supply.'; }
  else if(pv >= 0.6){ pvCol='#ff9f43'; pvShow=pv.toFixed(2);
    pvWhy='Mediocre progress for the volume traded. Needs follow-through to confirm.'; }
  else if(pv < 0.15){ pvCol='#ff9f43'; pvShow=pv.toFixed(2);
    pvWhy='Squat - heavy volume with effectively zero net price progress. Every buyer was matched by a seller at the same price. This is ambiguous: it can be a fund absorbing stock (bullish) or a holder unloading into demand (bearish). Read it against Acc/Dist and where price sits in the base, then watch which way the next session breaks.'; }
  else { pvCol='#ff4757'; pvShow=pv.toFixed(2);
    pvWhy='Price badly lagged the volume - buyers turned up but sellers absorbed most of the effort. Leans distribution unless Acc/Dist says otherwise.'; }

  var _flow = (function(){
    var oc = r.ohlcv || [];
    if(!oc.length) return null;
    var acc = function(rows){
      var buy=0, sell=0, mfv=0, vsum=0;
      for(var i=0;i<rows.length;i++){
        var h=rows[i][1], l=rows[i][2], c=rows[i][3], v=rows[i][4];
        var rng=h-l;
        var frac = rng>0 ? (c-l)/rng : 0.5;
        buy += v*frac; sell += v*(1-frac);
        mfv += (rng>0 ? ((c-l)-(h-c))/rng : 0) * v;
        vsum += v;
      }
      return { buy:buy, sell:sell, pct: (buy+sell)>0 ? buy/(buy+sell)*100 : 50, cmf: vsum>0 ? mfv/vsum : 0 };
    };
    var f20 = acc(oc.slice(-20)), f1 = acc(oc.slice(-1));
    var obv=0, obvHist=[];
    for(var k=1;k<oc.length;k++){
      obv += (oc[k][3]>oc[k-1][3] ? oc[k][4] : (oc[k][3]<oc[k-1][3] ? -oc[k][4] : 0));
      obvHist.push(obv);
    }
    var obvRising = obvHist.length>20 ? obvHist[obvHist.length-1] > obvHist[obvHist.length-21] : null;
    return { f20:f20, f1:f1, obvRising:obvRising };
  })();

  var flowHTML='';
  if(_flow){
    var _fb = _flow.f20.pct, _ft = _flow.f1.pct, _cmf = _flow.f20.cmf;
    var _fc = _fb>=55?'#00d084':_fb>=48?'#ff9f43':'#ff4757';
    var _cmfTxt = _cmf>0.05?'net buying pressure':_cmf<-0.05?'net selling pressure':'balanced, with no clear side';
    flowHTML='<div style=\"border-top:1px solid var(--border);margin-top:8px;padding-top:7px\">'+
      '<div style=\"font-size:10px;font-weight:700;color:var(--text);margin-bottom:5px\">Estimated buy / sell split</div>'+
      '<div style=\"display:flex;height:7px;border-radius:4px;overflow:hidden;margin-bottom:4px\">'+
        '<div style=\"width:'+_fb.toFixed(1)+'%;background:#00d084\"></div>'+
        '<div style=\"width:'+(100-_fb).toFixed(1)+'%;background:#ff4757\"></div>'+
      '</div>'+
      '<div style=\"display:flex;justify-content:space-between;font-size:9.5px;margin-bottom:5px\">'+
        '<span style=\"color:#00d084\">Buy '+_fb.toFixed(0)+'%</span>'+
        '<span style=\"color:var(--muted)\">last 20 sessions</span>'+
        '<span style=\"color:#ff4757\">Sell '+(100-_fb).toFixed(0)+'%</span>'+
      '</div>'+
      '<div style=\"display:flex;justify-content:space-between;font-size:9.5px;padding:2px 0\"><span style=\"color:var(--muted)\">Today</span><strong style=\"color:'+(_ft>=55?'#00d084':_ft>=45?'#ff9f43':'#ff4757')+'\">Buy '+_ft.toFixed(0)+'% / Sell '+(100-_ft).toFixed(0)+'%</strong></div>'+
      '<div style=\"display:flex;justify-content:space-between;font-size:9.5px;padding:2px 0\"><span style=\"color:var(--muted)\">Chaikin Money Flow (20)</span><strong style=\"color:'+_fc+'\">'+(_cmf>=0?'+':'')+_cmf.toFixed(3)+'</strong></div>'+
      '<div style=\"display:flex;justify-content:space-between;font-size:9.5px;padding:2px 0\"><span style=\"color:var(--muted)\">OBV vs 20 sessions ago</span><strong style=\"color:'+(_flow.obvRising?'#00d084':'#ff4757')+'\">'+(_flow.obvRising===null?'n/a':(_flow.obvRising?'Rising':'Falling'))+'</strong></div>'+
      '<div style=\"font-size:9.5px;color:var(--muted);line-height:1.45;margin-top:4px\">Money flow is '+_cmfTxt+'. This split is estimated from where each session closed inside its own range - a close near the high means buyers won the day. It is not the true bid/ask split, which needs tick data the daily feed does not carry.</div>'+
      '</div>';
  }

  var mRow = function(label, val, col, why){
    return '<div style=\"border-top:1px solid var(--border);padding-top:6px;margin-top:6px\">'+
      '<div style=\"display:flex;justify-content:space-between\"><span style=\"color:var(--muted)\">'+label+'</span>'+
      '<strong style=\"color:'+col+'\">'+val+'</strong></div>'+
      '<div style=\"font-size:9.5px;color:var(--muted);line-height:1.45;margin-top:2px\">'+why+'</div></div>';
  };

  var smartMoneyHtml = '<div>'+
    '<div class=\"dh\">Smart Money Indicators</div>'+
    '<div class=\"abox\" style=\"padding:10px;font-size:11px;line-height:1.6;background:var(--bg3);border:1px solid var(--border);border-left:3.5px solid '+adrCol+'\">'+
    '<div style=\"font-size:12px;font-weight:800;color:#fff;margin-bottom:3px\">60D Acc/Dist: <span style=\"color:'+adrCol+'\">'+adr.toFixed(2)+'x</span></div>'+
    '<div style=\"font-size:10px;color:'+adrCol+';font-weight:600;margin-bottom:3px\">'+adrTxt+'</div>'+
    '<div style=\"font-size:9.5px;color:var(--muted);line-height:1.45\">'+adrWhy+'</div>'+
    mRow('Price/Vol (PVR):', pvShow, pvCol, pvWhy)+
    mRow('Vol vs 50D:', vr.toFixed(1)+'x', vrCol, vrWhy)+
    flowHTML+
    '<div style=\"border-top:1px solid var(--border);margin-top:8px;padding-top:6px;font-size:9px;color:var(--muted);line-height:1.5\">'+
      '<strong style=\"color:var(--text)\">How these are built.</strong> '+
      '<b>Acc/Dist</b> adds up all volume on up days and divides it by all volume on down days across the last 60 sessions - above 1.0 means buyers were the aggressive side. This same test also gates the Stage 2 label: a stock cannot be called Advancing unless it is above 1.0. '+
      '<b>Vol vs 50D</b> is the current day volume divided by the 50-day average, so 2.0x means double the usual turnover. '+
      '<b>PVR</b> divides the current day percent price move by the excess volume above average, answering: for all that extra volume, how far did the price actually travel? A low PVR on heavy volume is churning - buyers showed up and sellers absorbed all of it, which Minervini treats as a supply warning. It is shown as n/a below 1.3x volume, where the maths becomes unstable.'+
    '</div>'+
    '</div></div>';

  var candleSigsHTML = '<div style="margin-top:12px"><div class="dh" style="color:var(--gold)">Advanced Price Action Highlights</div>';
  if(r.candleSignals && r.candleSignals.length > 0){
    for(var k=0; k<r.candleSignals && r.candleSignals.length; k++){
      var sig = r.candleSignals[k];
      var ico = sig.includes(\'Pivot\') ? \'\\u26a1\' : sig.includes(\'Squat\') ? \'\\U0001F3CB\' : sig.includes(\'Inside\') ? \'\\U0001F92B\' : \'\\U0001F504\';
      var col = sig.includes(\'Accumulation\') || sig.includes(\'Absorbed\') || sig.includes(\'Pivot\') ? \'#00d084\' : sig.includes(\'Distribution\') ? \'#ff4757\' : \'#ff9f43\';
      var dsc = sig.includes(\'Pivot\')?\'Heavy institutional buying. Yesterdays up volume exceeds highest down volume of past 10 days.\':sig.includes(\'Inside\')?\'Volume has dried up as price tightens. Sellers are exhausted.\':sig.includes(\'Squat\')?\'Large volume prints but price made no progress. Usually masks hidden accumulation (or distribution).\':\'Price undercut previous lows but closed strong. Supply was aggressively absorbed.\';
      candleSigsHTML += \'<div style="background:var(--bg2);padding:9px;border-radius:6px;margin-bottom:6px;border:1px solid var(--border);border-left:3px solid \'+col+\'\">\'+
        \'<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px\"><span style=\"font-size:13px\">\'+ico+\'</span><span style=\"font-size:11px;font-weight:700;color:\'+col+\'\">\'+sig+\'</span></div>\'+
        \'<div style=\"font-size:10px;color:var(--muted);line-height:1.3\">\'+dsc+\'</div></div>\';
    }
  } else {
    candleSigsHTML += \'<div style=\"background:var(--bg2);padding:9px;border-radius:6px;border:1px solid var(--border);font-size:10px;color:var(--muted);line-height:1.3\">No standout anomalies (e.g. Squats) detected in last 5 days. Volume flow remains characteristic of \'+(r.accDistRatio>1.1?\'accumulation\':\'consolidation\')+\'.</div>\';
  }
  candleSigsHTML += \'</div>\';

  var _oc = r.ohlcv || [];
  var _cl = _oc.map(function(x){return x[3];}).filter(function(v){return typeof v==='number'&&isFinite(v);});
  var _hi = _oc.map(function(x){return x[1];}).filter(function(v){return typeof v==='number'&&isFinite(v);});
  var _vo = _oc.map(function(x){return x[4];});
  var _mean = function(a){ if(!a.length) return 0; var t=0; for(var q=0;q<a.length;q++)t+=a[q]; return t/a.length; };
  var _back = function(n){ if(_cl.length>n){ var o=_cl[_cl.length-1-n]; return o>0 ? (r.price-o)/o*100 : null; } return null; };
  var _c10=_back(10), _c20=_back(20);
  var _pivot = _hi.length>=20 ? Math.max.apply(null,_hi.slice(-20)) : null;
  if(_pivot!==null && !(_pivot>0)) _pivot=null;
  var _toPivot = _pivot ? (_pivot-r.price)/r.price*100 : null;
  var _v5 = _vo.length>=5 ? _mean(_vo.slice(-5)) : null;
  var _vAll = _vo.length ? _mean(_vo) : null;
  var _vdu = (_v5 && _vAll) ? _v5/_vAll : null;
  var _extMa50 = r.ma50 ? (r.price-r.ma50)/r.ma50*100 : null;
  var _sep = (r.ma50 && r.ma200) ? (r.ma50-r.ma200)/r.ma200*100 : null;
  var _sgn = function(v){ return (v>=0?'+':'')+v.toFixed(1)+'%'; };

  var nuances = [];

  if(_pivot!==null){
    if(r.price >= _pivot*0.999){
      nuances.push('Price is at the 20-day high of '+CUR+_pivot.toFixed(2)+' - the breakout is happening now, not pending. Volume today is '+r.volRatio.toFixed(1)+'x average, and the 1.5x threshold is what separates a real break from a fade.');
    } else {
      nuances.push('The 20-day high is '+CUR+_pivot.toFixed(2)+', '+_toPivot.toFixed(1)+'% above the current '+CUR+r.price.toFixed(2)+'. '+(_toPivot>10?'That gap is too wide to trade as a pivot - the stock has to build a tighter right side before an entry exists':'Set the alert there and require volume above 1.5x on the break; buying below the pivot is anticipating rather than confirming')+'.');
    }
  }

  if(stg===2 && _extMa50!==null && _sep!==null){
    nuances.push('Stage 2 has real separation, not a marginal cross: price is '+_sgn(_extMa50)+' above the MA50 and the MA50 sits '+_sgn(_sep)+' above the MA200'+(_extMa50>10?'. That said, '+_extMa50.toFixed(1)+'% above the MA50 is extended - a stop at the MA50 forces a wide risk band':'')+'.');
  } else if(stg!==2 && _extMa50!==null){
    var _cn={ma50:'price above MA50',ma150:'MA50 above MA150',ma200:'MA150 above MA200',trend:'200-day MA rising',high:'within 25% of the 52W high',low:'well clear of the 52W low',vol:'volume breakout'};
    var _failed = r.checks ? Object.keys(r.checks).filter(function(k){return !r.checks[k];}).map(function(k){return _cn[k]||k;}) : [];
    nuances.push('Trend structure is incomplete: price is '+_sgn(_extMa50)+' vs the MA50, and the trend template still fails on '+(_failed.length?_failed.join('; '):'at least one leg')+'. Until those close, this is a watch item rather than a Stage 2 entry.');
  }

  if(_c20!==null && _c10!==null && r.chg5d!==null){
    var _tight = Math.abs(r.chg5d) < Math.abs(_c10) && Math.abs(_c10) < Math.abs(_c20);
    nuances.push('Swing sizes: '+_sgn(_c20)+' over 20 sessions, '+_sgn(_c10)+' over 10, '+_sgn(r.chg5d)+' over the last 5. '+(_tight?'Each leg is shallower than the one before - that stepwise contraction is exactly what the VCP thesis rests on':'The legs are not contracting in order yet, so the base is still loose and no clean pivot has formed')+'. Scored '+r.vcpScore+'/4.');
  }

  if(_vdu!==null){
    nuances.push('Volume across the last 5 sessions is running at '+(_vdu*100).toFixed(0)+'% of the 60-day average - '+(_vdu<0.8?'supply is drying up, which is the tell that sellers are finished and the base is ready':'still active, so the base has not gone quiet yet and the pivot is less reliable')+'.');
  }

  if(r.accDistRatio){
    nuances.push('Up-day volume is '+r.accDistRatio.toFixed(2)+'x down-day volume over 60 sessions, so buyers accounted for roughly '+(r.accDistRatio/(1+r.accDistRatio)*100).toFixed(0)+'% of everything traded in the base.');
  }

  if(r.revGrowth!==null && r.revGrowth!==undefined){
    nuances.push('Behind the chart: revenue '+(r.revGrowth>=0?'+':'')+r.revGrowth+'% YoY'+(r.netMargin!==null&&r.netMargin!==undefined?' at a '+r.netMargin+'% net margin':'')+(r.epsGrowth!==null&&r.epsGrowth!==undefined?', EPS '+(r.epsGrowth>=0?'+':'')+r.epsGrowth+'%':'')+'. Fundamental score '+(r.fundScore||0)+'/3.');
  }

  if(r.daysToEvent!==null && r.daysToEvent!==undefined && r.daysToEvent<=21){
    nuances.push('A scheduled event lands in '+r.daysToEvent+' days. Entering a breakout into a report means holding gap risk that no stop can protect against - either size down or wait for the print.');
  }

  if(r.candleSignals && r.candleSignals.some(function(x){return x.indexOf('Pivot')>-1;})) nuances.push('A pocket pivot fired inside the base: an up-day volume print larger than any down-day volume of the prior 10 sessions. That is institutional buying entering before the breakout is obvious.');

  if(nuances.length===0) nuances.push('Not enough price history to build a read on this one yet.');

  var risks = [];
  if(stg!==2) risks.push('Not Stage 2. The trend template is unconfirmed, so buying here anticipates a stage change rather than trading one.');
  if(r.accDistRatio<1.0) risks.push('Down-day volume exceeds up-day volume over 60 sessions ('+r.accDistRatio.toFixed(2)+'x). Distribution is running underneath the price action.');
  else if(r.accDistRatio<1.2) risks.push('Acc/Dist is only '+r.accDistRatio.toFixed(2)+'x. The buying edge is too thin to call this institutional accumulation.');
  if(r.pctFromHigh>15) risks.push('Trading '+r.pctFromHigh+'% below the 52W high. Too deep in the base for a pivot entry - the right side has not formed yet.');
  if(r.vcpScore<2) risks.push('VCP score '+r.vcpScore+'/4. The base is still loose; volatility has not contracted enough to define a pivot.');
  if(r.status==='breakout' && r.volRatio<1.5) risks.push('Breakout is running on only '+r.volRatio.toFixed(1)+'x volume. The 1.5x threshold matters - breakouts without volume confirmation fail at a high rate.');
  if(r.revGrowth!==null && r.revGrowth!==undefined && r.revGrowth<0) risks.push('Revenue down '+r.revGrowth+'% YoY. The chart is ahead of the business; full SEPA wants both moving together.');
  if(r.epsGrowth!==null && r.epsGrowth!==undefined && r.epsGrowth<0) risks.push('EPS down '+r.epsGrowth+'% YoY. There is no earnings engine behind the price move.');
  if(r.fundScore===0) risks.push('Fundamental score 0/3. This is a purely technical setup with no revenue or earnings confirmation.');
  if(risks.length===0) risks.push('No material counter-evidence in the data. The residual risk is market-level: a broad index reversal drags most leaders down with it.');

  var tmEntry = r.price, tmStop = r.ma50 || (r.price*0.93), tmHTML;
  if(tmStop >= tmEntry){
    tmHTML = 'Price sits below its MA50, so an MA50 stop would land above the entry. There is no valid risk level here yet - treat this as a base-building candidate to watch, not an entry.';
  } else {
    var rPct = (tmEntry-tmStop)/tmEntry*100;
    var maxPos = 100/rPct;
    var tgt = tmEntry + 2*(tmEntry-tmStop);
    tmHTML = 'Entry '+CUR+tmEntry.toFixed(2)+', stop at MA50 '+CUR+tmStop.toFixed(2)+' = <strong style=\"color:#ff9f43\">'+rPct.toFixed(1)+'% risk</strong> per share. '+
      'To cap a full stop-out at 1% of your account, size this at no more than <strong style=\"color:var(--gold)\">'+maxPos.toFixed(1)+'% of capital</strong>. '+
      'A 2R target sits at <strong style=\"color:#00d084\">'+CUR+tgt.toFixed(2)+'</strong>.'+
      (rPct>10 ? ' <span style=\"color:#ff4757\">A stop more than 10% away breaches the standard risk ceiling - wait for a tighter entry nearer the pivot.</span>' : '')+
      (maxPos>25 ? ' <span style=\"color:var(--muted)\">The tight stop implies a large position; concentration beyond roughly 25% of capital is its own risk regardless of how close the stop sits.</span>' : '');
  }

  var bullets = function(arr, col){
    var out='';
    for(var z=0; z<arr.length; z++){
      out += '<div style=\"display:flex;gap:6px;margin-bottom:6px\"><span style=\"color:'+col+';flex:none\">&#9642;</span><span>'+arr[z]+'</span></div>';
    }
    return out;
  };

  var nuanceHTML = '<div style=\"height:100%\"><div class=\"dh\">Aggressive Strategy Sentiment</div>'+
    '<div class=\"abox\" style=\"padding:12px;font-size:11.5px;border-left-color:var(--gold);background:rgba(212,175,55,.05);line-height:1.55\">'+
    '<strong style=\"color:var(--gold);display:block;margin-bottom:6px;font-size:10.5px\">STOCK VERDICT</strong>'+
    bullets(nuances.slice(0,5), 'var(--gold)')+
    '<div style=\"margin-top:10px;padding-top:9px;border-top:1px solid rgba(212,175,55,.2)\">'+
    '<strong style=\"color:#ff9f43;display:block;margin-bottom:6px;font-size:10.5px\">WHAT ARGUES AGAINST IT</strong>'+
    bullets(risks.slice(0,4), '#ff9f43')+
    '</div>'+
    '<div style=\"margin-top:10px;padding-top:9px;border-top:1px solid rgba(212,175,55,.2)\">'+
    '<strong style=\"color:var(--text);display:block;margin-bottom:6px;font-size:10.5px\">POSITION MATH</strong>'+
    '<div style=\"font-size:10.5px;color:var(--muted);line-height:1.5\">'+tmHTML+'</div>'+
    '</div>'+
    '</div></div>';

  var _rs = (function(){
    try{
      if(typeof D==='undefined' || !D.length || r.chg250d===null || r.chg250d===undefined) return null;
      var better=0, n=0;
      for(var i=0;i<D.length;i++){
        var v=D[i].chg250d;
        if(v!==null && v!==undefined){ n++; if(v < r.chg250d) better++; }
      }
      return n>0 ? Math.round(better/n*100) : null;
    }catch(e){ return null; }
  })();

  var _ruleRow = function(state, text){
    var ico = state===true ? '&#10003;' : state===false ? '&#10007;' : '&#9679;';
    var col = state===true ? '#00d084' : state===false ? '#ff4757' : '#5a7a9a';
    return '<div style=\"display:flex;gap:6px;padding:3px 0;align-items:flex-start\">'+
      '<span style=\"color:'+col+';flex:none;font-size:10px;width:11px\">'+ico+'</span>'+
      '<span style=\"color:'+(state===false?'var(--muted)':'var(--text)')+';font-size:9.5px;line-height:1.4\">'+text+'</span></div>';
  };

  var _tt = [];
  _tt.push(_ruleRow(r.price>r.ma150 && r.price>r.ma200, 'Price above both the 150-day and 200-day moving averages'));
  _tt.push(_ruleRow(r.ma150>r.ma200, 'The 150-day sits above the 200-day'));
  _tt.push(_ruleRow(!!(r.checks && r.checks.trend), 'The 200-day is trending up, not flat or falling'));
  _tt.push(_ruleRow(r.ma50>r.ma150 && r.ma50>r.ma200, 'The 50-day is above both longer averages'));
  _tt.push(_ruleRow(r.price>r.ma50, 'Price is above the 50-day'));
  _tt.push(_ruleRow(r.pctAboveLow>=30, 'At least 30% above the 52-week low (now '+r.pctAboveLow.toFixed(0)+'%)'));
  _tt.push(_ruleRow(r.pctFromHigh<=25, 'Within 25% of the 52-week high (now '+r.pctFromHigh.toFixed(0)+'% below)'));
  _tt.push(_ruleRow(_rs===null?null:(_rs>=70), _rs===null?'Relative strength rank - not computable':'Relative strength in the top 30% (this stock ranks '+_rs+'th percentile of the screened list on 12-month gain)'));
  var _ttPass = (r.price>r.ma150&&r.price>r.ma200)+(r.ma150>r.ma200)+(!!(r.checks&&r.checks.trend))+(r.ma50>r.ma150&&r.ma50>r.ma200)+(r.price>r.ma50)+(r.pctAboveLow>=30)+(r.pctFromHigh<=25)+((_rs!==null&&_rs>=70)?1:0);

  var ttHTML='<div style=\"margin-top:14px\"><div class=\"dh\">Trend Template &#8212; '+_ttPass+'/8</div>'+
    '<div class=\"abox\" style=\"padding:9px;background:var(--bg3);border-left-color:'+(_ttPass>=7?'#00d084':_ttPass>=5?'#ff9f43':'#ff4757')+'\">'+
    _tt.join('')+
    '<div style=\"font-size:9px;color:var(--muted);line-height:1.45;margin-top:6px;border-top:1px solid var(--border);padding-top:5px\">All eight must hold before a stock is considered a Stage 2 candidate. The relative-strength rank is measured against the other names on this screen, not the whole market, so treat it as a guide rather than a true RS rating.</div>'+
    '</div></div>';

  var _entryExt = _pivot ? (r.price-_pivot)/_pivot*100 : null;
  var _stopPct = (r.ma50 && r.ma50<r.price) ? (r.price-r.ma50)/r.price*100 : null;

  var _pb = [];
  _pb.push(_ruleRow(_stopPct===null?null:(_stopPct<=8), _stopPct===null?'Cut every loss at 7-8% below entry - no valid stop level here yet':'Cut every loss at 7-8% below entry (an MA50 stop is '+_stopPct.toFixed(1)+'% away)'));
  _pb.push(_ruleRow(null, 'Risk no more than 1% of the account on any single position - size from the stop, never from conviction'));
  _pb.push(_ruleRow(_entryExt===null?null:(_entryExt<=5 && _entryExt>=-5), _entryExt===null?'Buy only near the pivot':'Buy within about 5% of the pivot (price is '+(_entryExt>=0?'+':'')+_entryExt.toFixed(1)+'% against the 20-day high)'));
  _pb.push(_ruleRow(null, 'Never average down into a losing position - add only to trades already working'));
  _pb.push(_ruleRow(null, 'Keep the average gain at least twice the average loss; a 50% hit rate then still compounds'));
  _pb.push(_ruleRow(null, 'Sell part of the position into strength on the way up rather than round-tripping the whole gain'));
  _pb.push(_ruleRow((r.ma50 && r.price>r.ma50)?true:false, 'Exit if the stock closes below the 50-day on heavy volume'));
  _pb.push(_ruleRow(null, 'Cut size after consecutive losses and add it back only once trades start working again'));
  _pb.push(_ruleRow(null, 'Trade only when the broad market is in a confirmed uptrend - most breakouts fail in a corrective market'));

  var pbHTML='<div style=\"margin-top:10px\"><div class=\"dh\">Risk &amp; Sell Discipline</div>'+
    '<div class=\"abox\" style=\"padding:9px;background:var(--bg3);border-left-color:var(--gold)\">'+
    _pb.join('')+
    '<div style=\"font-size:9px;color:var(--muted);line-height:1.45;margin-top:6px;border-top:1px solid var(--border);padding-top:5px\">Ticks and crosses mark the rules this screen can measure. Grey dots are judgement calls the data cannot decide for you - they are here as a checklist, not a verdict.</div>'+
    '</div></div>';

  var _scoreCard = (function(){
    var P = function(state,title,headline,body){ return {state:state,title:title,headline:headline,body:body}; };
    var pills = [];

    var cn={ma50:'price above the 50-day',ma150:'the 50-day above the 150-day',ma200:'the 150-day above the 200-day',trend:'a rising 200-day',high:'being within 25% of the 52-week high',low:'being well clear of the 52-week low',vol:'a volume breakout'};
    var failed = r.checks ? Object.keys(r.checks).filter(function(k){return !r.checks[k];}).map(function(k){return cn[k]||k;}) : [];
    pills.push(P(
      _ttPass>=7?'pass':_ttPass>=5?'partial':'fail',
      'Trend',
      'Trend Template '+_ttPass+'/8, currently Stage '+stg,
      _ttPass>=7
        ? 'The structure is in place: price sits above all three moving averages with the shorter ones leading, and the 200-day is rising. This is the gate - Minervini does not buy a stock that fails it, no matter how good the story is.'
        : 'The structure is incomplete'+(failed.length?', failing on '+failed.join(', ')+'':'')+'. A stock outside a confirmed uptrend is a watch item, not a candidate, because the whole method rests on joining a move that is already underway.'
    ));

    var fs = r.fundScore||0;
    var rgv = (r.revGrowth===null||r.revGrowth===undefined)?null:r.revGrowth;
    var egv = (r.epsGrowth===null||r.epsGrowth===undefined)?null:r.epsGrowth;
    var fBody;
    if(rgv===null && egv===null){ fBody='No revenue or earnings data came back for this name, so the fundamental leg cannot be tested. Treat the setup as technical only.'; }
    else {
      fBody='Revenue '+(rgv===null?'unknown':(rgv>=0?'+':'')+rgv+'% YoY')+', EPS '+(egv===null?'unknown':(egv>=0?'+':'')+egv+'%')+(r.netMargin!==null&&r.netMargin!==undefined?', net margin '+r.netMargin+'%':'')+'. ';
      fBody += (rgv!==null&&rgv<0)||(egv!==null&&egv<0)
        ? 'The business is going backwards while the chart holds up. Minervini wants both moving together - price leading earnings is how momentum trades turn into value traps.'
        : 'Earnings and revenue are pointing the same way as the chart, which is the confirmation the method looks for.';
    }
    pills.push(P(fs>=3?'pass':fs>=1?'partial':'fail','Fundamentals','Fundamental score '+fs+'/3',fBody));

    var cBody='This screen only knows scheduled dates. A genuine catalyst is a reason institutions started buying - a contract, an approval, a new product, a management change - and that has to be found in announcements, not in price data. ';
    var cState='manual';
    if(r.nextEventLabel || r.daysToEvent!==null&&r.daysToEvent!==undefined){
      cBody += 'A scheduled event is '+(r.daysToEvent!==null&&r.daysToEvent!==undefined?r.daysToEvent+' days out':'on the calendar')+', which is a date to plan around rather than a catalyst in itself.';
    } else {
      cBody += 'Nothing is on the calendar in the near term.';
    }
    pills.push(P(cState,'Catalyst','Not assessable from price data',cBody));

    var eState, eBody;
    if(_pivot===null){ eState='manual'; eBody='Not enough price history to locate a pivot.'; }
    else {
      var near = Math.abs(_entryExt)<=5;
      var tightOK = _bp ? _bp.contracting : false;
      eState = (near && tightOK) ? 'pass' : near ? 'partial' : 'fail';
      eBody='The 20-day high is '+CUR+_pivot.toFixed(2)+' and price is '+(_entryExt>=0?'+':'')+_entryExt.toFixed(1)+'% against it. '+
        (tightOK?'Pullbacks are contracting window over window, so a real pivot has formed.':'Pullbacks are not contracting in order yet, so no clean pivot has formed'+(near?' even though price is close to the high':'')+'.')+
        (_vdu!==null?' Volume over the last 5 sessions is '+(_vdu*100).toFixed(0)+'% of the 60-day average'+(_vdu<0.8?', the dry-up that usually precedes a break.':', so the base has not gone quiet.'):'');
    }
    pills.push(P(eState,'Entry Point',_pivot===null?'No pivot':'Pivot '+CUR+_pivot.toFixed(2),eBody));

    var xState, xBody, xHead;
    if(_stopPct===null){ xState='manual'; xHead='No valid stop'; xBody='Price is below its 50-day, so that stop would sit above the entry. There is no defined risk here, which means there is no trade.'; }
    else {
      xState = _stopPct<=8?'pass':_stopPct<=10?'partial':'fail';
      xHead = _stopPct.toFixed(1)+'% risk to the 50-day';
      xBody='A stop at the 50-day is '+_stopPct.toFixed(1)+'% below the current price, so a 1% account risk caps the position at about '+(100/_stopPct).toFixed(1)+'% of capital. '+
        (_stopPct<=8?'That sits inside the 7-8% loss ceiling the method depends on.':'That is wider than the 7-8% ceiling - either wait for a tighter entry or accept a smaller position.')+((100/_stopPct)>25?' Note that a stop this tight implies a large position; concentration past roughly 25% of capital is its own risk.':'')+
        ' The exit rules matter more than the entry: the edge comes from keeping the average gain at least twice the average loss, not from picking more winners.';
    }
    pills.push(P(xState,'Exit and Risk',xHead,xBody));

    return pills;
  })();

  var scHTML = (function(){
    var col={pass:'#00d084',partial:'#ff9f43',fail:'#ff4757',manual:'#5a7a9a'};
    var ico={pass:'&#10003;',partial:'&#9679;',fail:'&#10007;',manual:'&#9679;'};
    var lbl={pass:'Met',partial:'Partial',fail:'Not met',manual:'Manual check'};
    var passed=0, testable=0;
    for(var i=0;i<_scoreCard.length;i++){ if(_scoreCard[i].state!=='manual'){ testable++; if(_scoreCard[i].state==='pass') passed++; } }
    var rows='';
    for(var j=0;j<_scoreCard.length;j++){
      var pl=_scoreCard[j], c=col[pl.state];
      rows += '<div style=\"border-left:3px solid '+c+';background:var(--bg2);border-radius:5px;padding:8px 10px;margin-bottom:6px\">'+
        '<div style=\"display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px\">'+
        '<span style=\"font-size:10.5px;font-weight:800;color:#fff\">'+(j+1)+'. '+pl.title+'</span>'+
        '<span style=\"font-size:9px;color:'+c+';font-weight:700\">'+ico[pl.state]+' '+lbl[pl.state]+'</span></div>'+
        '<div style=\"font-size:9.5px;color:'+c+';margin-bottom:3px\">'+pl.headline+'</div>'+
        '<div style=\"font-size:10px;color:var(--muted);line-height:1.5\">'+pl.body+'</div></div>';
    }
    var verdict = passed===testable
      ? 'Every leg this screen can test is satisfied. What is left is the catalyst and the market backdrop, both of which are yours to judge.'
      : passed===0
      ? 'None of the testable legs hold. This is not a SEPA setup in its current state.'
      : passed+' of the '+testable+' testable legs hold. Minervini treats these as cumulative rather than a majority vote - a strong chart does not compensate for a weak business, and neither compensates for a wide stop.';
    return '<div style=\"margin-top:14px\"><div class=\"dh\">SEPA Scorecard &#8212; '+passed+'/'+testable+' testable legs</div>'+
      rows+
      fullSummary(r,passed,testable)+'</div>';
  })();

  var chartCol=\'<div style=\"display:flex;flex-direction:column;gap:12px\">\'+
    \'<div><div class=\"dh\">60-Day Candlestick + Volume (orange dash = MA50)</div>\'+
    drawCandles(r.ohlcv,r.ma50,r.price)+\'</div>\'+
    candleSigsHTML+
    scHTML+
    \'</div>\';

  var sepaCol=\'<div>\'+
    \'<div class=\"dh\">SEPA Checklist \\u2014 \'+r.sepaScore+\'/7</div>\'+
    stageBox+
    \'<div class=\"cl\">\'+crows+\'</div>\'+
    \'<div class=\"pi\" style=\"margin-top:12px\"><span class=\"pk\">5D Chg</span><span class=\"\'+(r.chg5d>=0?\"gn\":\"rd\")+\'\">\'+(r.chg5d>=0?\"+\":\"\")+r.chg5d+\'%</span></div>\'+
    \'<div class=\"pi\"><span class=\"pk\">60D Chg</span><span class=\"\'+(r.chg60d>=0?\"gn\":\"rd\")+\'\">\'+(r.chg60d>=0?\"+\":\"\")+r.chg60d+\'%</span></div>\'+
    \'<div class=\"pi\"><span class=\"pk\">12M Chg</span><span class=\"\'+(r.chg250d>=0?\"gn\":\"rd\")+\'\">\'+(r.chg250d>=0?\"+\":\"\")+r.chg250d+\'%</span></div>\'+
    ttHTML+
    \'</div>\';

  var vcpCol=\'<div>\'+
    \'<div class=\"dh\">Catalysts & VCP Base</div>\'+
    evHtml+
    \'<div><div class=\"dh\" style=\"margin-top:12px;margin-bottom:5px\">Base Progression</div>\'+
    \'<div class=\"abox\" style=\"padding:10px;font-size:11px;border-left-color:var(--blue);line-height:1.4;background:var(--bg3)\">\'+
    \'<strong style=\"color:#fff\">\'+vd+\'</strong><br/><span style=\"color:var(--muted)\">\'+vcpPointers+\'</span>\'+bpHTML+\'</div></div>\'+
    smartMoneyHtml+
    \'</div>\';
    
  var tradeCol=\'<div>\'+
    tlBox+
    \'<div class=\"abox\" style=\"margin-top:6px;padding:10px;line-height:1.6\">\'+
    \'<div style=\"font-weight:800;font-size:9px;color:var(--text);margin-bottom:6px;letter-spacing:0.5px\">SUMMARY</div>\'+(r.analysis || \"Awaiting breakout confirmation.\")+
    \'<div class=\"aact \'+ac+\'\" style=\"margin-top:8px\">\'+at+\'</div></div>\'+
    pbHTML+tech2HTML(r)+
    \'</div>\';

  chartCol=chartCol.slice(0,-6)+indChartsHTML(r)+\'</div>\';
  if(r.ipo)sepaCol=sepaCol.slice(0,5)+ipoNote(r)+sepaCol.slice(5);
  sepaCol=sepaCol.slice(0,-6)+srHTML(r)+\'</div>\';
  nuanceHTML=nuanceHTML.slice(0,-6)+volStatsHTML(r)+\'</div>\';
  return \'<div class=\"dpanel\">\'+chartCol+sepaCol+fundCol+vcpCol+tradeCol+nuanceHTML+\'<div class=\"xpool\" style=\"display:none\">\'+extraCards(r).join(\'\')+\'</div></div>\';
}


function _topMv(col){return Array.prototype.filter.call(col.querySelectorAll('.mv'),function(m){var p=m.parentElement;while(p&&p!==col){if(p.classList.contains('mv'))return false;p=p.parentElement;}return true;});}
function balancePanel(panel){
  if(!panel)return;
  panel.style.alignItems='start';
  var cols=Array.prototype.slice.call(panel.children).filter(function(c){return !c.classList.contains('xpool');});
  for(var it=0;it<40;it++){
    var rows={};cols.forEach(function(c){var k=Math.round(c.offsetTop);(rows[k]=rows[k]||[]).push(c);});
    var moved=false;
    Object.keys(rows).forEach(function(k){
      var g=rows[k];if(g.length<2||moved)return;
      var hs=g.map(function(c){return c.getBoundingClientRect().height;});
      var ti=hs.indexOf(Math.max.apply(null,hs)),si=hs.indexOf(Math.min.apply(null,hs)),diff=hs[ti]-hs[si];
      if(diff<40)return;
      var best=null,bestMax=hs[ti]-20;
      _topMv(g[ti]).forEach(function(b){var h=b.getBoundingClientRect().height+12;if(h<20)return;var m=Math.max(hs[ti]-h,hs[si]+h);if(m<bestMax){bestMax=m;best=b;}});
      if(best){var tgt=g[si];(tgt.lastElementChild&&tgt.children.length===1&&tgt.lastElementChild.tagName==='DIV'&&tgt.lastElementChild.style.height==='100%'?tgt.lastElementChild:tgt).appendChild(best);moved=true;}
    });
    if(!moved)break;
  }
}
function tog(i){
  var el=document.getElementById('d'+i);
  var mr=document.getElementById('mr'+i);
  var showing=el.style.display!=='none';
  el.style.display=showing?'none':'table-row';
  if(mr)mr.classList.toggle('expanded',!showing);
  if(!showing&&!el.dataset.bal){el.dataset.bal='1';requestAnimationFrame(function(){var dp=el.querySelector('.dpanel');balancePanel(dp);fillGaps(dp,dp.querySelector('.xpool'));});}
}
render();
</script>
</body>
</html>"""
    html = tmpl.replace("{stamp_str}", stamp_str).replace("{today_str}", today_str)
    html = html.replace("{ny_str}", ny_str).replace("{cap_str}", cap_str)
    html = html.replace("{json_data}", json_data)
    html = html.replace("{sector_opts}", sector_opts)
    html = html.replace("{top_html}", top_html)
    html = html.replace("{n}", str(n))
    html = html.replace("{len(breakouts)}", str(len(breakouts)))
    html = html.replace("{len(pivots)}", str(len(pivots)))
    html = html.replace("{len(watching)}", str(len(watching)))
    html = html.replace("{len(ipos)}", str(len(ipos)))
    html = html.replace("{len(stage1)}", str(len(stage1)))
    html = html.replace("{len(stage2)}", str(len(stage2)))
    html = html.replace("{len(stage3)}", str(len(stage3)))
    html = html.replace("{len(stage4)}", str(len(stage4)))
    return html
