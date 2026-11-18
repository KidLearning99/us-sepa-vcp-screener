import yfinance as yf
import decision
import json, os, time, requests, random
from datetime import date, datetime
from zoneinfo import ZoneInfo

MELBOURNE = ZoneInfo("Australia/Melbourne")
NEW_YORK  = ZoneInfo("America/New_York")

def today_ny():
    """US trading date. Event countdowns (earnings, ex-div) are measured from
    the New York date, not the runner's UTC clock or Melbourne."""
    return datetime.now(NEW_YORK).date()
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

MIN_MARKET_CAP  = int(os.environ.get("MIN_MARKET_CAP", 5_000_000_000))  # US$5B+
SEPA_MIN        = 3
MIN_ADV         = 1_000_000   # thin-trading threshold (avg daily traded value)
VOL_BREAKOUT    = 1.5
VCP_MIN         = 2
FALLBACK_FILE   = "data/us_universe.txt"

# Nasdaq screener metadata per ticker, used when Yahoo's t.info is throttled.
# Sector names are mapped to Yahoo's so the sector filter stays consistent.
NASDAQ_META = {}
NASDAQ_SECTOR_TO_YAHOO = {
    "Finance": "Financial Services", "Health Care": "Healthcare",
    "Consumer Discretionary": "Consumer Cyclical", "Consumer Staples": "Consumer Defensive",
    "Telecommunications": "Communication Services", "Technology": "Technology",
    "Industrials": "Industrials", "Real Estate": "Real Estate", "Energy": "Energy",
    "Utilities": "Utilities", "Basic Materials": "Basic Materials",
}

def get_all_us_tickers():
    """
    Ticker universe: every US-listed common stock (NYSE, NASDAQ, NYSE American)
    above MIN_MARKET_CAP.

    Primary source: Nasdaq's stock screener API (covers all three exchanges,
    includes market cap). Preferreds, warrants, units and rights are dropped.
    Class shares are converted to Yahoo format (BRK/B -> BRK-B).

    Fallback: data/us_universe.txt, a committed snapshot of the universe.

    Never returns [] silently: an empty universe raises so the run fails
    loudly instead of publishing an empty dashboard.
    """
    def _from_nasdaq():
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true"
        resp = requests.get(url, timeout=60, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })
        resp.raise_for_status()
        rows = (resp.json().get("data") or {}).get("rows") or []
        if not rows:
            raise ValueError("Nasdaq screener returned no rows (blocked or changed)")
        tickers = []
        for r in rows:
            sym  = (r.get("symbol") or "").strip().upper()
            name = (r.get("name") or "").lower()
            try:
                cap = float(r.get("marketCap") or 0)
            except ValueError:
                cap = 0
            if not sym or cap < MIN_MARKET_CAP:
                continue
            if "^" in sym:                       # preferred shares
                continue
            if any(w in name for w in (" warrant", " unit", " right", "preferred",
                                        "depositary shares representing")):
                continue
            yf_sym = sym.replace("/", "-").replace(".", "-")
            tickers.append(yf_sym)
            NASDAQ_META[yf_sym] = {
                "name": (r.get("name") or "").replace(" Common Stock", "").replace(" Class A", "").strip(),
                "sector": NASDAQ_SECTOR_TO_YAHOO.get(r.get("sector") or "", ""),
                "mktcap": cap,
            }
        print(f"Market cap pre-filter: {len(tickers)}/{len(rows)} above "
              f"${MIN_MARKET_CAP/1e9:g}B")
        return sorted(set(tickers))

    def _from_snapshot():
        with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
            return sorted({l.strip().upper() for l in f if l.strip() and not l.startswith("#")})

    for label, fn in (("Nasdaq screener", _from_nasdaq),
                      ("committed snapshot", _from_snapshot)):
        try:
            tickers = fn()
            if tickers:
                print(f"Loaded {len(tickers)} US tickers from {label}")
                return tickers
            print(f"{label} returned 0 tickers")
        except Exception as e:
            print(f"Ticker source '{label}' failed: {type(e).__name__}: {e}")

    raise RuntimeError(
        "No US tickers from any source - aborting rather than publishing "
        "an empty dashboard."
    )

US_TICKERS = get_all_us_tickers() if __name__ == "__main__" else []

def fmt_cap(c):
    if c >= 1e12: return f"${c/1e12:.1f}T"
    if c >= 1e9:  return f"${c/1e9:.1f}B"
    if c >= 1e6:  return f"${c/1e6:.0f}M"
    return f"${c:.0f}"

def fmt_pct(v):
    return ('+' if v >= 0 else '') + str(round(v, 2)) + '%'

def _parse_date(raw):
    if raw is None: return None
    if hasattr(raw, 'date'): return raw.date()
    if isinstance(raw, str):
        try: return datetime.strptime(raw[:10], '%Y-%m-%d').date()
        except: return None
    return None

# ── Batch download price history for a chunk of tickers ──────────────────────
def download_chunk(tickers, period="2y"):   # 2y: 1y for scoring + 1y for the backtest
    """Download OHLCV for a batch of tickers in one request. Returns dict ticker->df."""
    try:
        raw = yf.download(
            tickers, period=period, interval="1d",
            group_by="ticker", auto_adjust=True,
            progress=False, threads=True
        )
    except Exception as e:
        print(f"  batch download error: {e}")
        return {}

    result = {}
    if len(tickers) == 1:
        t = tickers[0]
        if not raw.empty and isinstance(raw.columns, pd.MultiIndex):
            raw = raw[t] if t in raw.columns.get_level_values(0) else raw.droplevel(0, axis=1)
        raw = raw.dropna(subset=['Close']) if not raw.empty else raw
        if not raw.empty:
            result[t] = raw
        return result

    for t in tickers:
        try:
            # Drop rows with no close price (Yahoo sometimes returns a bar with
            # volume but NaN OHLC). One NaN bar breaks the dashboard's JS.
            df = raw[t].dropna(how='all').dropna(subset=['Close'])
            if not df.empty and len(df) >= 30:
                result[t] = df
        except Exception:
            pass
    return result

# ── Technical indicators from the full price history ─────────────────────────
SPY_CLOSE = None   # S&P 500 (SPY) closes, set in fetch_all for relative strength

