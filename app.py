"""S&H Marktboard – Stocks and Holdings
Zeigt das Board (web/board.html) und füllt es mit Live-Daten von Yahoo Finance.
Nachrichten werden automatisch ins Deutsche übersetzt und als Kurzfassung direkt im Board gezeigt."""
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from deep_translator import GoogleTranslator, MyMemoryTranslator

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


# ---------- Übersetzung ins Deutsche (mehrere Wege, mit Zwischenspeicher) ----------
ENGLISCH = {"the", "and", "to", "of", "in", "is", "for", "on", "with", "as", "after", "its", "by", "from", "stock", "stocks",
            "shares", "says", "are", "will", "this", "that", "why", "how", "what", "today", "market", "investors"}


def englisch(t):
    return len(set(re.findall(r"[a-z']+", str(t).lower())) & ENGLISCH) >= 2


@st.cache_resource
def _uebersetzungen():
    return {}


def _glatt(t):
    return " ".join(str(t).split())[:500]


def _gtx(text):
    r = requests.get("https://translate.googleapis.com/translate_a/single",
                     params={"client": "gtx", "sl": "auto", "tl": "de", "dt": "t", "q": text}, timeout=12)
    r.raise_for_status()
    return "".join(seg[0] for seg in r.json()[0] if seg and seg[0])


def _eins(t):
    for weg in (lambda x: _gtx(x), lambda x: GoogleTranslator(source="auto", target="de").translate(x),
                lambda x: MyMemoryTranslator(source="en-GB", target="de-DE").translate(x)):
        try:
            aus = weg(t)
            if aus and not englisch(aus):
                return aus
        except Exception:
            continue
    return None


def _block(texte):
    try:
        teile = _gtx("\n".join(texte)).split("\n")
        if len(teile) == len(texte) and not any(englisch(x) for x in teile):
            return teile
    except Exception:
        pass
    return [_eins(t) for t in texte]


