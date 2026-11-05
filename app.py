"""S&H Marktboard – Stocks and Holdings
Zeigt das Board 1:1 wie im Claude-Artifact (web/board.html) und füllt es mit Live-Daten von Yahoo Finance."""
import html
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

st.set_page_config(page_title="S&H Marktboard", page_icon="logo.png", layout="wide", initial_sidebar_state="collapsed")
BERLIN = ZoneInfo("Europe/Berlin")

# ---------- Börsen: Zeitzone, Öffnung, Schluss, Mittagspause ----------
NY = ("America/New_York", time(9, 30), time(16, 0), None)
XETRA = ("Europe/Berlin", time(9, 0), time(17, 30), None)
TOKIO = ("Asia/Tokyo", time(9, 0), time(15, 30), (time(11, 30), time(12, 30)))
HK = ("Asia/Hong_Kong", time(9, 30), time(16, 0), (time(12, 0), time(13, 0)))
KRYPTO = ("Europe/Berlin", time(0, 0), time(23, 59), None)

# id im Board: (Yahoo-Ticker, Anzeigename, Währung, Börse, Ticker für Nachrichten)
INDIZES = {
    "msci": ("URTH", "MSCI World", "USD", NY, "URTH"),
    "spx": ("^GSPC", "S&P 500", "USD", NY, "SPY"),
    "spit": ("XLK", "S&P 500 Tech", "USD", NY, "XLK"),
    "dax": ("^GDAXI", "DAX", "EUR", XETRA, "^GDAXI"),
    "dow": ("^DJI", "Dow Jones", "USD", NY, "DIA"),
    "qqq": ("QQQ", "QQQ", "USD", NY, "QQQ"),
    "ftseaw": ("VT", "FTSE All-World", "USD", NY, "VT"),
    "nikkei": ("^N225", "Nikkei 225", "JPY", TOKIO, "^N225"),
    "hsi": ("^HSI", "Hang Seng", "HKD", HK, "^HSI"),
    "vix": ("^VIX", "VIX", "USD", NY, "^VIX"),
}
AKTIEN = {
    "sie": ("SIE.DE", XETRA), "dte": ("DTE.DE", XETRA), "nke": ("NKE", NY), "btc": ("BTC-USD", KRYPTO),
    "alv": ("ALV.DE", XETRA), "pep": ("PEP", NY), "ko": ("KO", NY), "nvda": ("NVDA", NY), "aapl": ("AAPL", NY),
    "msft": ("MSFT", NY), "avgo": ("AVGO", NY), "orcl": ("ORCL", NY), "mu": ("MU", NY), "googl": ("GOOGL", NY),
    "meta": ("META", NY), "amzn": ("AMZN", NY), "tsla": ("TSLA", NY), "jpm": ("JPM", NY), "v": ("V", NY),
    "lly": ("LLY", NY), "cat": ("CAT", NY), "xom": ("XOM", NY), "mdlz": ("MDLZ", NY),
}
# Branche im Board: (Sektor-ETF, Mitglieder-ids mit Gewicht)
BRANCHEN = {
    "tech": ("XLK", {"nvda": 20, "aapl": 19, "msft": 17, "avgo": 6, "orcl": 3.5, "mu": 3.5}),
    "fin": ("XLF", {"jpm": 14, "v": 11}), "disc": ("XLY", {"amzn": 35, "tsla": 20}),
    "comm": ("XLC", {"googl": 45, "meta": 25}), "health": ("XLV", {"lly": 16}), "ind": ("XLI", {"cat": 12}),
    "stap": ("XLP", {"ko": 18, "pep": 14, "mdlz": 8}), "energy": ("XLE", {"xom": 30}),
    "util": ("XLU", {}), "re": ("XLRE", {}), "mat": ("XLB", {}),
}
QUARTALS_LISTE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "ABNB", "QCOM", "NKE", "PEP", "KO",
                  "JPM", "WMT", "DIS", "NFLX", "SAP.DE", "SIE.DE", "DTE.DE", "ALV.DE", "BAS.DE", "MBG.DE", "RHM.DE"]


def minute(ts):
    return ts.hour * 60 + ts.minute