def technicals(hist):
    """RSI, MACD, Stochastic, ATR, Bollinger, ADX and RS vs SPY. Each value is
    None when there is not enough history, so the dashboard shows n/a."""
    out = {}
    def _r(v, d=2):
        try:
            v = float(v)
            return round(v, d) if v == v and abs(v) != float("inf") else None
        except Exception:
            return None
    try:
        c = hist["Close"].astype(float)
        h = hist["High"].astype(float) if "High" in hist else c
        l = hist["Low"].astype(float) if "Low" in hist else c

        # RSI(14), Wilder smoothing
        if len(c) > 15:
            d = c.diff()
            gain = d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss.replace(0, float("nan"))
            rsi = 100 - 100 / (1 + rs)
            out["rsi"] = _r(rsi.iloc[-1], 1)

        # MACD(12,26,9)
        if len(c) > 35:
            macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
            sig = macd.ewm(span=9, adjust=False).mean()
            hst = macd - sig
            out["macd"] = _r(macd.iloc[-1], 3)
            out["macdSignal"] = _r(sig.iloc[-1], 3)
            out["macdHist"] = _r(hst.iloc[-1], 3)
            out["macdHistPrev"] = _r(hst.iloc[-2], 3)
            cross = None
            for k in range(1, 6):   # crossover within the last 5 sessions
                if hst.iloc[-k] > 0 >= hst.iloc[-k - 1]: cross = f"bull {k - 1}d ago"; break
                if hst.iloc[-k] < 0 <= hst.iloc[-k - 1]: cross = f"bear {k - 1}d ago"; break
            out["macdCross"] = cross

        # Stochastic %K(14) / %D(3)
        if len(c) > 17:
            ll, hh = l.rolling(14).min(), h.rolling(14).max()
            k = 100 * (c - ll) / (hh - ll).replace(0, float("nan"))
            out["stochK"] = _r(k.iloc[-1], 1)
            out["stochD"] = _r(k.rolling(3).mean().iloc[-1], 1)

        # ATR(14) and ATR as % of price
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        if len(c) > 15:
            atr = tr.ewm(alpha=1/14, adjust=False).mean()
            out["atr"] = _r(atr.iloc[-1], 2)
            out["atrPct"] = _r(atr.iloc[-1] / c.iloc[-1] * 100, 2)

        # Bollinger(20,2): %B, bandwidth, and bandwidth percentile over 120 sessions
        if len(c) > 20:
            m = c.rolling(20).mean(); sd = c.rolling(20).std()
            up, lo = m + 2 * sd, m - 2 * sd
            bw = (up - lo) / m * 100
            out["bbPctB"] = _r((c.iloc[-1] - lo.iloc[-1]) / (up.iloc[-1] - lo.iloc[-1]) * 100, 0)
            out["bbWidth"] = _r(bw.iloc[-1], 1)
            win = bw.dropna().tail(120)
            if len(win) >= 40:
                out["bbWidthPctile"] = _r((win < win.iloc[-1]).mean() * 100, 0)

        # ADX(14) with +DI / -DI
        if len(c) > 30:
            upm, dnm = h.diff(), -l.diff()
            pdm = upm.where((upm > dnm) & (upm > 0), 0.0)
            ndm = dnm.where((dnm > upm) & (dnm > 0), 0.0)
            atr_w = tr.ewm(alpha=1/14, adjust=False).mean()
            pdi = 100 * pdm.ewm(alpha=1/14, adjust=False).mean() / atr_w
            ndi = 100 * ndm.ewm(alpha=1/14, adjust=False).mean() / atr_w
            dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, float("nan"))
            out["adx"] = _r(dx.ewm(alpha=1/14, adjust=False).mean().iloc[-1], 1)
            out["plusDI"] = _r(pdi.iloc[-1], 1)
            out["minusDI"] = _r(ndi.iloc[-1], 1)

        # Second set: moving-average stack, oscillators, money flow, trend tools
        px = c.iloc[-1]
        mas = {}
        for key, ser in (("ema10", c.ewm(span=10, adjust=False).mean()),
                         ("ema21", c.ewm(span=21, adjust=False).mean()),
                         ("sma20", c.rolling(20).mean()),
                         ("sma50", c.rolling(50).mean()),
                         ("sma100", c.rolling(100).mean()),
                         ("sma200", c.rolling(200).mean())):
            v = ser.iloc[-1]
            if v == v:
                mas[key] = {"v": _r(v, 2), "d": _r((px / v - 1) * 100, 1),
                            "slope": _r((v / ser.iloc[-6] - 1) * 100, 2) if len(ser) > 6 and ser.iloc[-6] == ser.iloc[-6] else None}
        out["mas"] = mas

        if len(c) > 20:   # Williams %R(14), CCI(20), ROC(10/20)
            ll, hh = l.rolling(14).min(), h.rolling(14).max()
            out["willR"] = _r(-100 * (hh.iloc[-1] - px) / (hh.iloc[-1] - ll.iloc[-1]), 1) if hh.iloc[-1] > ll.iloc[-1] else None
            tp = (h + l + c) / 3
            md = tp.rolling(20).apply(lambda x: abs(x - x.mean()).mean(), raw=True)
            out["cci"] = _r((tp.iloc[-1] - tp.rolling(20).mean().iloc[-1]) / (0.015 * md.iloc[-1]), 0) if md.iloc[-1] else None
            out["roc10"] = _r((px / c.iloc[-11] - 1) * 100, 1)
            out["roc20"] = _r((px / c.iloc[-21] - 1) * 100, 1)

        if "Volume" in hist and len(c) > 20:   # MFI(14) and OBV trend
            v = hist["Volume"].astype(float)
            tp = (h + l + c) / 3
            rmf = tp * v
            pos = rmf.where(tp > tp.shift(), 0.0).rolling(14).sum()
            neg = rmf.where(tp < tp.shift(), 0.0).rolling(14).sum()
            out["mfi"] = _r(100 - 100 / (1 + pos.iloc[-1] / neg.iloc[-1]), 1) if neg.iloc[-1] else _r(100.0, 1)
            obv = (v * c.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))).cumsum()
            out["obvTrend"] = _r((obv.iloc[-1] - obv.iloc[-21]) / v.tail(20).mean(), 1) if v.tail(20).mean() else None

        if len(c) > 30:   # Parabolic SAR (0.02 / 0.2)
            af, mx = 0.02, 0.2
            bull = True; sar = l.iloc[0]; ep = h.iloc[0]; a = af; flip = 0
            for i in range(1, len(c)):
                sar = sar + a * (ep - sar)
                if bull:
                    sar = min(sar, l.iloc[i - 1], l.iloc[i - 2] if i > 1 else l.iloc[i - 1])
                    if l.iloc[i] < sar:
                        bull, sar, ep, a, flip = False, ep, l.iloc[i], af, i
                    elif h.iloc[i] > ep:
                        ep, a = h.iloc[i], min(a + af, mx)
                else:
                    sar = max(sar, h.iloc[i - 1], h.iloc[i - 2] if i > 1 else h.iloc[i - 1])
                    if h.iloc[i] > sar:
                        bull, sar, ep, a, flip = True, ep, h.iloc[i], af, i
                    elif l.iloc[i] < ep:
                        ep, a = l.iloc[i], min(a + af, mx)
            out["sar"] = _r(sar, 2); out["sarBull"] = bool(bull)
            out["sarAge"] = int(len(c) - 1 - flip)

        if len(c) > 52:   # Ichimoku: price vs cloud (cloud plotted 26 ahead, so use spans from 26 ago)
            tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
            kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
            spa = ((tenkan + kijun) / 2).shift(26)
            spb = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
            top, bot = max(spa.iloc[-1], spb.iloc[-1]), min(spa.iloc[-1], spb.iloc[-1])
            if top == top and bot == bot:
                out["ichi"] = "above" if px > top else ("below" if px < bot else "inside")
                out["tkCross"] = "bull" if tenkan.iloc[-1] > kijun.iloc[-1] else "bear"

        # ── Series for the indicator charts (last 60 sessions, same window as candles)
        N = 60
        def _ser(x, d=2): return [_r(v, d) for v in x.tail(N).tolist()]
        if len(c) > 15:
            out["rsiS"] = _ser(rsi, 1)
        if len(c) > 35:
            out["macdS"] = _ser(macd, 3); out["sigS"] = _ser(sig, 3); out["histS"] = _ser(hst, 3)
        if SPY_CLOSE is not None:
            rl = (c / SPY_CLOSE.reindex(c.index).ffill()).dropna()
            if len(rl) >= N:
                base = rl.iloc[-N]
                out["rsS"] = [_r(v / base * 100, 2) for v in rl.tail(N).tolist()]

        # ── Support / resistance
        if len(c) > 30:
            # Classic floor pivots from the last completed session
            H, L, C = h.iloc[-1], l.iloc[-1], c.iloc[-1]
            P = (H + L + C) / 3
            out["pivots"] = {"P": _r(P), "R1": _r(2 * P - L), "R2": _r(P + (H - L)), "R3": _r(H + 2 * (P - L)),
                             "S1": _r(2 * P - H), "S2": _r(P - (H - L)), "S3": _r(L - 2 * (H - P))}
            # Fibonacci retracement of the 60-session swing
            win_h, win_l = h.tail(60), l.tail(60)
            sh, sl = win_h.max(), win_l.min()
            up = win_h.idxmax() > win_l.idxmin()   # swing up: retrace from the high down
            fib = {}
            for f in (0.236, 0.382, 0.5, 0.618, 0.786):
                fib[str(f)] = _r(sh - (sh - sl) * f) if up else _r(sl + (sh - sl) * f)
            out["fib"] = {"hi": _r(sh), "lo": _r(sl), "up": bool(up), "lv": fib}
            # Swing levels: 5-bar fractal highs/lows over the last 120 sessions
            hh_, ll_ = h.tail(120).tolist(), l.tail(120).tolist()
            highs = [hh_[i] for i in range(2, len(hh_) - 2) if hh_[i] == max(hh_[i - 2:i + 3])]
            lows  = [ll_[i] for i in range(2, len(ll_) - 2) if ll_[i] == min(ll_[i - 2:i + 3])]
            def _cluster(vals):
                vals = sorted(vals); outv = []
                for v in vals:
                    if outv and abs(v / outv[-1][0] - 1) < 0.015:
                        outv[-1] = ((outv[-1][0] * outv[-1][1] + v) / (outv[-1][1] + 1), outv[-1][1] + 1)
                    else:
                        outv.append((v, 1))
                return outv
            lv = _cluster(highs + lows)
            res = sorted([x for x in lv if x[0] > px], key=lambda x: x[0])[:3]
            sup = sorted([x for x in lv if x[0] < px], key=lambda x: -x[0])[:3]
            out["res"] = [{"v": _r(v), "n": n} for v, n in res]
            out["sup"] = [{"v": _r(v), "n": n} for v, n in sup]

        # ── Extra indicators (filler cards on the dashboard)
        if len(c) > 60 and "Volume" in hist:
            v = hist["Volume"].astype(float)
            ex = {}
            # Aroon (25)
            n = 25
            hh_i = h.tail(n + 1).values.argmax(); ll_i = l.tail(n + 1).values.argmin()
            ex["aroonUp"] = _r((hh_i) / n * 100, 0); ex["aroonDn"] = _r((ll_i) / n * 100, 0)
            # Ultimate Oscillator (7,14,28)
            bp = c - pd.concat([l, c.shift()], axis=1).min(axis=1)
            trr = pd.concat([h, c.shift()], axis=1).max(axis=1) - pd.concat([l, c.shift()], axis=1).min(axis=1)
            a7, a14, a28 = (bp.rolling(k).sum() / trr.rolling(k).sum() for k in (7, 14, 28))
            ex["uo"] = _r(100 * (4 * a7.iloc[-1] + 2 * a14.iloc[-1] + a28.iloc[-1]) / 7, 1)
            # Chande Momentum Oscillator (14)
            dd = c.diff().tail(14); su, sd = dd.clip(lower=0).sum(), -dd.clip(upper=0).sum()
            ex["cmo"] = _r(100 * (su - sd) / (su + sd), 0) if (su + sd) else None
            # Vortex (14)
            vmp = (h - l.shift()).abs().rolling(14).sum(); vmm = (l - h.shift()).abs().rolling(14).sum()
            trs = trr.rolling(14).sum()
            ex["viPlus"] = _r(vmp.iloc[-1] / trs.iloc[-1], 2); ex["viMinus"] = _r(vmm.iloc[-1] / trs.iloc[-1], 2)
            # Elder Ray (13)
            e13 = c.ewm(span=13, adjust=False).mean()
            ex["bullPow"] = _r(h.iloc[-1] - e13.iloc[-1], 2); ex["bearPow"] = _r(l.iloc[-1] - e13.iloc[-1], 2)
            # Force Index (13), scaled by average dollar volume
            fi = (c.diff() * v).ewm(span=13, adjust=False).mean()
            dv = (c * v).tail(50).mean()
            ex["force"] = _r(fi.iloc[-1] / dv * 100, 2) if dv else None
            # Awesome Oscillator
            mid = (h + l) / 2
            ao = mid.rolling(5).mean() - mid.rolling(34).mean()
            ex["ao"] = _r(ao.iloc[-1] / c.iloc[-1] * 100, 2); ex["aoUp"] = bool(ao.iloc[-1] > ao.iloc[-2])
            # Chaikin Money Flow (20) and Chaikin Oscillator (3,10)
            mfm = ((c - l) - (h - c)) / (h - l).replace(0, float("nan"))
            mfv = (mfm * v).fillna(0)
            ex["cmf"] = _r(mfv.tail(20).sum() / v.tail(20).sum(), 3) if v.tail(20).sum() else None
            adl = mfv.cumsum()
            cho = adl.ewm(span=3, adjust=False).mean() - adl.ewm(span=10, adjust=False).mean()
            ex["chaikinOsc"] = _r(cho.iloc[-1] / v.tail(20).mean(), 2) if v.tail(20).mean() else None
            # TRIX (15)
            e3 = c.ewm(span=15, adjust=False).mean().ewm(span=15, adjust=False).mean().ewm(span=15, adjust=False).mean()
            trix = e3.pct_change() * 100
            ex["trix"] = _r(trix.iloc[-1], 3); ex["trixSig"] = _r(trix.ewm(span=9, adjust=False).mean().iloc[-1], 3)
            # Linear regression trend over 50 sessions (log price): annualised slope and R squared
            import numpy as _np
            y = _np.log(c.tail(50).values); x = _np.arange(len(y))
            sl_, ic_ = _np.polyfit(x, y, 1); pred = sl_ * x + ic_
            ss = ((y - y.mean()) ** 2).sum()
            ex["lrSlope"] = _r((_np.exp(sl_ * 252) - 1) * 100, 0)
            ex["lrR2"] = _r(1 - ((y - pred) ** 2).sum() / ss, 2) if ss else None
            # Rolling VWAP (20 and 50 sessions)
            tp_ = (h + l + c) / 3
            for k in (20, 50):
                vw = (tp_ * v).tail(k).sum() / v.tail(k).sum() if v.tail(k).sum() else None
                ex[f"vwap{k}"] = _r(vw, 2) if vw else None
            out["ex"] = ex

        # ── Volatility and risk statistics
        ret = c.pct_change().dropna()
        if len(ret) > 60:
            import math as _m
            out["hv20"] = _r(ret.tail(20).std() * _m.sqrt(252) * 100, 1)
            out["hv60"] = _r(ret.tail(60).std() * _m.sqrt(252) * 100, 1)
            out["hv250"] = _r(ret.std() * _m.sqrt(252) * 100, 1)
            peak = c.cummax(); ddser = c / peak - 1
            out["maxDD"] = _r(ddser.min() * 100, 1)
            out["curDD"] = _r(ddser.iloc[-1] * 100, 1)
            out["adr20"] = _r(((h - l) / c).tail(20).mean() * 100, 2)
            r60 = ret.tail(60)
            out["upDays60"] = _r((r60 > 0).mean() * 100, 0)
            out["bestDay60"] = _r(r60.max() * 100, 1); out["worstDay60"] = _r(r60.min() * 100, 1)
            streak = 0
            for v in reversed(ret.tolist()):
                if v > 0 and streak >= 0: streak += 1
                elif v < 0 and streak <= 0: streak -= 1
                else: break
            out["streak"] = streak
            if "Open" in hist:
                o_ = hist["Open"].astype(float)
                gaps = (o_ / c.shift() - 1).tail(60).dropna()
                out["gapUps"] = int((gaps > 0.02).sum()); out["gapDowns"] = int((gaps < -0.02).sum())
            if SPY_CLOSE is not None:
                sret = SPY_CLOSE.reindex(c.index).ffill().pct_change()
                j = pd.concat([ret, sret], axis=1).dropna()
                if len(j) > 60 and j.iloc[:, 1].var() > 0:
                    out["beta"] = _r(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var(), 2)
                    out["corr"] = _r(j.iloc[:, 0].corr(j.iloc[:, 1]), 2)
                    _b1 = SPY_CLOSE.tail(252)
                    spy_dd = (_b1 / _b1.cummax() - 1).min()
                    out["spyMaxDD"] = _r(spy_dd * 100, 1)

        if len(c) > 21:   # Keltner(20, 2xATR10) and Donchian(20)
            em = c.ewm(span=20, adjust=False).mean().iloc[-1]
            at10 = tr.ewm(alpha=1/10, adjust=False).mean().iloc[-1]
            out["keltPos"] = _r((px - (em - 2 * at10)) / (4 * at10) * 100, 0) if at10 else None
            dh, dl = h.iloc[-21:-1].max(), l.iloc[-21:-1].min()
            out["donHi"] = _r(dh, 2); out["donLo"] = _r(dl, 2)
            out["donBreak"] = "up" if px > dh else ("down" if px < dl else None)

        # Relative strength vs S&P 500 (SPY): stock return minus SPY return
        if SPY_CLOSE is not None:
            spy = SPY_CLOSE.reindex(c.index).ffill()
            for n, key in ((63, "rs3m"), (126, "rs6m"), (len(c) - 1, "rs12m")):
                if len(c) > n and n > 0 and spy.iloc[-1 - n] == spy.iloc[-1 - n]:
                    sr = c.iloc[-1] / c.iloc[-1 - n] - 1
                    br = spy.iloc[-1] / spy.iloc[-1 - n] - 1
                    out[key] = _r((sr - br) * 100, 1)
            ratio = (c / spy).dropna()
            if len(ratio) >= 50:
                out["rsLineHigh"] = bool(ratio.iloc[-1] >= ratio.tail(250).max() * 0.995)
    except Exception as e:
        out["error"] = str(e)[:80]
    return out

