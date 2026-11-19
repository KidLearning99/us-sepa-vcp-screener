"""
Decision engine shared by the ASX, US and India SEPA+VCP screeners.

- candle_patterns(df): recent candlestick reversal / continuation patterns
- ichimoku(df): full Ichimoku Kinko Hyo reading
- market_state(bench): is the broad market in an uptrend (Minervini's market filter)
- decide(df, bench, market): BUY / ALERT / WAIT / WATCH / AVOID / SELL with prices
- backtest(hist_map, bench): how the exact same BUY rule performed over the past year

Everything here uses only price and volume history, so the live decision and the
backtest apply the same rules. Educational use only; not financial advice.
"""
import math
import pandas as pd
import numpy as np

# Rule parameters (kept in one place so the live rule and the backtest match)
PIVOT_LOOKBACK  = 20     # pivot = highest high of the prior 20 sessions
BREAKOUT_VOL    = 1.5    # breakout volume vs 50-day average
MAX_CHASE       = 0.05   # do not buy more than 5% above the pivot
ALERT_ZONE      = 0.05   # within 5% below the pivot -> set an alert
MAX_STOP        = 0.08   # never risk more than 8% (Minervini's 7-8% rule)
TARGET_1        = 0.20   # Minervini takes part profits around +20-25%
HORIZON         = 60     # backtest: sessions allowed for the trade to work

# SEPA scorecard and position sizing. The sizing checks were chosen from a
# 4-year backtest of ~7,000 breakouts across the US, ASX and India screeners:
# only these separated better from worse breakouts in all three markets.
EXT_MA50_MAX    = 0.25   # more than 25% above the 50-day = extended -> half size
ACC_MIN         = 1.2    # up-day / down-day volume over 50 sessions that counts as accumulation
RS_HIGH         = 0.98   # RS line within 2% of its 1-year high
EVENT_DAYS      = 10     # results due within this many days -> one size step down (gap risk)
RSI_HOT         = 80     # context only


def _f(v, d=2):
    try:
        v = float(v)
        return round(v, d) if math.isfinite(v) else None
    except Exception:
        return None


# ── Candlestick patterns ──────────────────────────────────────────────────────
PATTERN_INFO = {
    "Hammer": ("bullish", "1-candle reversal",
               "Small body near the top with a long lower wick after a decline: sellers pushed the price down but buyers rejected the lower prices."),
    "Inverted Hammer": ("bullish", "1-candle reversal",
               "Small body near the bottom with a long upper wick after a decline: buyers are testing higher prices. Needs a strong next day to confirm."),
    "Shooting Star": ("bearish", "1-candle reversal",
               "Small body near the bottom with a long upper wick after a rise: buyers pushed higher but sellers rejected it."),
    "Hanging Man": ("bearish", "1-candle reversal",
               "Hammer shape appearing after a rise: selling showed up during the day. Needs a weak next day to confirm."),
    "Dragonfly Doji": ("bullish", "1-candle reversal",
               "Open, high and close near the top with a long lower shadow: intraday sellers lost control - a possible turn in an oversold stock."),
    "Gravestone Doji": ("bearish", "1-candle reversal",
               "Open, low and close near the bottom with a long upper shadow: intraday buyers lost control - a possible top."),
    "Bullish Engulfing": ("bullish", "2-candle reversal",
               "A green candle whose body completely swallows the previous red body after a decline: buyers have overwhelmed sellers."),
    "Bearish Engulfing": ("bearish", "2-candle reversal",
               "A red candle whose body completely swallows the previous green body after a rise: sellers have overwhelmed buyers."),
    "Morning Star": ("bullish", "3-candle reversal",
               "A long red candle, a small 'star', then a strong green candle closing past the red candle's midpoint: selling is exhausted and a bottom may be forming."),
    "Evening Star": ("bearish", "3-candle reversal",
               "A long green candle, a small 'star', then a strong red candle closing below the green candle's midpoint: buying is exhausted and a top may be forming."),
    "Three White Soldiers": ("bullish", "3-candle continuation",
               "Three long green candles in a row with small wicks, each closing higher: sustained, heavy buying."),
    "Three Black Crows": ("bearish", "3-candle continuation",
               "Three long red candles in a row with small wicks, each closing lower: sustained, heavy selling."),
}