def deutsch(texte):
    """Übersetzt alle Texte. Rückgabe: Funktion, die zu jedem Text die deutsche Fassung liefert oder None."""
    speicher = _uebersetzungen()
    neu = [t for t in dict.fromkeys(_glatt(x) for x in texte if x) if t not in speicher]
    bloecke, akt, n = [], [], 0
    for t in neu:
        if akt and n + len(t) > 1500:
            bloecke.append(akt)
            akt, n = [], 0
        akt.append(t)
        n += len(t) + 1
    if akt:
        bloecke.append(akt)
    with ThreadPoolExecutor(4) as ex:
        for blk, erg in zip(bloecke, ex.map(_block, bloecke)):
            speicher.update(zip(blk, erg))

    def tr(x):
        if not x:
            return None
        g = _glatt(x)
        if g in speicher and speicher[g]:
            return speicher[g]
        return None if englisch(g) else g   # schon deutsch (z. B. deutsche Quellen)
    return tr


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
        tk = yf.Ticker(ticker)
        try:
            roh = tk.get_news(count=40, tab="news") or []
        except Exception:
            roh = tk.news or []
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
        out.append({"zeit": ts.tz_convert(BERLIN), "titel": titel, "text": (c.get("summary") or c.get("description") or "")[:400],
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
    v0 = float(davor.iloc[-1])
    return {"heute": heute, "vortag": v0, "pct": (heute / v0 - 1) * 100, "dom": dom,
            "pause": [f(pause[0]), f(pause[1])] if pause else None, "status": "live" if offen else "close",
            "start": heute.index[0], "ende_davor": davor.index[-1], "boerse": boerse}


def zahl_de(x, stellen=1, vorzeichen=True):
    s = f"{x:+,.{stellen}f}" if vorzeichen else f"{x:,.{stellen}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".").replace("-", "−")


def dauer(t0, t1):
    m = int((t1 - t0).total_seconds() // 60)
    return f"{m} Min." if m < 60 else f"{m // 60} Std." + (f" {m % 60} Min." if m % 60 else "")


def bewegungen(s: pd.Series, schwelle, maximal=4, fenster=24):
    """Die größten Kursbewegungen (Prozentpunkte) innerhalb von höchstens 2 Stunden, ohne Überlappung."""
    v = s.values.astype(float)
    n = len(v)
    belegt = np.zeros(n, bool)
    out = []
    for _ in range(maximal):
        best = None
        for i in range(1, n):
            for j in range(max(0, i - fenster), i):
                if belegt[j:i + 1].any():
                    continue
                d = v[i] - v[j]
                if best is None or abs(d) > abs(best[2]):
                    best = (j, i, d)
        if not best or abs(best[2]) < schwelle:
            break
        j, i, d = best
        belegt[j:i + 1] = True
        out.append((s.index[j], s.index[i], float(d)))
    return sorted(out)


def aenderung(serie, t0, t1):
    """Veränderung einer Vergleichsreihe im selben Zeitfenster, nur wenn sie dort Daten hat."""
    if serie is None or serie.empty or t0 < serie.index[0] - timedelta(minutes=10) or t0 > serie.index[-1]:
        return None
    a, b = serie.asof(t0), serie.asof(min(t1, serie.index[-1]))
    return None if pd.isna(a) or pd.isna(b) else float(b - a)


def zeitpunkt_grund(t0, boerse):
    m = minute(t0)
    if boerse is XETRA:
        if 540 <= m <= 570:
            return "Handelsstart in Frankfurt um 9:00 Uhr: Aufträge aus der Nacht werden ausgeführt."
        if 925 <= m <= 975:
            return "Mit dem US-Börsenstart um 15:30 Uhr kommt oft Bewegung in den deutschen Markt."
        if 865 <= m <= 890:
            return "Um 14:30 Uhr erscheinen üblicherweise wichtige US-Konjunkturdaten."
    elif boerse in (TOKIO, HK):
        if m <= minute(datetime.combine(t0.date(), boerse[1], ZoneInfo(boerse[0])).astimezone(BERLIN)) + 30:
            return "Erste halbe Stunde nach Handelsstart in Asien."
    else:
        if 865 <= m <= 890:
            return "Um 14:30 Uhr erscheinen üblicherweise wichtige US-Konjunkturdaten."
        if 925 <= m <= 975:
            return "Erste Handelsstunde nach dem US-Börsenstart um 15:30 Uhr, wenn besonders viele Aufträge ausgeführt werden."
        if 955 <= m <= 990:
            return "Um 16:00 Uhr kommen oft weitere US-Daten wie Stimmungs- oder Immobilienzahlen."
        if 1195 <= m <= 1230:
            return "Um 20:00 Uhr veröffentlicht die US-Notenbank an Zinstagen ihre Entscheidung."
        if 1230 <= m <= 1320:
            return "Letzte Handelsstunde in New York: Fonds passen zum Schluss ihre Positionen an."
    return None


def plane(name, t0, t1, d, eigene, markt, vergleiche, termine, boerse, prozent=True, ist_luecke=False, seit=None):
    """Sammelt alle Gründe für eine Bewegung, noch ohne Übersetzung."""
    vor = timedelta(minutes=150 if ist_luecke else 120)
    eigen = [n for n in eigene if (seit or t0 - vor) <= n["zeit"] <= t1 + timedelta(minutes=5)]
    allg = [n for n in markt if t0 - timedelta(minutes=90) <= n["zeit"] <= t1 + timedelta(minutes=5)]
    return {"name": name, "t0": t0, "t1": t1, "d": d, "eigen": eigen[-2:], "markt": allg[-1:], "vergleiche": vergleiche,
            "termine": [e for e in termine if t0 - timedelta(hours=20) <= datetime.fromtimestamp(e["t"] / 1000, BERLIN) <= t1],
            "boerse": boerse, "prozent": prozent, "luecke": ist_luecke}


def schreibe(p, tr, nr):
    """Macht aus dem Plan einen Zeitstempel mit deutscher Begründung."""
    d, b, ausloeser, link, quelle = p["d"], [], None, None, None
    verb = ("steigt" if d > 0 else "fällt")
    if p["luecke"]:
        titel = f"{p['name']} startet mit {zahl_de(d)} % {'Aufschlag' if d > 0 else 'Abschlag'}"
    else:
        titel = f"{p['name']} {verb} um {zahl_de(abs(d), vorzeichen=False)} % in {dauer(p['t0'], p['t1'])}"
    for n in p["eigen"]:
        de_t, de_x = tr(n["titel"]), tr(n["text"])
        if not de_t:
            continue
        b.append(f"<b>{n['zeit']:%H:%M} Uhr, {html.escape(n['quelle'])}:</b> {html.escape(de_t)}" + (f" – {html.escape(de_x[:200])}" if de_x else ""))
        ausloeser = ausloeser or html.escape(de_t)
        link, quelle = n["link"], n["quelle"]
    for e in p["termine"]:
        wann = datetime.fromtimestamp(e["t"] / 1000, BERLIN)
        if "act" in e and "est" in e:
            ueber = e["act"]["eps"] >= e["est"]["eps"]
            txt = (f"Quartalszahlen ({wann:%d.%m. %H:%M} Uhr): Gewinn je Aktie {zahl_de(e['act']['eps'], 2, False)} bei erwarteten "
                   f"{zahl_de(e['est']['eps'], 2, False)} – {'über' if ueber else 'unter'} den Erwartungen.")
        else:
            txt = f"Quartalszahlen am {wann:%d.%m. um %H:%M} Uhr."
        b.append(txt)
        ausloeser = ausloeser or txt
    for vname, c, art in p["vergleiche"]:
        if c is None:
            continue
        if art == "vix":
            b.append(f"VIX {('steigt' if c > 0 else 'fällt')} um {zahl_de(abs(c), 1, False)} Punkte – "
                     f"{'Anleger werden nervöser.' if c > 0 else 'Anleger beruhigen sich.'}")
            continue
        if p["name"] == "Ø aller Märkte":
            b.append(f"Treiber: {vname} {zahl_de(c)} % im selben Zeitraum.")
            ausloeser = ausloeser or f"Getrieben vor allem von {vname} ({zahl_de(c)} %)."
        elif abs(c) >= 0.35 * abs(d) and c * d > 0:
            b.append(f"Gleichzeitig {vname} {zahl_de(c)} % – die Bewegung läuft mit dem Gesamtmarkt.")
            ausloeser = ausloeser or f"Breite Marktbewegung: {vname} {zahl_de(c)} % im selben Zeitraum."
        elif abs(c) < 0.2 * abs(d):
            b.append(f"{vname} im selben Zeitraum kaum verändert ({zahl_de(c)} %) – die Bewegung ist eigenständig.")
        elif c * d < 0:
            b.append(f"{vname} läuft entgegengesetzt ({zahl_de(c)} %).")
    eigene_titel = {n["titel"] for n in p["eigen"]}
    for n in p["markt"]:
        de_t = tr(n["titel"]) if n["titel"] not in eigene_titel else None
        if de_t:
            b.append(f"<b>Marktmeldung {n['zeit']:%H:%M} Uhr, {html.escape(n['quelle'])}:</b> {html.escape(de_t)}")
            ausloeser = ausloeser or html.escape(de_t)
            link, quelle = link or n["link"], quelle or n["quelle"]
    zg = zeitpunkt_grund(p["t0"], p["boerse"])
    if zg:
        b.append(zg)
        ausloeser = ausloeser or zg
    if p["luecke"]:
        b.insert(0, "Die Lücke entstand zwischen dem letzten Schlusskurs und dem Handelsstart.")
    if not ausloeser:
        ausloeser = "Kein einzelner Auslöser zu finden – vermutlich Gewinnmitnahmen oder normale Schwankung."
    t = minute(p["t0"])
    return f"m{nr}", {"t": t, "dir": 1 if d > 0 else -1, "place": "Kursbewegung", "h": titel, "b": b,
                      "w": ausloeser, "link": link, "src": html.escape(quelle) if quelle else None}


def plaene_fuer(name, sz, ticker, eigene, markt, vergleich_reihen, termine, schwelle_min, prozent=True):
    s = sz["pct"] if prozent else sz["heute"]
    spanne = float(s.max() - s.min()) if len(s) else 0
    schwelle = max(schwelle_min, 0.28 * spanne)
    plaene = []
    erster = float(s.iloc[0]) if prozent else 0.0
    if prozent and abs(erster) >= schwelle:
        plaene.append(plane(name, sz["start"], sz["start"], erster, eigene, markt, [], termine, sz["boerse"], ist_luecke=True, seit=sz["ende_davor"]))
    for t0, t1, d in bewegungen(s, schwelle):
        if prozent:
            vgl = [(vn, aenderung(vr, t0, t1), art) for vn, vr, art in vergleich_reihen]
        else:
            vgl = []
        plaene.append(plane(name, t0, t1, d if prozent else (float(s.asof(t1)) / float(s.asof(t0)) - 1) * 100,
                            eigene, markt, vgl, termine, sz["boerse"]))
    return plaene


@st.cache_data(ttl=120, show_spinner="Lade Live-Kurse und übersetze Nachrichten …")
def live_daten():
    jetzt = datetime.now(BERLIN)
    aktien = sorted({t for _, a in BRANCHEN.values() for t in a} | set(LISTE))
    kurse = intraday_alle(tuple({v[0] for v in INDIZES.values()} | set(aktien)))
    news_tk = sorted({v[4] for v in INDIZES.values()} | set(aktien) | {etf for etf, _ in BRANCHEN.values()} | {"SPY", "QQQ"})
    news = nachrichten_alle(tuple(news_tk))
    termine = quartalszahlen(tuple(QUARTALS_LISTE))
    termine_von = {}
    for e in termine:
        termine_von.setdefault(e["ytk"], []).append(e)

    sitzungen = {t: sitzung(kurse[t], boerse_von(t) if t not in {v[0] for v in INDIZES.values()} else
                            next(v[3] for v in INDIZES.values() if v[0] == t)) for t in kurse}
    pct = {t: sz["pct"] for t, sz in sitzungen.items()}
    vix_lvl = sitzungen["^VIX"]["heute"] if "^VIX" in sitzungen else None
    REIHE = lambda name, t, art="pct": (name, (vix_lvl if art == "vix" else pct.get(t)), art)
    US_VGL = [REIHE("S&P 500", "^GSPC"), REIHE("Nasdaq-100 (QQQ)", "QQQ")]
    VGL = {"spx": [REIHE("Nasdaq-100 (QQQ)", "QQQ"), REIHE("VIX", "^VIX", "vix")], "qqq": [REIHE("S&P 500", "^GSPC"), REIHE("VIX", "^VIX", "vix")],
           "dow": [REIHE("S&P 500", "^GSPC")], "spit": [REIHE("Nasdaq-100 (QQQ)", "QQQ")], "msci": [REIHE("S&P 500", "^GSPC")],
           "ftseaw": [REIHE("S&P 500", "^GSPC")], "dax": [REIHE("S&P 500", "^GSPC"), REIHE("Nasdaq-100 (QQQ)", "QQQ")],
           "nikkei": [REIHE("Hang Seng", "^HSI")], "hsi": [REIHE("Nikkei 225", "^N225")], "vix": [REIHE("S&P 500", "^GSPC")]}
    MARKT = {"dax": news.get("^GDAXI", []) + news.get("SPY", []), "nikkei": news.get("^N225", []), "hsi": news.get("^HSI", [])}
    us_markt = sorted(news.get("SPY", []) + news.get("QQQ", []), key=lambda x: x["zeit"])

    plaene = {}   # Chart-id -> Liste von Plänen
    live = {"now": minute(jetzt), "stand": f"{jetzt:%H:%M}", "idx": {}, "stocks": [], "ev": {}, "evfor": {}, "sec": {},
            "logos": {t: logo_urls(t) for t in FIRMEN}, "er": termine}
    for b, (t, name, cur, boerse, ntk) in INDIZES.items():
        if t not in sitzungen:
            continue
        sz = sitzungen[t]
        h, v0, vix = sz["heute"], sz["vortag"], b == "vix"
        live["idx"][b] = {"name": name, "cur": cur, "prev": v0, "last": float(h.iloc[-1]), "dom": sz["dom"], "status": sz["status"],
                          "lunch": sz["pause"], "open": float(h.iloc[0]), "high": float(h.max()), "low": float(h.min()),
                          "s": [[minute(ts), round(float(x), 2) if vix else round(float(y), 4)] for (ts, x), y in zip(h.items(), sz["pct"].values)]}
        eigene = news.get(ntk, [])
        markt = MARKT.get(b, us_markt)
        plaene[b] = plaene_fuer(name, sz, t, eigene, markt if markt is not eigene else [], VGL.get(b, []), [],
                                5.0 if vix else 0.35, prozent=True)

    sektor_von = {t: (sec, w) for sec, (_, a) in BRANCHEN.items() for t, w in a.items()}
    for t in aktien:
        if t not in sitzungen:
            continue
        sz = sitzungen[t]
        h = sz["heute"]
        sec, w = sektor_von.get(t, (None, 0))
        i = bid(t)
        name = FIRMEN.get(t, [t])[0]
        live["stocks"].append({"id": i, "tk": t, "name": name, "cur": "EUR" if t.endswith(".DE") else "USD",
                               "last": float(h.iloc[-1]), "p": float(sz["pct"].iloc[-1]), "dom": sz["dom"], "status": sz["status"],
                               "sec": sec, "w": w, "list": 1 if t in LISTE else 0,
                               "s": [[minute(ts), round(float(y), 4)] for ts, y in sz["pct"].items()]})
        de = t.endswith(".DE")
        vgl = [REIHE("DAX", "^GDAXI")] if de else US_VGL
        markt = news.get("^GDAXI", []) if de else us_markt
        plaene[i] = plaene_fuer(name, sz, t, news.get(t, []), markt, vgl, termine_von.get(t, []), 1.0 if t != "BTC-USD" else 1.2)

    # Ø aller Märkte: Durchschnitt wie im Board, Bewegungen mit den treibenden Indizes als Grund
    mitglieder = [b for b in live["idx"] if b != "vix"]
    if mitglieder:
        datum = max(sitzungen[INDIZES[b][0]]["heute"].index[-1].date() for b in mitglieder)
        raster = pd.date_range(datetime.combine(datum, time(0, 0), BERLIN), min(jetzt, datetime.combine(datum, time(23, 55), BERLIN)), freq="5min")
        spalten = {}
        for b in mitglieder:
            s = pct[INDIZES[b][0]]
            s = s if s.index[-1].date() == datum else pd.Series(dtype=float)
            spalten[INDIZES[b][1]] = s.reindex(s.index.union(raster)).ffill().reindex(raster).fillna(0)
        df = pd.DataFrame(spalten)
        welt = df.mean(axis=1)
        wp = []
        sp = float(welt.max() - welt.min())
        for t0, t1, d in bewegungen(welt, max(0.2, 0.28 * sp)):
            treiber = sorted(((n, float(df[n].asof(t1) - df[n].asof(t0))) for n in df.columns), key=lambda x: -abs(x[1]))
            vgl = [(n, c, "pct") for n, c in treiber[:3] if abs(c) >= 0.15]
            region = next((b for b in mitglieder if INDIZES[b][1] == (vgl[0][0] if vgl else "")), "spx")
            eig = news.get(INDIZES[region][4], []) + (us_markt if INDIZES[region][3] is NY else [])
            p = plane("Ø aller Märkte", t0, t1, d, sorted(eig, key=lambda x: x["zeit"]), [], vgl, [], INDIZES[region][3])
            wp.append(p)
        plaene["welt"] = wp

    # alles Nötige auf einen Schlag übersetzen
    texte = []
    for liste in plaene.values():
        for p in liste:
            for n in p["eigen"] + p["markt"]:
                texte += [n["titel"], n["text"]]
    for etf, _ in BRANCHEN.values():
        for n in news.get(etf, [])[-8:]:
            texte += [n["titel"], n["text"]]
    tr = deutsch(texte)

    nr = 0
    for cid, liste in plaene.items():
        keys = []
        for p in liste:
            k, ev = schreibe(p, tr, nr)
            nr += 1
            live["ev"][k] = ev
            keys.append(k)
        live["evfor"][cid] = keys

    p_von = {s["tk"]: s["p"] for s in live["stocks"]}
    for sec, (etf, mitgl) in BRANCHEN.items():
        werte = [(p_von[t], w) for t, w in mitgl.items() if t in p_von]
        p = sum(a * w for a, w in werte) / sum(w for _, w in werte) if werte else 0
        meldungen = []
        for n in news.get(etf, [])[::-1]:
            h_de = tr(n["titel"])
            if not h_de:
                continue
            x_de = tr(n["text"]) if n["text"] else ""
            meldungen.append({"h": html.escape(h_de), "b": html.escape(x_de or "")[:260], "link": n["link"], "src": html.escape(n["quelle"])})
            if len(meldungen) == 4:
                break
        live["sec"][sec] = {"p": p, "news": meldungen}

    live["foot"] = (f"Live-Daten von Yahoo Finance, bis ca. 15 Min. verzögert · Stand {jetzt:%d.%m.%Y, %H:%M} Uhr · "
                    "Zeitstempel markieren die großen Kursbewegungen mit ihren wahrscheinlichen Gründen · Nachrichten automatisch übersetzt · "
                    "MSCI World = ETF URTH, FTSE All-World = ETF VT, S&amp;P 500 Tech = ETF XLK · Seite neu laden für frische Kurse · "
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
components.html("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<style>:root{color-scheme:dark}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>"
                + seite.replace("/*__LIVE__*/null", daten, 1) + "</body></html>", height=1000, scrolling=True)