# ── Score one ticker from its price dataframe ─────────────────────────────────
def score_stock(ticker, hist):
    try:
        closes  = hist['Close']
        volumes = hist['Volume']

        price  = float(closes.iloc[-1])
        volume = float(volumes.iloc[-1])
        if price <= 0: return None

        ma50   = round(float(closes.tail(50).mean()), 3)
        ma150  = round(float(closes.tail(150).mean()), 3) if len(closes) >= 150 else round(float(closes.mean()), 3)
        ma200  = round(float(closes.tail(200).mean()), 3) if len(closes) >= 200 else round(float(closes.mean()), 3)
        ma200p = round(float(closes.tail(220).head(200).mean()), 3) if len(closes) >= 220 else ma200

        hi52   = float(closes.max())
        lo52   = float(closes.min())
        pct_hi = round(max(0, (hi52 - price) / hi52 * 100), 1) if hi52 > 0 else 0
        pct_lo = round((price - lo52) / lo52 * 100, 1) if lo52 > 0 else 0

        def perf(n):
            if len(closes) > n:
                old = float(closes.iloc[-n])
                return round((price - old) / old * 100, 2) if old > 0 else 0
            return 0

        chg1d   = round((price - float(closes.iloc[-2])) / float(closes.iloc[-2]) * 100, 2) if len(closes) >= 2 else 0
        chg5d   = perf(5)
        chg10d  = perf(10)
        chg20d  = perf(20)
        chg60d  = perf(60)
        chg250d = perf(min(250, len(closes) - 1))

        avg50v = float(volumes.tail(50).mean())
        volr   = round(volume / avg50v, 2) if avg50v > 0 else 1.0

        c_ma50  = price > ma50
        c_ma150 = ma50 > ma150
        c_ma200 = ma150 > ma200
        c_trend = ma200 > ma200p
        c_high  = pct_hi <= 25
        c_low   = pct_lo >= 25
        c_vol   = volr >= VOL_BREAKOUT

        sepa = sum([c_ma50, c_ma150, c_ma200, c_trend, c_high, c_low, c_vol])
        # Recent listings (under 200 sessions) cannot pass the MA150/MA200 checks
        # yet, so they are always kept and tagged instead of being dropped.
        ipo = len(closes) < 200
        if sepa < SEPA_MIN and not ipo: return None

        vcp = min(sum([
            abs(chg5d)  < abs(chg10d),
            abs(chg10d) < abs(chg20d),
            abs(chg20d) < abs(chg60d),
            volr < 0.8
        ]), 4)

        ve  = volr - 1.0
        pvr = min(round(abs(chg1d) / ve, 2) if ve > 0.1 else round(abs(chg1d) * 2, 2), 9.99)

        if sepa >= 5 and c_vol and vcp >= VCP_MIN: status = "breakout"
        elif sepa >= 4 and vcp >= VCP_MIN and pct_hi <= 15: status = "near-pivot"
        else: status = "watch"

        try:
            rev_quarters = []
            _tkr = yf.Ticker(ticker)
            REV_KEYS = ['Total Revenue', 'TotalRevenue', 'Revenue', 'Operating Revenue', 'Revenues']
            for _attr in ['quarterly_income_stmt', 'quarterly_financials', 'income_stmt', 'financials']:
                _df = getattr(_tkr, _attr, None)
                try:
                    if _df is None or _df.empty:
                        continue
                except Exception:
                    continue
                for key in REV_KEYS:
                    if key in _df.index:
                        row = _df.loc[key].dropna().sort_index()
                        for dt, val in row.items():
                            try:
                                ts = pd.Timestamp(dt)
                                label = f"Q{(ts.month-1)//3+1} {str(ts.year)[2:]}" if _attr.startswith("quarterly") else f"FY{str(ts.year)[2:]}"
                                rev_quarters.append([label, float(val)])
                            except Exception:
                                pass
                        if rev_quarters:
                            rev_quarters = rev_quarters[-8:]
                            break
                if rev_quarters:
                    break
        except Exception:
            rev_quarters = []

        # ── 60-day OHLCV for candlestick chart ──────────────────────────────────
        try:
            ohlcv = []
            tail60 = hist.tail(60)
            op_col = tail60.get('Open',  tail60['Close'])
            hi_col = tail60.get('High',  tail60['Close'])
            lo_col = tail60.get('Low',   tail60['Close'])
            cl_col = tail60['Close']
            vo_col = tail60['Volume']
            for j in range(len(tail60)):
                ohlcv.append([
                    round(float(op_col.iloc[j]), 3),
                    round(float(hi_col.iloc[j]), 3),
                    round(float(lo_col.iloc[j]), 3),
                    round(float(cl_col.iloc[j]), 3),
                    int(float(vo_col.iloc[j]))
                ])
        except Exception:
            ohlcv = []

        # ── Minervini Stage Detection (1-4) ──────────────────────────────────────
        try:
            # Up-day vs down-day volume accumulation last 60 days
            up_vol = down_vol = 0.0
            for j in range(1, min(61, len(closes))):
                chg_j = float(closes.iloc[-j]) - float(closes.iloc[-j - 1])
                v_j   = float(volumes.iloc[-j])
                if chg_j > 0: up_vol  += v_j
                else:         down_vol += v_j
            vol_accumulating = up_vol > down_vol
            acc_dist_ratio = round(up_vol / down_vol, 2) if down_vol > 0 else 99.0

            # Volatility expansion: recent 20d std vs earlier 40d std
            ret_s = closes.pct_change().dropna()
            v20  = float(ret_s.tail(20).std()) if len(ret_s) >= 20 else 0
            v40  = float(ret_s.tail(60).head(40).std()) if len(ret_s) >= 60 else v20
            vol_expanding = (v20 > v40 * 1.2) if v40 > 0 else False

            # Lower-highs + lower-lows pattern (Stage 4 signal)
            if len(closes) >= 60:
                rh = float(closes.tail(20).max())
                eh = float(closes.tail(60).head(40).max())
                rl = float(closes.tail(20).min())
                el2 = float(closes.tail(60).head(40).min())
                stage4_pattern = rh < eh * 0.97 and rl < el2 * 0.97
            else:
                stage4_pattern = False

            pa200     = price > ma200
            ma15_a200 = ma150 > ma200
            ma200_up  = ma200 > ma200p

            # Priority: Stage 2 -> Stage 4 -> Stage 3 -> Stage 1
            if pa200 and ma15_a200 and ma200_up and vol_accumulating:
                stage = 2   # Advancing — only buy stage
            elif not ma200_up and not pa200 and stage4_pattern:
                stage = 4   # Declining — avoid
            elif vol_expanding or (pa200 and not ma200_up) or (not pa200 and not stage4_pattern and not ma15_a200):
                stage = 3   # Topping / distribution
            else:
                stage = 1   # Neglect / consolidation
        except Exception:
            stage = 1
            acc_dist_ratio = 1.0

        # ── Candlestick Formations (SEPA/VCP suitable) ───────────────────
        try:
            candle_signals = []
            if len(closes) >= 15:
                c_op = float(hist.get('Open', closes).iloc[-1])
                c_hi = float(hist.get('High', closes).iloc[-1])
                c_lo = float(hist.get('Low', closes).iloc[-1])
                c_cl = float(closes.iloc[-1])
                c_vo = float(volumes.iloc[-1])
                
                p_op = float(hist.get('Open', closes).iloc[-2])
                p_hi = float(hist.get('High', closes).iloc[-2])
                p_lo = float(hist.get('Low', closes).iloc[-2])
                p_cl = float(closes.iloc[-2])
                p_vo = float(volumes.iloc[-2])
                
                avg_vol_10 = float(volumes.tail(10).mean())
                
                # 1. Pocket Pivot (Up volume > highest down volume of past 10 days)
                if c_cl > c_op and c_cl > p_cl:
                    max_down_vol_10 = 0
                    for k in range(2, 12):
                        if float(closes.iloc[-k]) < float(closes.iloc[-k-1]):
                            dv = float(volumes.iloc[-k])
                            if dv > max_down_vol_10: max_down_vol_10 = dv
                    if max_down_vol_10 > 0 and c_vo > max_down_vol_10 and c_vo > avg_vol_10:
                        candle_signals.append("Pocket Pivot (Accumulation)")

                # 2. Inside Day & Dry Up
                if c_hi < p_hi and c_lo > p_lo and c_vo < avg_vol_10 * 0.6:
                    candle_signals.append("Inside Day & Vol Dry-up")

                # 3. Squat (High vol, tight spread)
                avg_spread = float((hist.get('High', closes) - hist.get('Low', closes)).tail(15).mean())
                spread = c_hi - c_lo
                if c_vo > avg_vol_10 * 1.5 and spread < avg_spread * 0.8:
                    if c_cl >= c_op: candle_signals.append("Support Squat (Hidden Accumulation)")
                    else:            candle_signals.append("Resistance Squat (Hidden Distribution)")

                # 4. Shakeout / Reversal
                min_lo_5 = float(hist.get('Low', closes).tail(6).head(5).min())
                if c_lo < min_lo_5 and c_cl > c_lo + (c_hi - c_lo) * 0.6 and c_vo > avg_vol_10:
                    candle_signals.append("Shakeout & Reversal (Supply Absorbed)")
        except Exception:
            candle_signals = []

        return {
            "_ticker_raw": ticker,
            "price": round(price, 3), "change": round(chg1d, 2),
            "ma50": ma50, "ma150": ma150, "ma200": ma200,
            "volRatio": volr, "pvr": pvr, "vcpScore": vcp, "sepaScore": sepa,
            "pctFromHigh": pct_hi, "pctAboveLow": pct_lo,
            "hi52": round(hi52, 2), "lo52": round(lo52, 2),
            "chg5d": chg5d, "chg60d": chg60d, "chg250d": chg250d,
            "status": status,
            "stage": stage,
            "ohlcv": ohlcv,
            "candleSignals": candle_signals,
            "accDistRatio": acc_dist_ratio,
            "tech": technicals(hist),
            "ipo": ipo, "sessions": int(len(closes)),
            "listDate": str(hist.index[0].date()) if ipo else None,
            "checks": {"ma50": c_ma50, "ma150": c_ma150, "ma200": c_ma200,
                       "trend": c_trend, "high": c_high, "low": c_low, "vol": c_vol},
            # filled in later by enrich_stock
            "ticker": ticker, "name": ticker,
            "sector": "", "mktcap": 0, "mktcapFmt": "",
            "shortSignal": "", "analysis": "",
            "revGrowth": None, "revTrend": None, "revQuarters": rev_quarters,
            "epsGrowth": None, "netMargin": None,
            "trailingEps": None, "forwardEps": None, "fundScore": 0,
            "nextEarnings": None, "nextEventLabel": None,
            "nextExDiv": None, "daysToEvent": None,
        }
    except Exception as e:
        print(f"  score_stock {ticker}: {e}")
        return None