def boerse_berlin(boerse, datum):
    """Öffnung, Schluss und Mittagspause der Börse an diesem Tag, als Minuten in Berliner Zeit."""
    tz, auf, zu, pause = boerse
    z = ZoneInfo(tz)
    f = lambda t: minute(datetime.combine(datum, t, z).astimezone(BERLIN))
    return f(auf), f(zu), ([f(pause[0]), f(pause[1])] if pause else None)


# ---------- Daten holen ----------
@st.cache_data(ttl=90, show_spinner=False)
def intraday_alle(tickers: tuple):
    d = yf.download(list(tickers), period="5d", interval="5m", group_by="ticker", progress=False, threads=True, auto_adjust=False)
    out = {}
    for t in tickers:
        try:
            c = d[t]["Close"].dropna() if isinstance(d.columns, pd.MultiIndex) else d["Close"].dropna()
        except KeyError:
            continue
        if c.empty:
            continue
        c.index = c.index.tz_convert(BERLIN)
        out[t] = c
    return out


@st.cache_data(ttl=900, show_spinner=False)
def nachrichten(ticker: str):
    try:
        roh = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for n in roh:
        c = n.get("content", n)
        titel, zeit = c.get("title"), c.get("pubDate") or c.get("providerPublishTime")
        if not titel or not zeit:
            continue
        ts = pd.to_datetime(zeit, unit="s", utc=True) if isinstance(zeit, (int, float)) else pd.to_datetime(zeit, utc=True)
        url = c.get("canonicalUrl")
        link = url.get("url") if isinstance(url, dict) else c.get("link")
        prov = c.get("provider")
        quelle = prov.get("displayName") if isinstance(prov, dict) else c.get("publisher", "")
        out.append({"zeit": ts.tz_convert(BERLIN), "titel": titel, "link": link, "quelle": quelle or ""})
    return sorted(out, key=lambda x: x["zeit"])


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def quartalszahlen(tickers: tuple):
    jetzt = datetime.now(BERLIN)
    out = []
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            df = tk.get_earnings_dates(limit=8)
            name = tk.info.get("shortName", t)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for zeit, row in df.iterrows():
            z = zeit.tz_convert(BERLIN)
            if jetzt - timedelta(days=3) <= z <= jetzt + timedelta(days=10):
                erw, ist = row.get("EPS Estimate"), row.get("Reported EPS")
                e = {"tk": t.split(".")[0], "name": name, "t": int(z.timestamp() * 1000), "q": "Quartalszahlen"}
                if pd.notna(erw):
                    e["est"] = {"eps": float(erw)}
                if pd.notna(ist):
                    e["act"] = {"eps": float(ist)}
                    if pd.notna(erw):
                        e["more"] = [f"Überraschung: {row.get('Surprise(%)', 0):+.1f} %".replace(".", ",")]
                out.append(e)
    return sorted(out, key=lambda x: x["t"])


# ---------- Live-Daten fürs Board aufbereiten ----------
def sitzung(kurs: pd.Series, boerse):
    """Letzte Handelssitzung: Kurve als [Minute, Wert], Vortagesschluss, Zeitfenster."""
    tage = sorted(set(kurs.index.date))
    heute = kurs[kurs.index.date == tage[-1]]
    vortag = float(kurs[kurs.index.date == tage[-2]].iloc[-1]) if len(tage) > 1 else float(heute.iloc[0])
    auf, zu, pause = boerse_berlin(boerse, tage[-1])
    jetzt = datetime.now(BERLIN)
    offen = tage[-1] == jetzt.date() and auf <= minute(jetzt) < zu
    return heute, vortag, [min(auf, minute(heute.index[0])), max(zu, minute(heute.index[-1]))], pause, \
        ("live" if offen or boerse is KRYPTO else "close"), tage[-1]


def events(news_ticker, datum, prefix):
    ev = {}
    for i, n in enumerate(nachrichten(news_ticker)):
        if n["zeit"].date() != datum:
            continue
        k = f"{prefix}{i}"
        ev[k] = {"t": minute(n["zeit"]), "place": html.escape(n["quelle"] or "Nachricht"),
                 "h": html.escape(n["titel"]), "b": [], "w": "", "link": n["link"]}
    return ev


