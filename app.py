"""S&H Marktboard – Stocks and Holdings
Zeigt das Board (web/board.html) und füllt es mit Live-Daten von Yahoo Finance.
Nachrichten werden automatisch ins Deutsche übersetzt und als Kurzfassung direkt im Board gezeigt."""
import html
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from deep_translator import GoogleTranslator

st.set_page_config(page_title="S&H Marktboard", page_icon="logo.png", layout="wide", initial_sidebar_state="collapsed")
BERLIN = ZoneInfo("Europe/Berlin")

# ---------- Börsen: Zeitzone, Öffnung, Schluss, Mittagspause ----------
NY = ("America/New_York", time(9, 30), time(16, 0), None)
XETRA = ("Europe/Berlin", time(9, 0), time(17, 30), None)
TOKIO = ("Asia/Tokyo", time(9, 0), time(15, 30), (time(11, 30), time(12, 30)))
HK = ("Asia/Hong_Kong", time(9, 30), time(16, 0), (time(12, 0), time(13, 0)))
KRYPTO = ("Europe/Berlin", time(0, 0), time(23, 59), None)

# Board-id: (Yahoo-Ticker, Name, Währung, Börse, Ticker für Nachrichten)
INDIZES = {
    "msci": ("URTH", "MSCI World", "USD", NY, "URTH"), "spx": ("^GSPC", "S&P 500", "USD", NY, "SPY"),
    "spit": ("XLK", "S&P 500 Tech", "USD", NY, "XLK"), "dax": ("^GDAXI", "DAX", "EUR", XETRA, "^GDAXI"),
    "dow": ("^DJI", "Dow Jones", "USD", NY, "DIA"), "qqq": ("QQQ", "QQQ", "USD", NY, "QQQ"),
    "ftseaw": ("VT", "FTSE All-World", "USD", NY, "VT"), "nikkei": ("^N225", "Nikkei 225", "JPY", TOKIO, "^N225"),
    "hsi": ("^HSI", "Hang Seng", "HKD", HK, "^HSI"), "vix": ("^VIX", "VIX", "USD", NY, "^VIX"),
}