def candle_patterns(df, lookback=3):
    """Patterns completed in the last `lookback` sessions, newest first."""
    out = []
    if df is None or len(df) < 25 or "Open" not in df:
        return out
    o, h, l, c = (df[k].astype(float).values for k in ("Open", "High", "Low", "Close"))
    v = df["Volume"].astype(float).values if "Volume" in df else None
    body = np.abs(c - o)
    rng = np.maximum(h - l, 1e-9)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    avg_body = pd.Series(body).rolling(20).mean().values
    sma10 = pd.Series(c).rolling(10).mean().values
    vol50 = pd.Series(v).rolling(50, min_periods=20).mean().values if v is not None else None
    n = len(c)

    def down_before(i):   # was the stock falling into bar i?
        j = i - 1
        return j >= 10 and (c[j] < sma10[j] or c[j] < c[max(0, j - 5)])

    def up_before(i):
        j = i - 1
        return j >= 10 and (c[j] > sma10[j] or c[j] > c[max(0, j - 5)])

    green = lambda i: c[i] > o[i]
    red = lambda i: c[i] < o[i]
    long_body = lambda i: avg_body[i] == avg_body[i] and body[i] >= avg_body[i]

    for i in range(n - 1, max(n - 1 - lookback, 24), -1):
        found = []
        doji = body[i] <= 0.1 * rng[i]
        # one-candle shapes
        if doji and upper[i] <= 0.1 * rng[i] and lower[i] >= 0.6 * rng[i] and down_before(i):
            found.append("Dragonfly Doji")
        elif doji and lower[i] <= 0.1 * rng[i] and upper[i] >= 0.6 * rng[i] and up_before(i):
            found.append("Gravestone Doji")
        elif not doji and lower[i] >= 2 * body[i] and upper[i] <= 0.15 * rng[i]:
            if down_before(i): found.append("Hammer")
            elif up_before(i): found.append("Hanging Man")
        elif not doji and upper[i] >= 2 * body[i] and lower[i] <= 0.15 * rng[i]:
            if up_before(i): found.append("Shooting Star")
            elif down_before(i): found.append("Inverted Hammer")
        # two-candle
        p = i - 1
        if red(p) and green(i) and o[i] <= c[p] and c[i] >= o[p] and body[i] > body[p] and down_before(p + 1):
            found.append("Bullish Engulfing")
        if green(p) and red(i) and o[i] >= c[p] and c[i] <= o[p] and body[i] > body[p] and up_before(p + 1):
            found.append("Bearish Engulfing")
        # three-candle
        a, b = i - 2, i - 1
        if red(a) and long_body(a) and body[b] <= 0.35 * body[a] and green(i) and c[i] > (o[a] + c[a]) / 2 and down_before(a + 1):
            found.append("Morning Star")
        if green(a) and long_body(a) and body[b] <= 0.35 * body[a] and red(i) and c[i] < (o[a] + c[a]) / 2 and up_before(a + 1):
            found.append("Evening Star")
        if all(green(k) and long_body(k) and upper[k] <= 0.3 * body[k] for k in (a, b, i)) \
                and c[a] < c[b] < c[i] and o[a] <= o[b] <= c[a] and o[b] <= o[i] <= c[b]:
            found.append("Three White Soldiers")
        if all(red(k) and long_body(k) and lower[k] <= 0.3 * body[k] for k in (a, b, i)) \
                and c[a] > c[b] > c[i] and c[a] <= o[b] <= o[a] and c[b] <= o[i] <= o[b]:
            found.append("Three Black Crows")
        for name in found:
            kind, shape, desc = PATTERN_INFO[name]
            vol_ok = bool(vol50 is not None and vol50[i] == vol50[i] and v[i] > vol50[i])
            out.append({"name": name, "kind": kind, "shape": shape, "desc": desc,
                        "daysAgo": int(n - 1 - i), "date": str(df.index[i].date()),
                        "volConfirm": vol_ok})
    return out


# ── Ichimoku Kinko Hyo ────────────────────────────────────────────────────────
def ichimoku(df):
    if df is None or len(df) < 80:
        return None
    h, l, c = (df[k].astype(float) for k in ("High", "Low", "Close"))
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    span_a_raw = (tenkan + kijun) / 2                                  # plotted 26 ahead
    span_b_raw = (h.rolling(52).max() + l.rolling(52).min()) / 2       # plotted 26 ahead
    px = c.iloc[-1]
    a_now, b_now = span_a_raw.iloc[-27], span_b_raw.iloc[-27]           # cloud under today's bar
    a_fut, b_fut = span_a_raw.iloc[-1], span_b_raw.iloc[-1]             # cloud 26 sessions ahead
    top, bot = max(a_now, b_now), min(a_now, b_now)
    pos = "above" if px > top else ("below" if px < bot else "inside")
    tk = "bull" if tenkan.iloc[-1] > kijun.iloc[-1] else "bear"
    cross_age = None
    diff = (tenkan - kijun).dropna()
    for k in range(1, min(30, len(diff) - 1)):
        if (diff.iloc[-k] > 0) != (diff.iloc[-k - 1] > 0):
            cross_age = k - 1
            break
    chikou_up = bool(px > c.iloc[-27])
    fut_bull = bool(a_fut > b_fut)
    score = sum([pos == "above", tk == "bull", chikou_up, fut_bull]) - sum([pos == "below", tk == "bear", not chikou_up, not fut_bull])
    verdict = ("Strong bullish" if score == 4 else "Bullish" if score >= 2 else
               "Strong bearish" if score == -4 else "Bearish" if score <= -2 else "Neutral")
    return {"tenkan": _f(tenkan.iloc[-1]), "kijun": _f(kijun.iloc[-1]),
            "spanA": _f(a_now), "spanB": _f(b_now), "futA": _f(a_fut), "futB": _f(b_fut),
            "cloudTop": _f(top), "cloudBot": _f(bot), "pos": pos, "tk": tk, "tkCrossAge": cross_age,
            "chikouUp": chikou_up, "chikouRef": _f(c.iloc[-27]), "futBull": fut_bull,
            "thickPct": _f(abs(a_now - b_now) / px * 100, 1), "verdict": verdict, "score": int(score)}