# ── Enrich one passing stock with metadata from t.info ────────────────────────
def enrich_stock(r):
    ticker = r["_ticker_raw"]
    try:
        t    = yf.Ticker(ticker)
        inf2 = {}
        for attempt in range(3):
            try:
                inf2 = t.info or {}
                if inf2.get("marketCap") or inf2.get("longName"):
                    break
            except Exception:
                pass
            time.sleep(2 * (attempt + 1) + random.random())
        meta = NASDAQ_META.get(ticker, {})
        if not inf2.get("marketCap") and meta.get("mktcap"):
            inf2["marketCap"] = meta["mktcap"]
        if not inf2.get("longName") and meta.get("name"):
            inf2["longName"] = meta["name"]
        if not inf2.get("sector") and meta.get("sector"):
            inf2["sector"] = meta["sector"]

        mktcap = float(inf2.get('marketCap') or 0)
        if mktcap < MIN_MARKET_CAP and mktcap > 0:
            return None   # filter by market cap now that we have it

        r["mktcap"]    = int(mktcap)
        r["mktcapFmt"] = fmt_cap(mktcap)
        r["name"]      = inf2.get('longName', ticker)
        r["sector"]    = inf2.get('sector', '') or inf2.get('industry', '') or ''
        r["ticker"]    = ticker

        pm = inf2.get('profitMargins')
        te = inf2.get('trailingEps')
        fe = inf2.get('forwardEps')
        rg = inf2.get('revenueGrowth')
        eg = inf2.get('earningsGrowth')

        if pm is not None: r["netMargin"]   = round(pm * 100, 1)
        if te is not None: r["trailingEps"] = round(float(te), 3)
        if fe is not None: r["forwardEps"]  = round(float(fe), 3)
        if rg is not None: r["revGrowth"]   = round(rg * 100, 1)
        if eg is not None: r["epsGrowth"]   = round(eg * 100, 1)

        rv = r["revGrowth"]
        if rv is not None:
            r["revTrend"] = 'accelerating' if rv > 20 else 'growing' if rv > 5 else 'declining' if rv < 0 else 'flat'

        fs = 0
        if rv is not None and rv > 5:  fs += 1
        if rv is not None and rv > 20: fs += 1
        if r["epsGrowth"] is not None and r["epsGrowth"] > 0: fs += 1
        r["fundScore"] = min(fs, 3)

        # Analyst consensus - comes in the same t.info response, so no extra request
        try:
            def _an(v):
                try:
                    v = float(v)
                    return round(v, 2) if v == v and v > 0 else None
                except Exception:
                    return None
            # recommendationKey is only present when Yahoo returned its fundamentals;
            # without it we cannot tell "no coverage" from "request failed"
            r["analystChecked"] = 'recommendationKey' in inf2
            n_an = int(inf2.get('numberOfAnalystOpinions') or 0)
            rkey = str(inf2.get('recommendationKey') or '').lower()
            if n_an > 0 and rkey and rkey != 'none':
                r["analyst"] = {
                    "n": n_an, "key": rkey,
                    "mean": _an(inf2.get('recommendationMean')),
                    "tMean": _an(inf2.get('targetMeanPrice')),
                    "tMed": _an(inf2.get('targetMedianPrice')),
                    "tHigh": _an(inf2.get('targetHighPrice')),
                    "tLow": _an(inf2.get('targetLowPrice')),
                }
        except Exception:
            pass

        # Calendar (inline)
        try:
            today = today_ny()
            cal   = t.calendar
            if isinstance(cal, dict):
                ed_list = cal.get('Earnings Date') or cal.get('earningsDate') or []
                if isinstance(ed_list, (list, tuple)) and ed_list: ed = _parse_date(ed_list[0])
                elif ed_list: ed = _parse_date(ed_list)
                else: ed = None
                if ed:
                    days = (ed - today).days
                    if -30 <= days <= 180:
                        r["nextEarnings"] = str(ed)
                        r["daysToEvent"]  = days
                        if days == 0:    r["nextEventLabel"] = "⚡ RESULTS TODAY"
                        elif days <= 7:  r["nextEventLabel"] = f"⚡ Results in {days}d"
                        elif days <= 30: r["nextEventLabel"] = f"📅 Results in {days}d"
                        else:            r["nextEventLabel"] = f"📅 Results {ed.strftime('%d %b')}"
                xd = cal.get('Ex-Dividend Date') or cal.get('exDividendDate')
                if xd:
                    d2 = _parse_date(xd)
                    if d2 and (d2 - today).days >= -7:
                        r["nextExDiv"] = d2.strftime('%d %b %Y')
        except Exception:
            pass

    except Exception:
        meta = NASDAQ_META.get(ticker, {})   # keep stock, fill what Nasdaq knows
        if meta:
            r["name"] = meta.get("name") or r["name"]
            r["sector"] = meta.get("sector") or r["sector"]
            r["mktcap"] = int(meta.get("mktcap") or 0)
            r["mktcapFmt"] = fmt_cap(r["mktcap"]) if r["mktcap"] else ""

    # Build short signals and analysis text
    volr    = r["volRatio"]
    chg250d = r["chg250d"]
    vcp     = r["vcpScore"]
    sepa    = r["sepaScore"]
    pct_hi  = r["pctFromHigh"]
    hi52    = r["hi52"]
    pvr     = r["pvr"]
    rev_trend       = r["revTrend"]
    next_event_label = r["nextEventLabel"]
    rev_growth_pct  = r["revGrowth"]
    eps_growth_pct  = r["epsGrowth"]
    trailing_eps    = r["trailingEps"]
    name            = r["name"]
    c_vol           = r["checks"]["vol"]
    c_ma50          = r["checks"]["ma50"]
    c_ma150         = r["checks"]["ma150"]
    c_ma200         = r["checks"]["ma200"]

    sigs = []
    if c_vol:                           sigs.append(f"Vol {volr}x avg")
    if chg250d > 50:                    sigs.append(f"+{chg250d}% 12M")
    if vcp >= 3:                        sigs.append("VCP tightening")
    if pct_hi < 5:                      sigs.append("Near 52W high")
    if rev_trend == 'accelerating':     sigs.append("↑↑ Revenue accelerating")
    elif rev_trend == 'growing':        sigs.append("↑ Revenue growing")
    if next_event_label and ('⚡' in next_event_label or '📅' in next_event_label):
        sigs.append(next_event_label)
    if not sigs: sigs.append(f"SEPA {sepa}/7")
    r["shortSignal"] = " · ".join(sigs[:3])

    tr   = "strongly uptrending" if chg250d > 40 else "uptrending" if chg250d > 15 else "recovering"
    mas  = "fully aligned (Price>MA50>MA150>MA200)" if (c_ma50 and c_ma150 and c_ma200) else "partially aligned"
    vls  = f"Volume is {volr}x the 50-day average" if volr >= 1.5 else f"Volume at {volr}x average"
    vcpd = ["no base","early base","developing VCP","good VCP (volume drying up)","textbook VCP (volume at lows)"][vcp]
    fund_ctx = ""
    if rev_growth_pct is not None:
        td = " (accelerating)" if rev_trend == 'accelerating' else " (growing)" if rev_trend == 'growing' else ""
        if rev_growth_pct > 20:  fund_ctx += f" Revenue growing strongly +{rev_growth_pct}% YoY{td}."
        elif rev_growth_pct > 5: fund_ctx += f" Revenue +{rev_growth_pct}% YoY{td}."
        elif rev_growth_pct < 0: fund_ctx += f" Revenue declined {rev_growth_pct}% YoY."
    if eps_growth_pct is not None and eps_growth_pct > 0:
        fund_ctx += f" EPS growth +{eps_growth_pct}%."
    elif trailing_eps and trailing_eps > 0:
        fund_ctx += f" Profitable (trailing EPS ${trailing_eps})."
    catalyst = f" CATALYST: {next_event_label}." if next_event_label else ""

    r["analysis"] = (
        f"{name} is {tr} over 12 months ({fmt_pct(chg250d)}), MAs {mas}. "
        f"Forming {vcpd}, {pct_hi}% below 52W high of ${round(hi52,2)}. "
        f"{vls}. SEPA {sepa}/7, PVR {pvr}.{fund_ctx}{catalyst}"
    )

    del r["_ticker_raw"]
    return r

