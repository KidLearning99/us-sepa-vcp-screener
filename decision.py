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
    return f, tt


def _stop_for(entry, low10):
    stop = entry * (1 - MAX_STOP)
    if low10 == low10 and entry * (1 - MAX_STOP) < low10 < entry * 0.98:
        stop = low10                       # tighter stop under the recent swing low
    return stop


# ── Live decision ─────────────────────────────────────────────────────────────
def decide(df, bench, market, liquid=True, locked=False):
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
    checks = [{"ok": bool(tt[k].iloc[-1]), "text": k} for k in tt.columns]
    passed = sum(x["ok"] for x in checks)
    enough_history = len(df) >= 200
    trend_ok = bool(last["tt_all"])
    checks.append({"ok": bool(liquid and not locked), "text": "Trades normally (not thin or locked)"})
    checks.append({"ok": bool(market.get("allowBuys", True)), "text": "Market not in correction"})

    above_pivot = pivot == pivot and px > pivot
    dist = (px / pivot - 1) if pivot == pivot and pivot else None
    reasons = []
    action = "WATCH"

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
        if action in ("BUY", "ALERT") and not market.get("allowBuys", True):
            reasons.append("The broad market is in a correction - Minervini makes no new buys until it recovers, so treat this as watch-only.")
            action = "ALERT" if action == "BUY" else action
        elif action == "BUY" and market.get("state") == "pressure":
            reasons.append("The market uptrend is under pressure - consider half size.")
    elif trend_ok and not liquid:
        action = "WATCH"
        reasons = ["Trend rules are met but it trades too thinly to buy and sell safely."]
    else:
        action = "AVOID" if passed <= 4 else "WATCH"
        missing = [x["text"].lower() for x in checks[:8] if not x["ok"]]
        reasons = [("Fails " if action == "AVOID" else "Not yet: ") + "; ".join(missing[:4]) + "."]

    # prices
    entry = px if action == "BUY" else (pivot * 1.001 if pivot == pivot else px)
    stop = _stop_for(entry, last["low10"])
    if action == "SELL":
        entry, stop = None, None
    risk = (entry - stop) / entry if entry and stop else None
    out = {
        "action": action, "reasons": reasons, "checks": checks,
        "passed": passed, "total": 8,
        "price": _f(px), "pivot": _f(pivot), "distPivot": _f(dist * 100, 1) if dist is not None else None,
        "volRatio": _f(vr, 2),
        "entry": _f(entry) if entry else None, "stop": _f(stop) if stop else None,
        "riskPct": _f(risk * 100, 1) if risk else None,
        "t1": _f(entry * (1 + TARGET_1)) if entry else None,
        "t2": _f(entry + 3 * (entry - stop)) if entry and stop else None,
        "ma50": _f(last["ma50"]),
    }
    return out


# ── Backtest of the BUY rule ──────────────────────────────────────────────────
def backtest(hist_map, bench, min_adv=0.0, recent=252):
    """Apply the BUY rule to every stock on every day of the last `recent`
    sessions (with HORIZON sessions still to come), then follow each trade:
    win = +TARGET_1 reached before the stop; loss = stop hit first; otherwise
    exit at the close after HORIZON sessions. One trade at a time per stock."""
    trades = []
    for t, df in hist_map.items():
        try:
            if df is None or len(df) < 260:
                continue
            f, _ = _frame(df, bench)
            sig = (f["tt_all"] & (f["c"] > f["pivot"]) & (f["c"] <= f["pivot"] * (1 + MAX_CHASE))
                   & (f["v"] >= BREAKOUT_VOL * f["vol50"]) & ((f["c"] * f["v"]).rolling(20).mean() >= min_adv))
            n = len(f)
            start = max(200, n - recent - HORIZON)
            i = start
            idx = np.where(sig.values)[0]
            busy_until = -1
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
                trades.append({"ret": result, "days": days, "risk": 1 - stop / entry,
                               "outcome": "win" if result >= TARGET_1 - 1e-9 else ("stop" if result < 0 and days < HORIZON else "timeout")})
                busy_until = i + days
        except Exception:
            continue
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