# ── Market filter ─────────────────────────────────────────────────────────────
def market_state(bench):
    """Minervini only buys in a confirmed market uptrend."""
    if bench is None or len(bench) < 210:
        return {"state": "unknown", "label": "Market trend unknown", "allowBuys": True}
    c = bench.astype(float)
    ma50, ma200 = c.rolling(50).mean(), c.rolling(200).mean()
    px = c.iloc[-1]
    a50, a200 = px > ma50.iloc[-1], px > ma200.iloc[-1]
    r50 = ma50.iloc[-1] > ma50.iloc[-21]
    r200 = ma200.iloc[-1] > ma200.iloc[-21]
    off = (px / c.tail(252).max() - 1) * 100
    if a50 and a200 and r50:
        st, lab = "uptrend", "Confirmed uptrend"
    elif a200 and (a50 or r200):
        st, lab = "pressure", "Uptrend under pressure"
    else:
        st, lab = "correction", "Market in correction"
    return {"state": st, "label": lab, "allowBuys": st != "correction",
            "above50": bool(a50), "above200": bool(a200), "ma50Rising": bool(r50),
            "ma200Rising": bool(r200), "offHigh": _f(off, 1), "level": _f(px)}


# ── Rule components (shared by live decision and backtest) ────────────────────
def _frame(df, bench):
    c = df["Close"].astype(float)
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    v = df["Volume"].astype(float) if "Volume" in df else pd.Series(0.0, index=df.index)
    f = pd.DataFrame({"c": c, "h": h, "l": l, "v": v})
    f["ma50"] = c.rolling(50).mean()
    f["ma150"] = c.rolling(150).mean()
    f["ma200"] = c.rolling(200).mean()
    f["ma200_1m"] = f["ma200"].shift(21)
    f["hi252"] = h.rolling(252, min_periods=200).max()
    f["lo252"] = l.rolling(252, min_periods=200).min()
    f["pivot"] = h.shift(1).rolling(PIVOT_LOOKBACK).max()
    f["low10"] = l.rolling(10).min()
    f["vol50"] = v.rolling(50).mean()
    if bench is not None:
        b = bench.astype(float).reindex(c.index).ffill()
        f["rs"] = (c / c.shift(126)) - (b / b.shift(126))
    else:
        f["rs"] = 0.0
    tt = pd.DataFrame({
        "Price above 150 and 200-day": (c > f["ma150"]) & (c > f["ma200"]),
        "150-day above 200-day": f["ma150"] > f["ma200"],
        "200-day rising for a month": f["ma200"] > f["ma200_1m"],
        "50-day above 150 and 200-day": (f["ma50"] > f["ma150"]) & (f["ma50"] > f["ma200"]),
        "Price above 50-day": c > f["ma50"],
        "At least 25% above 52-week low": c >= 1.25 * f["lo252"],
        "Within 25% of 52-week high": c >= 0.75 * f["hi252"],
        "Beating the index over 6 months": f["rs"] > 0,
    })
    f["tt_all"] = tt.all(axis=1)
    _indicators(f, df, bench)
    return f, tt