def fetch_all():
    print(f"Fetching price history for {len(US_TICKERS)} US stocks in batches...")

    # Step 1: batch download price history (fast — one request per 50 stocks)
    BATCH = 50
    hist_map = {}
    for i in range(0, len(US_TICKERS), BATCH):
        chunk = US_TICKERS[i:i+BATCH]
        batch_result = download_chunk(chunk)
        hist_map.update(batch_result)
        pct = min(i + BATCH, len(US_TICKERS))
        print(f"  Price data: {pct}/{len(US_TICKERS)} tickers fetched, {len(hist_map)} with data")
        time.sleep(0.5)   # small pause between batches

    print(f"Price history: {len(hist_map)} tickers with >=30 days data")

    # S&P 500 benchmark for relative strength
    global SPY_CLOSE
    try:
        spy = download_chunk(["SPY"]).get("SPY")
        if spy is not None and not spy.empty:
            SPY_CLOSE = spy["Close"].astype(float)
            if hasattr(SPY_CLOSE, "columns"):   # yfinance may return a 1-col frame
                SPY_CLOSE = SPY_CLOSE.iloc[:, 0]
            print(f"SPY benchmark: {len(SPY_CLOSE)} sessions")
    except Exception as e:
        print(f"SPY benchmark unavailable: {e}")

    # Step 2: score all stocks from price data (CPU only, no network)
    candidates = []
    for ticker, hist in hist_map.items():
        r = score_stock(ticker, hist.tail(252))   # scoring uses the last year, as before
        if r:
            candidates.append(r)
    print(f"Passed SEPA filters: {len(candidates)} stocks — now enriching with metadata...")

    # Step 3: enrich passing stocks with t.info (parallel, but only ~candidates)
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(enrich_stock, r): r["ticker"] for r in candidates}
        done = 0
        for f in as_completed(futs):
            done += 1
            r = f.result()
            if r:
                results.append(r)

    # Step 4: decision engine, candlestick patterns, Ichimoku, market filter, backtest
    global META
    market = decision.market_state(SPY_CLOSE)
    print(f"Market filter: {market['label']}")
    for r in results:
        try:
            hist = hist_map.get(r["ticker"])
            tail = hist.tail(20)
            adv = float((tail["Close"] * tail["Volume"]).mean()) if len(tail) else 0
            last2 = hist.tail(2)
            locked = bool(len(last2) == 2 and ((last2["High"] == last2["Low"]) & (last2["Low"] == last2["Close"])).all())
            r["decision"] = decision.decide(hist, SPY_CLOSE, market, liquid=adv >= MIN_ADV, locked=locked)
            r["patterns"] = decision.candle_patterns(hist)
            r["ichimoku"] = decision.ichimoku(hist)
        except Exception as e:
            print(f"Decision failed for {r.get('ticker')}: {type(e).__name__}: {e}")
            r["decision"] = None
    bt = decision.backtest(hist_map, SPY_CLOSE, min_adv=MIN_ADV)
    print(f"Backtest of the BUY rule: {bt}")
    META = {"market": market, "backtest": bt}
    from collections import Counter
    print("Decisions:", dict(Counter((r.get("decision") or {}).get("action") for r in results)))

    results.sort(key=lambda x: (x['sepaScore'], x['vcpScore']), reverse=True)
    return results