# Firmen: Ticker|Name|Webadresse (Webadresse für das Logo)
FIRMEN = {z.split("|")[0]: z.split("|")[1:] for z in """
NVDA|Nvidia|nvidia.com;AAPL|Apple|apple.com;MSFT|Microsoft|microsoft.com;AVGO|Broadcom|broadcom.com;ORCL|Oracle|oracle.com;
AMD|AMD|amd.com;CRM|Salesforce|salesforce.com;CSCO|Cisco|cisco.com;MU|Micron|micron.com;ADBE|Adobe|adobe.com;
GOOGL|Alphabet|google.com;META|Meta|meta.com;NFLX|Netflix|netflix.com;DIS|Disney|disney.com;TMUS|T-Mobile US|t-mobile.com;
VZ|Verizon|verizon.com;AMZN|Amazon|amazon.com;TSLA|Tesla|tesla.com;HD|Home Depot|homedepot.com;MCD|McDonald's|mcdonalds.com;
NKE|Nike|nike.com;BKNG|Booking|booking.com;SBUX|Starbucks|starbucks.com;BRK-B|Berkshire|berkshirehathaway.com;
JPM|JPMorgan|jpmorganchase.com;V|Visa|visa.com;MA|Mastercard|mastercard.com;BAC|Bank of America|bankofamerica.com;
GS|Goldman Sachs|goldmansachs.com;WFC|Wells Fargo|wellsfargo.com;LLY|Eli Lilly|lilly.com;UNH|UnitedHealth|unitedhealthgroup.com;
JNJ|Johnson & Johnson|jnj.com;ABBV|AbbVie|abbvie.com;MRK|Merck & Co|merck.com;PFE|Pfizer|pfizer.com;GE|GE Aerospace|geaerospace.com;
CAT|Caterpillar|caterpillar.com;RTX|RTX|rtx.com;HON|Honeywell|honeywell.com;UBER|Uber|uber.com;BA|Boeing|boeing.com;
WMT|Walmart|walmart.com;COST|Costco|costco.com;PG|Procter & Gamble|pg.com;KO|Coca-Cola|coca-cola.com;PEP|PepsiCo|pepsico.com;
MDLZ|Mondelez|mondelezinternational.com;XOM|Exxon|exxonmobil.com;CVX|Chevron|chevron.com;COP|ConocoPhillips|conocophillips.com;
NEE|NextEra|nexteraenergy.com;SO|Southern Co|southerncompany.com;DUK|Duke Energy|duke-energy.com;PLD|Prologis|prologis.com;
AMT|American Tower|americantower.com;EQIX|Equinix|equinix.com;LIN|Linde|linde.com;SHW|Sherwin-Williams|sherwin-williams.com;
FCX|Freeport|fcx.com;ABNB|Airbnb|airbnb.com;QCOM|Qualcomm|qualcomm.com;INTC|Intel|intel.com;PLTR|Palantir|palantir.com;
PYPL|PayPal|paypal.com;SHOP|Shopify|shopify.com;SNOW|Snowflake|snowflake.com;ARM|Arm|arm.com;SPOT|Spotify|spotify.com;
SAP.DE|SAP|sap.com;SIE.DE|Siemens|siemens.com;ALV.DE|Allianz|allianz.com;DTE.DE|Deutsche Telekom|telekom.com;
MBG.DE|Mercedes-Benz|mercedes-benz.com;BMW.DE|BMW|bmw.com;VOW3.DE|Volkswagen|volkswagen.de;BAS.DE|BASF|basf.com;
BAYN.DE|Bayer|bayer.com;IFX.DE|Infineon|infineon.com;MUV2.DE|Munich Re|munichre.com;DBK.DE|Deutsche Bank|db.com;
RHM.DE|Rheinmetall|rheinmetall.com;ADS.DE|Adidas|adidas.com;DHL.DE|DHL Group|dhl.com;EOAN.DE|E.ON|eon.com;RWE.DE|RWE|rwe.com;
HEN3.DE|Henkel|henkel.com;BEI.DE|Beiersdorf|beiersdorf.com;MRK.DE|Merck KGaA|merckgroup.com;ENR.DE|Siemens Energy|siemens-energy.com;
CBK.DE|Commerzbank|commerzbank.de;HNR1.DE|Hannover Rück|hannover-re.com;BTC-USD|Bitcoin|bitcoin.org
""".strip().replace("\n", "").split(";") if z}

# Branchen der Heatmap (Board-id: Sektor-ETF für Meldungen, Aktien mit Gewicht in Mrd. $)
BRANCHEN = {
    "tech": ("XLK", {"NVDA": 4400, "AAPL": 4000, "MSFT": 3800, "AVGO": 1400, "ORCL": 600, "AMD": 300, "CRM": 250, "CSCO": 280, "MU": 200, "ADBE": 150}),
    "comm": ("XLC", {"GOOGL": 3200, "META": 1600, "NFLX": 450, "TMUS": 260, "DIS": 200, "VZ": 180}),
    "disc": ("XLY", {"AMZN": 2500, "TSLA": 1100, "HD": 380, "MCD": 220, "BKNG": 170, "SBUX": 100, "NKE": 90}),
    "fin": ("XLF", {"BRK-B": 1000, "JPM": 850, "V": 650, "MA": 520, "BAC": 350, "WFC": 260, "GS": 250}),
    "health": ("XLV", {"LLY": 900, "JNJ": 420, "ABBV": 380, "UNH": 300, "MRK": 250, "PFE": 150}),
    "ind": ("XLI", {"GE": 300, "CAT": 260, "RTX": 220, "UBER": 200, "BA": 160, "HON": 140}),
    "stap": ("XLP", {"WMT": 800, "COST": 420, "PG": 360, "KO": 300, "PEP": 200, "MDLZ": 90}),
    "energy": ("XLE", {"XOM": 480, "CVX": 300, "COP": 120}),
    "util": ("XLU", {"NEE": 160, "SO": 100, "DUK": 95}),
    "re": ("XLRE", {"PLD": 110, "AMT": 90, "EQIX": 80}),
    "mat": ("XLB", {"LIN": 220, "SHW": 85, "FCX": 60}),
}
LISTE = {"SIE.DE": XETRA, "DTE.DE": XETRA, "NKE": NY, "BTC-USD": KRYPTO, "ALV.DE": XETRA, "PEP": NY, "KO": NY}
QUARTALS_LISTE = [t for t in FIRMEN if t != "BTC-USD"]