def _indicators(f, df, bench):
    """Indicator series used to cross-check a breakout. Price/volume only, so the
    live decision and the backtest read exactly the same numbers."""
    c, h, l, v = f["c"], f["h"], f["l"], f["v"]
    # RSI 14 (Wilder)
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    f["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    # MACD 12/26/9 histogram
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    f["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    # ADX 14 with +DI / -DI
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    upm, dnm = h.diff(), -l.diff()
    pdm = upm.where((upm > dnm) & (upm > 0), 0.0)
    mdm = dnm.where((dnm > upm) & (dnm > 0), 0.0)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    mdi = 100 * mdm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    f["adx"], f["pdi"], f["mdi"] = dx.ewm(alpha=1 / 14, adjust=False).mean(), pdi, mdi
    # Relative-strength line vs the index, and how close it is to its 1-year high
    if bench is not None:
        b = bench.astype(float).reindex(c.index).ffill()
        rsl = c / b
        f["rs_line_hi"] = rsl / rsl.rolling(252, min_periods=120).max()
    else:
        f["rs_line_hi"] = np.nan
    # Volume dry-up: the 10 sessions before today vs the 50-day average
    f["dryup"] = v.shift(1).rolling(10).mean() / f["vol50"].shift(1)
    # Accumulation: up-day volume vs down-day volume over 50 sessions
    upv = v.where(d > 0, 0.0).rolling(50).sum()
    dnv = v.where(d < 0, 0.0).rolling(50).sum()
    f["ad_ratio"] = upv / dnv.replace(0, np.nan)
    # Where today's close sits in today's range (1 = at the high)
    f["clv"] = (c - l) / (h - l).replace(0, np.nan)
    f["ext50"] = c / f["ma50"] - 1
    # Ichimoku score (-4..+4), same reading as ichimoku()
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    sa = (tenkan + kijun) / 2
    sb = (h.rolling(52).max() + l.rolling(52).min()) / 2
    top = pd.concat([sa.shift(26), sb.shift(26)], axis=1).max(axis=1)
    bot = pd.concat([sa.shift(26), sb.shift(26)], axis=1).min(axis=1)
    chik = c > c.shift(26)
    f["ichi"] = ((c > top).astype(int) - (c < bot).astype(int)
                 + np.where(tenkan > kijun, 1, -1) + np.where(chik, 1, -1) + np.where(sa > sb, 1, -1))


def _base_windows(h, l):
    """Deepest pullback (from the running high) in three windows of the last 60
    sessions: 60-25, 25-10 and the last 10. Same measure as the dashboard."""
    n = len(h)
    if n < 30:
        return None

    def dd(a, b):
        a, b = max(0, a), min(n, b)
        peak, worst = -1.0, 0.0
        for i in range(a, b):
            if h[i] > peak:
                peak = h[i]
            if peak > 0:
                worst = max(worst, (peak - l[i]) / peak * 100)
        return worst
    return dd(n - 60, n - 25), dd(n - 25, n - 10), dd(n - 10, n)


def _leg(state, title, headline, body):
    return {"state": state, "title": title, "headline": headline, "body": body}


def quality(f, i, df, row=None, pivot=None, entry=None):
    """The SEPA scorecard for session i, built on the same pivot, entry and stop
    as the BUY rule, plus the sizing checks and the context indicators.
    row (live only) adds fundamentals, the next results date and analyst views."""
    row = row or {}
    x = f.iloc[i]
    px = x["c"]
    pivot = x["pivot"] if pivot is None else pivot
    num = lambda v: v is not None and v == v
    dist = (px / pivot - 1) if num(pivot) and pivot else None
    ent = entry if entry else (px if dist is None or 0 <= dist <= MAX_CHASE else pivot * 1.001)
    low10 = x["low10"]
    stop = _stop_for(ent, low10)
    risk = (ent - stop) / ent
    ext = x["ext50"] if num(x["ext50"]) else None
    vr = x["v"] / x["vol50"] if num(x["vol50"]) and x["vol50"] else None
    legs = []

    # 1. Trend - the same 8 rules as the BUY gate
    tt_ok = bool(x["tt_all"])
    legs.append(_leg("pass" if tt_ok else "fail", "Trend",
                     "All 8 trend rules met" if tt_ok else "Trend rules not all met",
                     "Price is above a rising 200-day, the 50-day and 150-day are stacked above it, and the stock is beating the index. This is the gate - no BUY without it."
                     if tt_ok else "The uptrend structure is incomplete, so this is a watch item, not a SEPA candidate."))

    # 2. Fundamentals (live only - there is no history of these for the backtest)
    rg, eg, fs = row.get("revGrowth"), row.get("epsGrowth"), row.get("fundScore") or 0
    if rg is None and eg is None:
        legs.append(_leg("manual", "Fundamentals", "No revenue or earnings data",
                         "Nothing came back for revenue or earnings growth, so this leg cannot be tested. Check the latest results yourself before buying."))
    else:
        neg = (rg is not None and rg < 0) or (eg is not None and eg < 0)
        st = "fail" if neg or fs == 0 else ("pass" if fs >= 3 else "partial")
        parts = ([f"Revenue {rg:+.1f}% YoY"] if rg is not None else ["Revenue growth unknown"]) + \
                ([f"EPS {eg:+.1f}%"] if eg is not None else ["EPS growth unknown"])
        legs.append(_leg(st, "Fundamentals", f"Fundamental score {fs}/3", ", ".join(parts) + ". " + (
            "The business is shrinking while the chart rises. SEPA wants both moving up together, so this blocks a BUY." if neg else
            "No meaningful growth behind the price move, so this blocks a BUY." if st == "fail" else
            "Revenue and earnings are both growing strongly - the confirmation SEPA looks for." if st == "pass" else
            "Some growth, though not the strong revenue and earnings growth SEPA prefers. It does not block a BUY, but check the latest results.")))

    # 3. Entry point - the BUY rule's own pivot and breakout tests
    n0 = max(0, i + 1 - 60)
    bw = _base_windows(f["h"].values[n0:i + 1], f["l"].values[n0:i + 1])
    tight = None
    if bw:
        w1, w2, w3 = bw
        tight = "full" if (w3 < w2 < w1) else ("some" if w3 < w1 else "none")
    if dist is None:
        legs.append(_leg("manual", "Entry Point", "No pivot yet", "Not enough price history to locate a pivot."))
    else:
        broke = 0 <= dist <= MAX_CHASE and vr is not None and vr >= BREAKOUT_VOL
        st = "pass" if broke else ("partial" if -ALERT_ZONE <= dist <= MAX_CHASE else "fail")
        body = (f"The pivot is the highest high of the prior {PIVOT_LOOKBACK} sessions ({pivot:.2f}); price is {dist * 100:+.1f}% against it" +
                (f" on {vr:.1f}x normal volume" if vr is not None else "") + ". " +
                ("That is a confirmed breakout: above the pivot, not more than 5% past it, and at least 1.5x volume. " if broke else
                 "Above the pivot but volume is under 1.5x, so the breakout is not confirmed. " if 0 <= dist <= MAX_CHASE else
                 "More than 5% past the pivot - extended, do not chase. " if dist > MAX_CHASE else
                 "Within 5% below the pivot: set an alert there and buy only on a high-volume break. " if dist >= -ALERT_ZONE else
                 "Too far below the pivot - the base is still forming. "))
        if bw:
            body += (f"Base pullbacks: {w1:.0f}% (60-25 sessions ago), {w2:.0f}% (25-10 ago), {w3:.0f}% (last 10) - " +
                     ("each shallower than the last, a clean contraction." if tight == "full" else
                      "tighter than at the start, though not in order." if tight == "some" else
                      "not tightening yet.") +
                     " Shown for context; in the backtest the tightening pattern alone did not predict better results.")
        legs.append(_leg(st, "Entry Point", f"Pivot {pivot:.2f} ({dist * 100:+.1f}%)", body))

    # 4. Exit and risk - the BUY rule's own stop, plus how stretched the stock is
    if ext is not None and ext > EXT_MA50_MAX:
        st = "partial"
    else:
        st = "pass" if risk <= MAX_STOP + 1e-9 else "fail"
    legs.append(_leg(st, "Exit and Risk", f"Stop {stop:.2f} ({risk * 100:.1f}% risk)",
                     f"The stop is {risk * 100:.1f}% below the {'price' if ent == px else 'entry at the pivot'} "
                     f"({'just under the 10-day low' if num(low10) and abs(stop - low10) < 1e-9 else 'the 8% maximum loss'}), "
                     f"so a 1% account risk allows a position of about {min(100 / max(risk * 100, 0.1), 100):.0f}% of capital. " +
                     (f"Price is {ext * 100:.0f}% above the 50-day - extended. Breakouts this stretched did worse in the backtest, so use half size."
                      if st == "partial" else
                      (f"Price is {ext * 100:.0f}% above the 50-day, not stretched. " if ext is not None else "") +
                      "Sell if the stop is hit, or on a close below the 50-day on heavy volume.")))

    # 5. Catalyst - only the calendar can be checked
    dte = row.get("daysToEvent")
    soon = dte is not None and 0 <= dte <= EVENT_DAYS
    legs.append(_leg("manual", "Catalyst", f"Results or event in {dte} days" if soon else "Not assessable from price data",
                     ("A scheduled event lands within " + str(EVENT_DAYS) + " days - gap risk that no stop can cover, so size is cut one step. " if soon else "") +
                     "A real catalyst (a contract, approval, new product or management change) has to be found in the company's announcements."))

    # Sizing checks (backtest-backed) and context indicators (shown, not scored)
    size_checks, context = [], []
    def chk(lst, ok, text, val):
        lst.append({"ok": bool(ok), "text": text, "val": val})
    rsh, adr = x.get("rs_line_hi", np.nan), x["ad_ratio"]
    lead = (num(adr) and adr >= ACC_MIN) or (num(rsh) and rsh >= RS_HIGH)
    chk(size_checks, ext is None or ext <= EXT_MA50_MAX, f"Not extended (within {EXT_MA50_MAX * 100:.0f}% of the 50-day)",
        f"{ext * 100:+.0f}% vs the 50-day" if ext is not None else "n/a")
    chk(size_checks, lead, "Institutional demand: accumulation or RS line at a new high",
        (f"up/down volume {adr:.2f}x" if num(adr) else "volume n/a") + (f", RS line {(rsh - 1) * 100:+.1f}% vs its high" if num(rsh) else ""))
    if num(x["dryup"]): chk(context, x["dryup"] < 1.0, "Volume dried up in the base", f"prior 10 sessions at {x['dryup'] * 100:.0f}% of normal")
    if num(x["macd_hist"]): chk(context, x["macd_hist"] > 0, "MACD momentum positive", f"histogram {x['macd_hist']:+.3f}")
    if num(x["adx"]): chk(context, x["adx"] >= 20 and x["pdi"] > x["mdi"], "ADX trend (20+, +DI above -DI)", f"ADX {x['adx']:.0f}, +DI {x['pdi']:.0f} / -DI {x['mdi']:.0f}")
    if num(x["ichi"]): chk(context, x["ichi"] >= 2, "Ichimoku bullish", f"score {int(x['ichi']):+d} of 4")
    if num(x["clv"]): chk(context, x["clv"] >= 0.5, "Closed in the upper half of the day's range", f"at {x['clv'] * 100:.0f}% of the range")
    if num(x["rsi"]): chk(context, x["rsi"] <= RSI_HOT, f"RSI not overbought (under {RSI_HOT})", f"RSI {x['rsi']:.0f}")
    try:
        bear = sorted({p["name"] for p in candle_patterns(df.iloc[:i + 1]) if p["kind"] == "bearish"})
        chk(context, not bear, "No bearish reversal candle in the last 3 sessions", ", ".join(bear) if bear else "none")
    except Exception:
        pass
    an = row.get("analyst") or {}
    if an.get("key"):
        chk(context, an.get("key") not in ("underperform", "sell"), "Analysts not negative",
            f"{an.get('n')} analysts, consensus {an.get('key').replace('_', ' ')}")
    return {"legs": legs, "sizeChecks": size_checks, "context": context,
            "eventSoon": bool(soon), "tight": tight, "ext50": _f(ext * 100, 1) if ext is not None else None}


def grade(q):
    """Verdict for a stock whose price has broken out.
    Returns (still_a_buy, size, reasons). Fundamentals that fail block the BUY;
    the sizing checks and a nearby results date only reduce the size."""
    st = {lg["title"]: lg["state"] for lg in q["legs"]}
    if st.get("Fundamentals") == "fail":
        return False, None, ["the fundamentals leg fails (no growth, or revenue/earnings falling) - SEPA needs the business growing behind the chart"]
    steps, why = 0, []
    missed = [c["text"].lower() for c in q["sizeChecks"] if not c["ok"]]
    if missed:
        steps += 1
        why.append("missing: " + "; ".join(missed))
    if q.get("eventSoon"):
        steps += 1
        why.append("results or an event are due within " + str(EVENT_DAYS) + " days")
    return True, ["full", "half", "quarter"][min(steps, 2)], why



def _check_value(name, f, has_bench=True):
    """This stock's actual numbers behind one trend-template check, in plain words."""
    try:
        last = f.iloc[-1]
        c, m50, m150, m200 = last["c"], last["ma50"], last["ma150"], last["ma200"]
        n = lambda v: f"{v:.2f}" if v == v else "n/a"
        if name == "Price above 150 and 200-day":
            return f"price {n(c)} vs 150-day {n(m150)}, 200-day {n(m200)}"
        if name == "150-day above 200-day":
            return f"{n(m150)} vs {n(m200)}"
        if name == "200-day rising for a month":
            return f"{n(m200)} now vs {n(last['ma200_1m'])} a month ago"
        if name == "50-day above 150 and 200-day":
            return f"50-day {n(m50)} vs {n(m150)} / {n(m200)}"
        if name == "Price above 50-day":
            return f"price {n(c)} vs 50-day {n(m50)}"
        if name == "At least 25% above 52-week low":
            lo = last["lo252"]
            return f"{(c / lo - 1) * 100:+.0f}% from the low of {n(lo)}" if lo == lo and lo else "n/a"
        if name == "Within 25% of 52-week high":
            hi = last["hi252"]
            return f"{(c / hi - 1) * 100:+.0f}% from the high of {n(hi)}" if hi == hi and hi else "n/a"
        if name == "Beating the index over 6 months":
            if not has_bench or len(f) < 127 or last["rs"] != last["rs"]:
                return "n/a (no index data)" if not has_bench else "n/a"
            own = c / f["c"].iloc[-127] - 1
            idx = own - last["rs"]
            return f"stock {own * 100:+.0f}% vs index {idx * 100:+.0f}%"
    except Exception:
        pass
    return ""


def _stop_for(entry, low10):
    stop = entry * (1 - MAX_STOP)
    if low10 == low10 and entry * (1 - MAX_STOP) < low10 < entry * 0.98:
        stop = low10                       # tighter stop under the recent swing low
    return stop


# ── Live decision ─────────────────────────────────────────────────────────────
def decide(df, bench, market, liquid=True, locked=False, row=None):
    if df is None or len(df) == 0:
        return None
    if len(df) < 60:
        px = float(df["Close"].iloc[-1])
        return {"action": "WATCH", "passed": 0, "total": 8, "checks": [],
                "reasons": [f"Listed only {len(df)} sessions ago - too new for the trend rules. Wait for its first proper base (several weeks of tight, orderly trading)."],
                "price": _f(px), "pivot": None, "distPivot": None, "volRatio": None,
                "entry": None, "stop": None, "riskPct": None, "t1": None, "t2": None, "ma50": None}
    f, tt = _frame(df, bench)
    last, prev = f.iloc[-1], f.iloc[-2]
    px, pivot = last["c"], last["pivot"]
    vr = last["v"] / last["vol50"] if last["vol50"] else 0
    checks = [{"ok": bool(tt[k].iloc[-1]), "text": k, "val": _check_value(k, f, bench is not None)} for k in tt.columns]
    passed = sum(x["ok"] for x in checks)
    enough_history = len(df) >= 200
    trend_ok = bool(last["tt_all"])
    checks.append({"ok": bool(liquid and not locked), "text": "Trades normally (not thin or locked)",
                   "val": "barely trading or locked" if locked else ("too thinly traded" if not liquid else "normal daily turnover")})
    checks.append({"ok": bool(market.get("allowBuys", True)), "text": "Market not in correction",
                   "val": market.get("label", "")})

    above_pivot = pivot == pivot and px > pivot
    dist = (px / pivot - 1) if pivot == pivot and pivot else None
    # the three breakout tests that turn a stock that passes the trend rules into a BUY today
    has_piv = pivot == pivot and bool(pivot)
    trigger = [
        {"ok": bool(above_pivot), "text": f"Closed above its {PIVOT_LOOKBACK}-day high (the pivot)",
         "val": f"close {px:.2f} vs pivot {pivot:.2f}" if has_piv else "no pivot yet"},
        {"ok": bool(dist is not None and dist <= MAX_CHASE), "text": f"Not more than {MAX_CHASE*100:.0f}% above the pivot (not chasing)",
         "val": f"{dist*100:+.1f}% from the pivot" if dist is not None else "-"},
        {"ok": bool(vr >= BREAKOUT_VOL), "text": f"Volume at least {BREAKOUT_VOL:g}x normal",
         "val": f"{vr:.1f}x the 50-day average" if vr == vr else "-"},
    ]
    reasons = []
    action = "WATCH"
    q, size, held_back = None, None, False

    # sell / avoid first
    broke_50 = prev["c"] >= prev["ma50"] and px < last["ma50"] and vr >= BREAKOUT_VOL
    stage4 = last["ma200"] == last["ma200"] and px < last["ma200"] and last["ma200"] < last["ma200_1m"]
    if locked:
        action, reasons = "AVOID", ["It is barely trading or locked at one price, so the signals cannot be acted on."]
    elif broke_50:
        action = "SELL"
        reasons = [f"Closed below the 50-day average on {vr:.1f}x normal volume - Minervini's main exit signal for a holding."]
    elif stage4:
        action = "AVOID"
        reasons = ["Below a falling 200-day average (Stage 4 decline) - SEPA never buys here."]
    elif not enough_history:
        action = "WATCH"
        reasons = [f"Only {len(df)} sessions of history - the 200-day rules cannot be tested yet. Judge it on its first orderly base."]
    elif trend_ok and liquid:
        if above_pivot and dist <= MAX_CHASE and vr >= BREAKOUT_VOL:
            action = "BUY"
            reasons = [f"Broke above its {PIVOT_LOOKBACK}-day high (pivot {pivot:.2f}) on {vr:.1f}x normal volume with every trend rule met."]
        elif above_pivot and dist <= MAX_CHASE:
            action = "ALERT"
            reasons = [f"Above the pivot ({pivot:.2f}) but volume is only {vr:.1f}x normal - a real breakout needs at least {BREAKOUT_VOL}x. Wait for a high-volume day."]
        elif above_pivot:
            action = "WAIT"
            reasons = [f"{dist*100:.0f}% above the pivot - extended. Buying here means a wide stop; wait for a pullback toward the 10/21-day averages or a new base."]
        elif dist is not None and dist >= -ALERT_ZONE:
            action = "ALERT"
            reasons = [f"All trend rules met and {abs(dist)*100:.1f}% below the pivot. Set a buy alert at {pivot:.2f} and act only if it breaks out on volume."]
        else:
            action = "WATCH"
            reasons = [f"Trend rules met but {abs(dist)*100:.0f}% below the pivot - still building a base."]
        # A price breakout must also pass the SEPA scorecard; the sizing checks set the position size
        q = quality(f, len(f) - 1, df, row)
        if action == "BUY":
            keep, size, why = grade(q)
            if not keep:
                action, held_back = "WAIT", True
                reasons = [f"Broke above the pivot ({pivot:.2f}) on {vr:.1f}x volume, but it is not a SEPA buy: " + "; ".join(why) + "."]
            elif size == "full":
                reasons.append("No SEPA leg fails, the stock is not extended, and accumulation or relative strength shows institutions buying.")
            else:
                reasons.append("Size cut because " + "; ".join(why) + ".")
        elif action == "ALERT":
            st = {lg["title"]: lg["state"] for lg in q["legs"]}
            if st.get("Fundamentals") == "fail":
                reasons.append("Even on a breakout this would not be a SEPA buy yet: the fundamentals leg fails.")
        if action in ("BUY", "ALERT") and not market.get("allowBuys", True):
            reasons.append("The broad market is in a correction - Minervini makes no new buys until it recovers, so treat this as watch-only.")
            action = "ALERT" if action == "BUY" else action
            size = None
        elif action == "BUY" and market.get("state") == "pressure":
            size = "half" if size == "full" else "quarter"
            reasons.append("The market uptrend is under pressure, so one more size step down.")
        if action == "BUY":
            reasons.append(f"Suggested position size: {size}.")
    elif trend_ok and not liquid:
        action = "WATCH"
        reasons = ["Trend rules are met but it trades too thinly to buy and sell safely."]
    else:
        action = "AVOID" if passed <= 4 else "WATCH"
        missing = [x["text"].lower() for x in checks[:8] if not x["ok"]]
        reasons = [("Fails " if action == "AVOID" else "Not yet: ") + "; ".join(missing[:4]) + "."]

    # prices
    entry = px if (action == "BUY" or held_back) else (pivot * 1.001 if pivot == pivot else px)
    stop = _stop_for(entry, last["low10"])
    if action == "SELL":
        entry, stop = None, None
    risk = (entry - stop) / entry if entry and stop else None
    out = {
        "action": action, "reasons": reasons, "checks": checks, "trigger": trigger,
        "passed": passed, "total": 8,
        "price": _f(px), "pivot": _f(pivot), "distPivot": _f(dist * 100, 1) if dist is not None else None,
        "volRatio": _f(vr, 2),
        "entry": _f(entry) if entry else None, "stop": _f(stop) if stop else None,
        "riskPct": _f(risk * 100, 1) if risk else None,
        "t1": _f(entry * (1 + TARGET_1)) if entry else None,
        "t2": _f(entry + 3 * (entry - stop)) if entry and stop else None,
        "ma50": _f(last["ma50"]),
        "size": size if action == "BUY" else None,
        "heldBack": held_back,
    }
    if enough_history and action != "SELL":
        try:   # (re)build the scorecard on the decision's own entry, so the legs and the box show the same stop
            q = quality(f, len(f) - 1, df, row, entry=entry)
        except Exception:
            q = None
    if q is not None:
        out["quality"] = q
    return out


# ── Backtest of the BUY rule ──────────────────────────────────────────────────
def _simulate(f, idx, start):
    """Follow each signal in idx: win = +TARGET_1 before the stop; loss = stop hit
    first; otherwise exit at the close after HORIZON sessions. One trade at a time."""
    trades, busy_until, n = [], -1, len(f)
    for i in idx:
        if i < start or i <= busy_until or i + 1 >= n:
            continue
        if i + HORIZON >= n:
            break                     # not enough future data yet
        entry = f["c"].iat[i]
        stop = _stop_for(entry, f["low10"].iat[i])
        tgt = entry * (1 + TARGET_1)
        result, days = None, HORIZON
        for k in range(i + 1, i + HORIZON + 1):
            lo, hi = f["l"].iat[k], f["h"].iat[k]
            if lo <= stop:
                result, days = (stop / entry - 1), k - i; break
            if hi >= tgt:
                result, days = TARGET_1, k - i; break
        if result is None:
            result = f["c"].iat[i + HORIZON] / entry - 1
        trades.append({"i": int(i), "ret": result, "days": days, "risk": 1 - stop / entry,
                       "outcome": "win" if result >= TARGET_1 - 1e-9 else ("stop" if result < 0 and days < HORIZON else "timeout")})
        busy_until = i + days
    return trades


def _stats(trades):
    if not trades:
        return {"n": 0}
    r = np.array([x["ret"] for x in trades])
    R = np.array([x["ret"] / x["risk"] if x["risk"] > 0 else 0 for x in trades])
    wins = sum(1 for x in trades if x["outcome"] == "win")
    stops = sum(1 for x in trades if x["outcome"] == "stop")
    pos = r[r > 0]
    neg = r[r <= 0]
    return {
        "n": len(trades), "winRate": _f(wins / len(trades) * 100, 0),
        "stopRate": _f(stops / len(trades) * 100, 0),
        "timeoutRate": _f((len(trades) - wins - stops) / len(trades) * 100, 0),
        "posRate": _f((r > 0).mean() * 100, 0),
        "avgRet": _f(r.mean() * 100, 1), "medRet": _f(np.median(r) * 100, 1),
        "avgWin": _f(pos.mean() * 100, 1) if len(pos) else None,
        "avgLoss": _f(neg.mean() * 100, 1) if len(neg) else None,
        "expR": _f(R.mean(), 2),
        "avgDays": _f(np.mean([x["days"] for x in trades]), 0),
        "horizon": HORIZON, "target": int(TARGET_1 * 100), "maxStop": int(MAX_STOP * 100),
    }


def backtest(hist_map, bench, min_adv=0.0, recent=252):
    """Apply the BUY rule to every stock on every day of the last `recent`
    sessions (with HORIZON sessions still to come) and follow each trade.
    The top-level numbers are all price breakouts; "full" and "half" split them
    by the sizing checks, so the dashboard shows whether the sizing still earns
    its keep in this market. Fundamentals and results dates have no history
    here, so they are not part of the test."""
    all_t, full_t, half_t = [], [], []
    for t, df in hist_map.items():
        try:
            if df is None or len(df) < 260:
                continue
            f, _ = _frame(df, bench)
            sig = (f["tt_all"] & (f["c"] > f["pivot"]) & (f["c"] <= f["pivot"] * (1 + MAX_CHASE))
                   & (f["v"] >= BREAKOUT_VOL * f["vol50"]) & ((f["c"] * f["v"]).rolling(20).mean() >= min_adv))
            n = len(f)
            start = max(200, n - recent - HORIZON)
            idx = [i for i in np.where(sig.values)[0] if i >= start]
            if not idx:
                continue
            trades = _simulate(f, idx, start)
            for tr in trades:
                i = tr.pop("i")
                full = all(c["ok"] for c in quality(f, i, df)["sizeChecks"])
                (full_t if full else half_t).append(tr)
                all_t.append(tr)
        except Exception:
            continue
    out = _stats(all_t)
    out["full"], out["half"] = _stats(full_t), _stats(half_t)
    if not all_t:
        out.update({"horizon": HORIZON, "target": int(TARGET_1 * 100), "maxStop": int(MAX_STOP * 100)})
    return out