META = {}

# Deployment is handled by GitHub Pages via the workflow — no publish function needed.

if __name__ == "__main__":
    print(f"SEPA+VCP US Screener - {today_ny()} (New York)")
    data = fetch_all()
    b = sum(1 for r in data if r['status'] == 'breakout')
    p = sum(1 for r in data if r['status'] == 'near-pivot')
    w = sum(1 for r in data if r['status'] == 'watch')
    print(f"Results: {len(data)} | Breakouts:{b} | NearPivot:{p} | Watch:{w}")
    import math
    bad = sum(1 for r in data if not isinstance(r.get('price'), (int, float))
              or not math.isfinite(r['price']))
    if data and bad > len(data) * 0.05:
        import sys
        print(f"ERROR: {bad}/{len(data)} rows have no valid price - refusing to "
              "publish a broken dashboard.")
        sys.exit(1)
    if not data:
        import sys
        print("ERROR: screener returned 0 rows — refusing to overwrite the "
              "live dashboard with an empty one.")
        sys.exit(1)
    try:
        import build_dashboard
        html = build_dashboard.build(data, min_cap=MIN_MARKET_CAP, meta=META)
        with open('index.html', 'w', encoding='utf-8') as f: f.write(html)
        print(f"Dashboard built: {len(html):,} chars")
        print("index.html ready — GitHub Pages deployment handled by workflow.")
    except Exception as ex:
        import traceback
        tb = traceback.format_exc()
        print(f"BUILD FAILED:\n{tb}")
        fallback = f'<html><body><pre style="padding:20px">Build error ({today_ny()}):\n{tb}</pre></body></html>'
        with open('index.html', 'w', encoding='utf-8') as f: f.write(fallback)
        print("Wrote fallback index.html for debugging")