@st.cache_data(ttl=90, show_spinner="Lade Live-Kurse …")
def live_daten():
    jetzt = datetime.now(BERLIN)
    tickers = tuple({v[0] for v in INDIZES.values()} | {v[0] for v in AKTIEN.values()})
    kurse = intraday_alle(tickers)
    live = {"now": minute(jetzt), "stand": f"{jetzt:%H:%M}", "idx": {}, "stk": {}, "ev": {}, "evfor": {}, "sec": {}, "er": []}

    for bid, (t, name, cur, boerse, news_t) in INDIZES.items():
        if t not in kurse:
            continue
        heute, vortag, dom, pause, status, datum = sitzung(kurse[t], boerse)
        vix = bid == "vix"
        s = [[minute(ts), round(float(v), 2) if vix else round((float(v) / vortag - 1) * 100, 4)] for ts, v in heute.items()]
        live["idx"][bid] = {"name": name, "cur": cur, "prev": vortag, "last": float(heute.iloc[-1]), "s": s, "dom": dom,
                            "status": status, "lunch": pause, "open": float(heute.iloc[0]), "high": float(heute.max()),
                            "low": float(heute.min())}
        ev = events(news_t, datum, bid)
        live["ev"].update(ev)
        live["evfor"][bid] = list(ev)

    for sid, (t, boerse) in AKTIEN.items():
        if t not in kurse:
            continue
        heute, vortag, dom, _, status, datum = sitzung(kurse[t], boerse)
        last = float(heute.iloc[-1])
        live["stk"][sid] = {"last": last, "p": (last / vortag - 1) * 100, "dom": dom, "status": status,
                            "s": [[minute(ts), round((float(v) / vortag - 1) * 100, 4)] for ts, v in heute.items()]}
        ev = events(t, datum, sid)
        live["ev"].update(ev)
        live["evfor"][sid] = list(ev)

    # Ø Markt: Nachrichten der großen Märkte
    live["evfor"]["welt"] = [k for k in live["ev"] if k.startswith(("spx", "qqq", "dax", "nikkei", "hsi"))][-14:]

    for sec, (etf, mitglieder) in BRANCHEN.items():
        werte = [(live["stk"][m]["p"], w) for m, w in mitglieder.items() if m in live["stk"]]
        if werte:
            p = sum(a * w for a, w in werte) / sum(w for _, w in werte)
        else:
            k = intraday_alle((etf,)).get(etf)
            p = (float(k.iloc[-1]) / float(k[k.index.date < k.index[-1].date()].iloc[-1]) - 1) * 100 if k is not None and len(set(k.index.date)) > 1 else 0
        meldungen = [f'<a href="{n["link"]}" target="_blank" rel="noopener" style="color:inherit">{html.escape(n["titel"])}</a>'
                     if n["link"] else html.escape(n["titel"]) for n in nachrichten(etf)[-4:][::-1]]
        live["sec"][sec] = {"p": p, "news": meldungen}

    live["er"] = quartalszahlen(tuple(QUARTALS_LISTE))
    live["foot"] = (f"Live-Daten von Yahoo Finance, bis ca. 15 Min. verzögert · Stand {jetzt:%d.%m.%Y, %H:%M} Uhr · "
                    "MSCI World = ETF URTH, FTSE All-World = ETF VT, S&amp;P 500 Tech = ETF XLK · Zum Aktualisieren Seite neu laden · "
                    "Keine Anlageberatung")
    return live


# ---------- Anzeige: das Board füllt den ganzen Bildschirm ----------
st.markdown("""<style>
header,footer,[data-testid="stToolbar"],[data-testid="stDecoration"],[data-testid="stStatusWidget"]{display:none!important}
.stApp{background:#07111B} .block-container{padding:0!important;max-width:100%!important}
iframe{height:100vh!important;height:100dvh!important;display:block}
[data-testid="stVerticalBlock"]{gap:0}
</style>""", unsafe_allow_html=True)

seite = Path(__file__).parent.joinpath("web", "board.html").read_text(encoding="utf-8")
daten = json.dumps(live_daten(), ensure_ascii=False).replace("</", "<\\/")
seite = seite.replace("/*__LIVE__*/null", daten, 1)
components.html("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<style>:root{color-scheme:dark}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>"
                + seite + "</body></html>", height=1000, scrolling=True)