def boerse_von(ticker):
    return LISTE.get(ticker) or (XETRA if ticker.endswith(".DE") else NY)


def bid(ticker):
    return ticker.lower().replace(".de", "").replace("-usd", "").replace("-", "")


def minute(ts):
    return ts.hour * 60 + ts.minute


def logo_urls(ticker):
    dom = FIRMEN.get(ticker, [None, None])[1]
    urls = [f"https://financialmodelingprep.com/image-stock/{ticker}.png"]
    if dom:
        urls.append(f"https://www.google.com/s2/favicons?domain={dom}&sz=128")
    return urls


# ---------- Übersetzung ins Deutsche (mit Zwischenspeicher) ----------
@st.cache_resource
def _uebersetzungen():
    return {}


def _glatt(t):
    return " ".join(str(t).split())[:500]


def _block(texte):
    """Mehrere Texte in einem Rutsch übersetzen (Zeilen bleiben erhalten)."""
    try:
        aus = GoogleTranslator(source="auto", target="de").translate("\n".join(texte)) or ""
        teile = aus.split("\n")
        if len(teile) == len(texte):
            return teile
    except Exception:
        pass
    erg = []
    for t in texte:
        try:
            erg.append(GoogleTranslator(source="auto", target="de").translate(t) or t)
        except Exception:
            erg.append(t)
    return erg


def deutsch(texte):
    speicher = _uebersetzungen()
    neu = [t for t in dict.fromkeys(_glatt(x) for x in texte if x) if t not in speicher]
    bloecke, akt, n = [], [], 0
    for t in neu:
        if akt and n + len(t) > 3500:
            bloecke.append(akt)
            akt, n = [], 0
        akt.append(t)
        n += len(t) + 1
    if akt:
        bloecke.append(akt)
    with ThreadPoolExecutor(4) as ex:
        for blk, erg in zip(bloecke, ex.map(_block, bloecke)):
            speicher.update(zip(blk, erg))
    return lambda x: speicher.get(_glatt(x), x) if x else x


# ---------- Daten holen ----------
@st.cache_data(ttl=120, show_spinner=False)
def intraday_alle(tickers: tuple):
    d = yf.download(list(tickers), period="5d", interval="5m", group_by="ticker", progress=False, threads=True, auto_adjust=False)
    out = {}
    for t in tickers:
        try:
            c = (d[t]["Close"] if isinstance(d.columns, pd.MultiIndex) else d["Close"]).dropna()
        except KeyError:
            continue
        if not c.empty:
            c.index = c.index.tz_convert(BERLIN)
            out[t] = c
    return out


def _news(ticker):
    try:
        roh = yf.Ticker(ticker).news or []
    except Exception:
        return ticker, []
    out = []
    for n in roh:
        c = n.get("content", n)
        titel, zeit = c.get("title"), c.get("pubDate") or c.get("providerPublishTime")
        if not titel or not zeit:
            continue
        ts = pd.to_datetime(zeit, unit="s", utc=True) if isinstance(zeit, (int, float)) else pd.to_datetime(zeit, utc=True)
        url = c.get("canonicalUrl") or c.get("clickThroughUrl")
        link = url.get("url") if isinstance(url, dict) else c.get("link")
        prov = c.get("provider")
        quelle = prov.get("displayName") if isinstance(prov, dict) else c.get("publisher", "")
        out.append({"zeit": ts.tz_convert(BERLIN), "titel": titel, "text": c.get("summary") or c.get("description") or "",
                    "link": link, "quelle": quelle or "Quelle"})
    return ticker, sorted(out, key=lambda x: x["zeit"])


@st.cache_data(ttl=900, show_spinner=False)
def nachrichten_alle(tickers: tuple):
    with ThreadPoolExecutor(12) as ex:
        return dict(ex.map(_news, tickers))


def _termine(t):
    jetzt = datetime.now(BERLIN)
    try:
        df = yf.Ticker(t).get_earnings_dates(limit=6)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    out = []
    for zeit, row in df.iterrows():
        z = zeit.tz_convert(BERLIN)
        if not (jetzt - timedelta(days=3) <= z <= jetzt + timedelta(days=14)):
            continue
        erw, ist, ueb = row.get("EPS Estimate"), row.get("Reported EPS"), row.get("Surprise(%)")
        e = {"tk": t.split(".")[0], "ytk": t, "name": FIRMEN.get(t, [t])[0], "t": int(z.timestamp() * 1000), "q": "Quartalszahlen"}
        if pd.notna(erw):
            e["est"] = {"eps": float(erw)}
        if pd.notna(ist):
            e["act"] = {"eps": float(ist)}
            if pd.notna(ueb):
                e["more"] = [f"Überraschung: {ueb:+.1f} %".replace(".", ",")]
        out.append(e)
    return out


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def quartalszahlen(tickers: tuple):
    with ThreadPoolExecutor(12) as ex:
        return sorted([e for liste in ex.map(_termine, tickers) for e in liste], key=lambda x: x["t"])


# ---------- Aufbereiten ----------
def sitzung(kurs: pd.Series, boerse):
    tage = sorted(set(kurs.index.date))
    heute = kurs[kurs.index.date == tage[-1]]
    davor = kurs[kurs.index.date == tage[-2]] if len(tage) > 1 else heute.iloc[:1]
    tz, auf, zu, pause = boerse
    z = ZoneInfo(tz)
    f = lambda t: minute(datetime.combine(tage[-1], t, z).astimezone(BERLIN))
    jetzt = datetime.now(BERLIN)
    offen = boerse is KRYPTO or (tage[-1] == jetzt.date() and f(auf) <= minute(jetzt) < f(zu))
    dom = [min(f(auf), minute(heute.index[0])), max(f(zu), minute(heute.index[-1]))]
    return {"heute": heute, "vortag": float(davor.iloc[-1]), "dom": dom, "pause": [f(pause[0]), f(pause[1])] if pause else None,
            "status": "live" if offen else "close", "start": heute.index[0], "ende_davor": davor.index[-1]}


def ereignisse(meldungen, sz, prefix, tr, maximal=6):
    """Nachrichten als Zeitstempel im Chart. Vorbörsliche Meldungen landen auf dem Handelsstart."""
    ev = {}
    passend = [n for n in meldungen if sz["ende_davor"] < n["zeit"] <= sz["heute"].index[-1] + timedelta(minutes=5)]
    for i, n in enumerate(passend[-maximal:]):
        vor = n["zeit"] < sz["start"]
        t = minute(sz["start"]) + 1 if vor else minute(n["zeit"])
        b = [html.escape(tr(n["text"]))] if n["text"] else []
        if vor:
            b.insert(0, f"Vor Handelsbeginn erschienen ({n['zeit']:%d.%m. %H:%M})")
        ev[f"{prefix}{i}"] = {"t": t, "place": html.escape(n["quelle"]), "h": html.escape(tr(n["titel"])), "b": b, "w": "",
                              "link": n["link"]}
    return ev


@st.cache_data(ttl=120, show_spinner="Lade Live-Kurse und übersetze Nachrichten …")
def live_daten():
    jetzt = datetime.now(BERLIN)
    aktien = sorted({t for _, a in BRANCHEN.values() for t in a} | set(LISTE))
    kurse = intraday_alle(tuple({v[0] for v in INDIZES.values()} | set(aktien)))
    news_tk = sorted({v[4] for v in INDIZES.values()} | set(aktien) | {etf for etf, _ in BRANCHEN.values()})
    news = nachrichten_alle(tuple(news_tk))

    # alle Texte vorab gemeinsam übersetzen
    texte = []
    for liste in news.values():
        for n in liste[-6:]:
            texte += [n["titel"], n["text"]]
    tr = deutsch(texte)

    live = {"now": minute(jetzt), "stand": f"{jetzt:%H:%M}", "idx": {}, "stocks": [], "ev": {}, "evfor": {}, "sec": {},
            "logos": {t: logo_urls(t) for t in FIRMEN}}
    for b, (t, name, cur, boerse, ntk) in INDIZES.items():
        if t not in kurse:
            continue
        sz = sitzung(kurse[t], boerse)
        h, v0, vix = sz["heute"], sz["vortag"], b == "vix"
        live["idx"][b] = {"name": name, "cur": cur, "prev": v0, "last": float(h.iloc[-1]), "dom": sz["dom"], "status": sz["status"],
                          "lunch": sz["pause"], "open": float(h.iloc[0]), "high": float(h.max()), "low": float(h.min()),
                          "s": [[minute(ts), round(float(x), 2) if vix else round((float(x) / v0 - 1) * 100, 4)] for ts, x in h.items()]}
        ev = ereignisse(news.get(ntk, []), sz, b, tr)
        live["ev"].update(ev)
        live["evfor"][b] = list(ev)

    sektor_von = {t: (sec, w) for sec, (_, a) in BRANCHEN.items() for t, w in a.items()}
    for t in aktien:
        if t not in kurse:
            continue
        sz = sitzung(kurse[t], boerse_von(t))
        h, v0 = sz["heute"], sz["vortag"]
        sec, w = sektor_von.get(t, (None, 0))
        i = bid(t)
        live["stocks"].append({"id": i, "tk": t, "name": FIRMEN.get(t, [t])[0], "cur": "EUR" if t.endswith(".DE") else "USD",
                               "last": float(h.iloc[-1]), "p": (float(h.iloc[-1]) / v0 - 1) * 100, "dom": sz["dom"],
                               "status": sz["status"], "sec": sec, "w": w, "list": 1 if t in LISTE else 0,
                               "s": [[minute(ts), round((float(x) / v0 - 1) * 100, 4)] for ts, x in h.items()]})
        ev = ereignisse(news.get(t, []), sz, i, tr, maximal=4)
        live["ev"].update(ev)
        live["evfor"][i] = list(ev)

    # Ø aller Märkte: die jüngsten Meldungen der großen Märkte
    welt = sorted((k for k in live["ev"] if k.rstrip("0123456789") in ("spx", "qqq", "dax", "nikkei", "hsi", "dow")),
                  key=lambda k: live["ev"][k]["t"])
    live["evfor"]["welt"] = welt[-8:]

    p_von = {s["tk"]: s["p"] for s in live["stocks"]}
    for sec, (etf, mitglieder) in BRANCHEN.items():
        werte = [(p_von[t], w) for t, w in mitglieder.items() if t in p_von]
        p = sum(a * w for a, w in werte) / sum(w for _, w in werte) if werte else 0
        meldungen = [{"h": html.escape(tr(n["titel"])), "b": html.escape(tr(n["text"]))[:260] if n["text"] else "",
                      "link": n["link"], "src": html.escape(n["quelle"])} for n in news.get(etf, [])[-4:][::-1]]
        live["sec"][sec] = {"p": p, "news": meldungen}

    live["er"] = quartalszahlen(tuple(QUARTALS_LISTE))
    live["foot"] = (f"Live-Daten von Yahoo Finance, bis ca. 15 Min. verzögert · Stand {jetzt:%d.%m.%Y, %H:%M} Uhr · "
                    "Nachrichten automatisch übersetzt · MSCI World = ETF URTH, FTSE All-World = ETF VT, S&amp;P 500 Tech = ETF XLK · "
                    "Seite neu laden für frische Kurse · Keine Anlageberatung")
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
components.html("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<style>:root{color-scheme:dark}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>"
                + seite.replace("/*__LIVE__*/null", daten, 1) + "</body></html>", height=1000, scrolling=True)
