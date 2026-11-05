"""S&H Marktboard – Stocks and Holdings
Live-Dashboard: Quartalszahlen-Leiste, Börsen-Status, Index-Charts mit Nachrichten-Zeitstempeln,
VIX, Tagesbilanz, Unternehmen und Branchen-Heatmap. Daten: Yahoo Finance über yfinance."""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="S&H Marktboard", page_icon="logo.png", layout="wide")

BERLIN = ZoneInfo("Europe/Berlin")
GOLD, BLUE = "#E3C47F", "#6A9CCF"
BG, PANEL, FG, MUTED = "#07111B", "#0D1A28", "#EEF1F4", "#8892A0"

# ---------- Was angezeigt wird ----------
INDIZES = {  # Name: (Yahoo-Ticker, Ticker für Nachrichten)
    "MSCI World": ("URTH", "URTH"),
    "S&P 500": ("^GSPC", "SPY"),
    "S&P 500 Tech": ("XLK", "XLK"),
    "DAX": ("^GDAXI", "^GDAXI"),
    "Dow Jones": ("^DJI", "DIA"),
    "QQQ": ("QQQ", "QQQ"),
    "FTSE All-World": ("VT", "VT"),
    "Nikkei 225": ("^N225", "^N225"),
    "Hang Seng": ("^HSI", "^HSI"),
}
VIX = "^VIX"
UNTERNEHMEN = {"Siemens": "SIE.DE", "Deutsche Telekom": "DTE.DE", "Nike": "NKE", "Bitcoin": "BTC-USD",
               "Allianz": "ALV.DE", "PepsiCo": "PEP", "Coca-Cola": "KO"}
BRANCHEN = {  # Branche: (Sektor-ETF für Nachrichten, {Aktie: (Ticker, Gewicht in Mrd. $)})
    "Technologie": ("XLK", {"Apple": ("AAPL", 4000), "Microsoft": ("MSFT", 3800), "Nvidia": ("NVDA", 4200),
                            "Broadcom": ("AVGO", 1500), "Oracle": ("ORCL", 600)}),
    "Kommunikation": ("XLC", {"Alphabet": ("GOOGL", 3000), "Meta": ("META", 1600), "Netflix": ("NFLX", 450)}),
    "Nicht-Basiskonsum": ("XLY", {"Amazon": ("AMZN", 2500), "Tesla": ("TSLA", 1200), "Home Depot": ("HD", 380)}),
    "Finanzen": ("XLF", {"JPMorgan": ("JPM", 800), "Visa": ("V", 650), "Berkshire": ("BRK-B", 1000)}),
    "Gesundheit": ("XLV", {"Eli Lilly": ("LLY", 900), "UnitedHealth": ("UNH", 350), "J&J": ("JNJ", 420)}),
    "Industrie": ("XLI", {"Caterpillar": ("CAT", 260), "GE Aerospace": ("GE", 300)}),
    "Basiskonsum": ("XLP", {"Walmart": ("WMT", 800), "Coca-Cola": ("KO", 300), "PepsiCo": ("PEP", 200)}),
    "Energie": ("XLE", {"Exxon": ("XOM", 480), "Chevron": ("CVX", 300)}),
    "Versorger": ("XLU", {"NextEra": ("NEE", 160)}),
    "Immobilien": ("XLRE", {"Prologis": ("PLD", 110)}),
    "Materialien": ("XLB", {"Linde": ("LIN", 220)}),
}
QUARTALS_LISTE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "ABNB", "QCOM", "NKE", "PEP",
                  "KO", "JPM", "WMT", "DIS", "SAP.DE", "SIE.DE", "DTE.DE", "ALV.DE", "BAS.DE", "MBG.DE"]
BOERSEN = [("Tokio", "Asia/Tokyo", time(9, 0), time(15, 30)), ("Hongkong", "Asia/Hong_Kong", time(9, 30), time(16, 0)),
           ("Frankfurt", "Europe/Berlin", time(9, 0), time(17, 30)), ("New York", "America/New_York", time(9, 30), time(16, 0))]


# ---------- Daten ----------
@st.cache_data(ttl=60, show_spinner=False)
def intraday(ticker: str):
    """Letzte Handelssitzung in 5-Minuten-Schritten (Berliner Zeit) und Schlusskurs davor."""
    try:
        d = yf.Ticker(ticker).history(period="5d", interval="5m")
    except Exception:
        return None
    if d is None or d.empty:
        return None
    d.index = d.index.tz_convert(BERLIN)
    tage = sorted(set(d.index.date))
    heute = d[d.index.date == tage[-1]]["Close"]
    vortag = d[d.index.date == tage[-2]]["Close"].iloc[-1] if len(tage) > 1 else heute.iloc[0]
    return {"kurve": heute, "vortag": float(vortag), "letzter": float(heute.iloc[-1]),
            "pct": (float(heute.iloc[-1]) / float(vortag) - 1) * 100, "datum": tage[-1]}


@st.cache_data(ttl=300, show_spinner=False)
def tagesaenderung(tickers: tuple):
    """Tagesveränderung in % für viele Aktien auf einmal (für die Heatmap)."""
    d = yf.download(list(tickers), period="5d", interval="1d", progress=False, group_by="ticker", auto_adjust=True)
    out = {}
    for t in tickers:
        try:
            c = d[t]["Close"].dropna()
            out[t] = (float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100
        except Exception:
            out[t] = None
    return out


@st.cache_data(ttl=600, show_spinner=False)
def nachrichten(ticker: str):
    """Schlagzeilen mit Zeitpunkt. Unterstützt altes und neues yfinance-Format."""
    try:
        roh = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for n in roh:
        c = n.get("content", n)
        titel = c.get("title")
        zeit = c.get("pubDate") or c.get("providerPublishTime")
        if not titel or not zeit:
            continue
        ts = pd.to_datetime(zeit, unit="s", utc=True) if isinstance(zeit, (int, float)) else pd.to_datetime(zeit, utc=True)
        link = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else c.get("link")
        quelle = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher")
        out.append({"zeit": ts.tz_convert(BERLIN), "titel": titel, "link": link, "quelle": quelle or ""})
    return sorted(out, key=lambda x: x["zeit"])


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def quartalszahlen(tickers: tuple):
    """Berichtstermine der letzten 3 und nächsten 10 Tage mit EPS-Erwartung und Ist."""
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
                out.append({"ticker": t, "name": name, "zeit": z, "erw": row.get("EPS Estimate"),
                            "ist": row.get("Reported EPS"), "ueberr": row.get("Surprise(%)")})
    return sorted(out, key=lambda x: x["zeit"])


# ---------- Hilfen ----------
def farbe(v):
    return GOLD if (v or 0) >= 0 else BLUE


def pct(v, stellen=2):
    if v is None or pd.isna(v):
        return "–"
    return f"{'+' if v > 0 else '−' if v < 0 else '±'}{abs(v):,.{stellen}f} %".replace(",", "X").replace(".", ",").replace("X", ".")


def zahl(v, stellen=2):
    return f"{v:,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def boersen_status():
    jetzt = datetime.now(BERLIN)
    teile = []
    for name, tz, auf, zu in BOERSEN:
        lokal = jetzt.astimezone(ZoneInfo(tz))
        werktag = lokal.weekday() < 5
        if werktag and auf <= lokal.time() < zu:
            schluss = datetime.combine(lokal.date(), zu, ZoneInfo(tz)).astimezone(BERLIN)
            teile.append(f"<span class='mk open'><i></i><b>{name}</b> offen bis {schluss:%H:%M}</span>")
            continue
        tag = lokal.date() if (werktag and lokal.time() < auf) else lokal.date() + timedelta(days=1)
        while tag.weekday() >= 5:
            tag += timedelta(days=1)
        oeffnet = datetime.combine(tag, auf, ZoneInfo(tz)).astimezone(BERLIN)
        wann = "" if oeffnet.date() == jetzt.date() else "morgen " if oeffnet.date() == jetzt.date() + timedelta(days=1) \
            else ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][oeffnet.weekday()] + " "
        teile.append(f"<span class='mk'><i></i><b>{name}</b> öffnet {wann}{oeffnet:%H:%M}</span>")
    return "".join(teile)


def tageskurve(kurven: dict):
    """Ø Markt: Durchschnitt der Tagesveränderungen auf einem gemeinsamen 5-Minuten-Raster (Berliner Zeit)."""
    datum = max(k["datum"] for k in kurven.values())
    start = datetime.combine(datum, time(0, 0), BERLIN)
    ende = min(datetime.now(BERLIN), start + timedelta(days=1))
    raster = pd.date_range(start, ende, freq="5min")
    spalten = {}
    for name, k in kurven.items():
        s = (k["kurve"] / k["vortag"] - 1) * 100
        if k["datum"] != datum:
            s = pd.Series(dtype=float)
        spalten[name] = s.reindex(s.index.union(raster)).ffill().reindex(raster).fillna(0)
    df = pd.DataFrame(spalten)
    return df.mean(axis=1), df


def chart(y_pct: pd.Series, basis_text: str, events: list, extra: pd.DataFrame = None, werte=None):
    """Kurve in Gold (über Vortag) und Blau (unter Vortag) mit Glow und Nachrichten-Zeitstempeln."""
    fig = go.Figure()
    if extra is not None:
        for name in extra.columns:
            s = extra[name]
            fig.add_scatter(x=s.index, y=s.values, mode="lines", name=name, line=dict(width=1.6, color=farbe(s.iloc[-1])),
                            opacity=0.45, hovertemplate=f"{name}: %{{y:.2f}} %<extra></extra>")
    oben, unten = y_pct.clip(lower=0), y_pct.clip(upper=0)
    fig.add_scatter(x=y_pct.index, y=[0] * len(y_pct), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=oben.index, y=oben.values, fill="tonexty", mode="lines", line=dict(width=0),
                    fillcolor="rgba(227,196,127,0.22)", showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=y_pct.index, y=[0] * len(y_pct), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=unten.index, y=unten.values, fill="tonexty", mode="lines", line=dict(width=0),
                    fillcolor="rgba(106,156,207,0.22)", showlegend=False, hoverinfo="skip")
    c = farbe(y_pct.iloc[-1])
    fig.add_scatter(x=y_pct.index, y=y_pct.values, mode="lines", line=dict(width=12, color=c), opacity=0.18,
                    showlegend=False, hoverinfo="skip")
    hover = "%{x|%H:%M} · %{y:+.2f} %"
    if werte is not None:
        fig.add_scatter(x=y_pct.index, y=y_pct.values, mode="lines", line=dict(width=3.6, color=c), showlegend=False,
                        customdata=werte.values, hovertemplate="%{x|%H:%M} · %{customdata:,.2f} (%{y:+.2f} %)<extra></extra>")
    else:
        fig.add_scatter(x=y_pct.index, y=y_pct.values, mode="lines", line=dict(width=3.6, color=c), showlegend=False,
                        hovertemplate=hover + "<extra></extra>")
    # Nachrichten-Zeitstempel: Stiel vom Kurs nach oben, Marke mit Uhrzeit
    if events:
        top = max(y_pct.max(), 0) + (y_pct.max() - y_pct.min() + 0.2) * 0.25
        xs, ys, texte = [], [], []
        for e in events:
            if e["zeit"] < y_pct.index[0] or e["zeit"] > y_pct.index[-1]:
                continue
            v = float(y_pct.asof(e["zeit"]))
            spaeter = float(y_pct.asof(e["zeit"] + timedelta(minutes=30)))
            fig.add_shape(type="line", x0=e["zeit"], x1=e["zeit"], y0=v, y1=top, line=dict(color="rgba(238,241,244,0.25)", width=1))
            xs.append(e["zeit"]); ys.append(top)
            texte.append(f"<b>{e['zeit']:%H:%M} · {e['quelle']}</b><br>{e['titel'][:90]}<br>"
                         f"Bewegung 30 Min danach: {spaeter - v:+.2f} Prozentpunkte")
        fig.add_scatter(x=xs, y=ys, mode="markers+text", text=[x.strftime("%H:%M") for x in xs], textposition="top center",
                        textfont=dict(size=10, color=GOLD), marker=dict(size=11, color=PANEL, line=dict(color=GOLD, width=2)),
                        hovertext=texte, hoverinfo="text", showlegend=False)
    fig.add_hline(y=0, line=dict(color="rgba(238,241,244,0.35)", dash="dot"), annotation_text=basis_text,
                  annotation_position="bottom right", annotation_font_color=MUTED)
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=FG), hovermode="closest", showlegend=False,
                      hoverlabel=dict(bgcolor=BG, bordercolor="#334", font_color=FG),
                      xaxis=dict(showgrid=False, tickformat="%H:%M", color=MUTED),
                      yaxis=dict(gridcolor="rgba(238,241,244,0.06)", ticksuffix=" %", color=MUTED, zeroline=False))
    return fig


# ---------- Aussehen ----------
st.markdown(f"""<style>
.stApp{{background:radial-gradient(1100px 600px at 85% -10%,rgba(106,156,207,.18),transparent 60%),{BG}}}
.block-container{{padding-top:1.2rem;max-width:1400px}}
.mk{{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;margin:0 6px 6px 0;border:1px solid rgba(238,241,244,.1);
  border-radius:99px;font-size:12px;color:#B7C0CA}}
.mk b{{color:{FG};font-weight:600}} .mk i{{width:7px;height:7px;border-radius:50%;background:#59626E}}
.mk.open{{border-color:rgba(227,196,127,.4)}} .mk.open i{{background:{GOLD};box-shadow:0 0 8px {GOLD}}}
.big{{font-size:52px;font-weight:600;letter-spacing:-.03em;line-height:1}}
.pill{{display:inline-block;font-weight:600;padding:3px 11px;border-radius:99px;margin-left:10px;font-size:15px}}
.zeile{{display:flex;justify-content:space-between;padding:5px 2px;border-bottom:1px solid rgba(238,241,244,.06);font-size:14px}}
.lv td{{padding:3px 8px;font-size:12.5px;color:{MUTED}}} .lv tr.on td{{color:{FG};background:rgba(227,196,127,.14)}}
</style>""", unsafe_allow_html=True)


# ---------- App ----------
@st.fragment(run_every="60s")
def board():
    jetzt = datetime.now(BERLIN)
    kopf_l, kopf_r = st.columns([5, 1])
    with kopf_l:
        st.markdown(boersen_status(), unsafe_allow_html=True)
    vix = intraday(VIX)
    with kopf_r:
        if vix:
            st.markdown(f"<div style='text-align:right'><span class='mk'><b>VIX {zahl(vix['letzter'])}</b>"
                        f"<span style='color:{farbe(vix['pct'])}'>{pct(vix['pct'], 0)}</span></span></div>", unsafe_allow_html=True)

    # Quartalszahlen-Leiste: Jetzt in der Mitte
    berichte = quartalszahlen(tuple(QUARTALS_LISTE))
    if berichte:
        fig = go.Figure()
        for b in berichte:
            vorbei = b["zeit"] <= jetzt and pd.notna(b["ist"])
            schlag = vorbei and pd.notna(b["erw"]) and b["ist"] >= b["erw"]
            col = (GOLD if schlag else BLUE) if vorbei else "#B7C0CA"
            info = f"<b>{b['name']}</b> ({b['ticker']})<br>{b['zeit']:%a %d.%m. %H:%M}<br>EPS erw.: {b['erw'] if pd.notna(b['erw']) else '–'}"
            if vorbei:
                info += f"<br>EPS ist: {b['ist']}  ({pct(b['ueberr'], 1)} Überraschung)"
            fig.add_scatter(x=[b["zeit"]], y=[0], mode="markers+text", text=[b["ticker"].split(".")[0]], textposition="top center",
                            textfont=dict(size=11, color=FG), marker=dict(size=16, color=PANEL, line=dict(color=col, width=3)),
                            hovertext=info, hoverinfo="text", showlegend=False)
        fig.add_vline(x=jetzt, line=dict(color=GOLD, dash="dot"))
        fig.add_annotation(x=jetzt, y=-0.9, text=f"Jetzt {jetzt:%H:%M}", showarrow=False, font=dict(color=BG, size=11), bgcolor=GOLD)
        fig.update_layout(height=120, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          xaxis=dict(range=[jetzt - timedelta(hours=36), jetzt + timedelta(hours=36)], showgrid=False,
                                     tickformat="%a %H:%M", color=MUTED),
                          yaxis=dict(visible=False, range=[-1.2, 1.2]), dragmode="pan")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        naechste = [b for b in berichte if abs((b["zeit"] - jetzt).total_seconds()) < 36 * 3600]
        gruppen = {}
        for b in naechste:
            gruppen.setdefault(b["zeit"].strftime("%a %d.%m. %H:%M"), []).append(b)
        if gruppen:
            spalten = st.columns(min(6, len(gruppen)))
            for sp, (wann, liste) in zip(spalten, list(gruppen.items())[:6]):
                with sp.popover(f"{wann} · {len(liste)} Bericht{'e' if len(liste) > 1 else ''}", use_container_width=True):
                    for b in liste:
                        st.markdown(f"**{b['name']}** ({b['ticker']})")
                        st.write(f"EPS erwartet: {b['erw'] if pd.notna(b['erw']) else '–'}")
                        if b["zeit"] <= jetzt:
                            st.write(f"EPS ist: {b['ist'] if pd.notna(b['ist']) else 'folgt'}"
                                     + (f" · Überraschung {pct(b['ueberr'], 1)}" if pd.notna(b['ueberr']) else ""))

    # Daten der Indizes
    kurven = {n: k for n, (t, _) in INDIZES.items() if (k := intraday(t))}
    links, rechts = st.columns([2.2, 1], gap="large")
    with links:
        auswahl = st.segmented_control("Chart", ["Ø Markt", *INDIZES, "VIX", *UNTERNEHMEN], default="Ø Markt",
                                       label_visibility="collapsed") or "Ø Markt"
        if auswahl == "Ø Markt" and kurven:
            mittel, einzeln = tageskurve(kurven)
            ev = []
            for t in ("SPY", "QQQ", "^GDAXI"):
                ev += nachrichten(t)
            wert, fig = mittel.iloc[-1], chart(mittel, "Vortag", ev[-12:], extra=einzeln)
            st.markdown(f"<div class='big'>{pct(wert)}<span class='pill' style='color:{farbe(wert)};border:1px solid {farbe(wert)}'>"
                        f"Ø aus {len(kurven)} Indizes</span></div>", unsafe_allow_html=True)
        else:
            ticker = (INDIZES.get(auswahl) or (VIX, VIX))[0] if auswahl not in UNTERNEHMEN else UNTERNEHMEN[auswahl]
            news_t = (INDIZES.get(auswahl) or (None, ticker))[1] if auswahl not in UNTERNEHMEN else ticker
            k = intraday(ticker)
            if not k:
                st.warning("Für diesen Wert kommen gerade keine Daten.")
                return
            y = (k["kurve"] / k["vortag"] - 1) * 100
            fig = chart(y, f"Vortag {zahl(k['vortag'])}", nachrichten(news_t)[-10:], werte=k["kurve"])
            st.markdown(f"<div class='big'>{zahl(k['letzter'])}<span class='pill' style='color:{farbe(k['pct'])};"
                        f"border:1px solid {farbe(k['pct'])}'>{pct(k['pct'])}</span></div>", unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.caption("Gold = über Vortag · Blau = unter Vortag · Zeitstempel antippen oder darüberfahren für die Nachricht")

        st.subheader("Unternehmen")
        sp = st.columns(4)
        for i, (name, t) in enumerate(UNTERNEHMEN.items()):
            k = intraday(t)
            if k:
                sp[i % 4].metric(name, zahl(k["letzter"], 0 if k["letzter"] > 10000 else 2), pct(k["pct"]))

    with rechts:
        if vix:
            st.subheader("VIX · Angstbarometer")
            g = go.Figure(go.Indicator(mode="gauge+number+delta", value=vix["letzter"],
                                       delta=dict(reference=vix["vortag"], relative=True, valueformat=".1%",
                                                  increasing=dict(color=GOLD), decreasing=dict(color=BLUE)),
                                       gauge=dict(axis=dict(range=[10, 40], tickcolor=MUTED), bar=dict(color=farbe(vix["pct"])),
                                                  bgcolor=PANEL, borderwidth=0,
                                                  steps=[dict(range=[10, 15], color="#13222F"), dict(range=[15, 20], color="#172938"),
                                                         dict(range=[20, 30], color="#1C3142"), dict(range=[30, 40], color="#22394D")])))
            g.update_layout(height=190, margin=dict(l=20, r=20, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", font=dict(color=FG))
            st.plotly_chart(g, use_container_width=True, config={"displayModeBar": False})
            v = vix["letzter"]
            stufe = 0 if v < 15 else 1 if v < 20 else 2 if v < 30 else 3
            reihen = [("unter 15", "ruhig"), ("15 – 20", "normal"), ("20 – 30", "nervös"), ("über 30", "Panik")]
            st.markdown("<table class='lv'>" + "".join(f"<tr class='{'on' if i == stufe else ''}'><td>{a}</td><td>{b}</td></tr>"
                                                       for i, (a, b) in enumerate(reihen)) + "</table>", unsafe_allow_html=True)
        st.subheader("Tagesbilanz")
        for name, k in sorted(kurven.items(), key=lambda x: -x[1]["pct"]):
            st.markdown(f"<div class='zeile'><span>{name}</span><b style='color:{farbe(k['pct'])}'>{pct(k['pct'])}</b></div>",
                        unsafe_allow_html=True)

    # Branchen-Heatmap
    st.subheader("Branchen")
    alle = tuple(t for _, (_, a) in BRANCHEN.items() for (t, _) in a.values())
    aend = tagesaenderung(alle)
    ids, eltern, groesse, farbwert, texte = [], [], [], [], []
    for br, (_, aktien) in BRANCHEN.items():
        werte = [(aend.get(t), w) for t, w in aktien.values() if aend.get(t) is not None]
        mittel = sum(a * w for a, w in werte) / sum(w for _, w in werte) if werte else 0
        ids.append(br); eltern.append(""); groesse.append(0); farbwert.append(mittel); texte.append(pct(mittel, 1))
        for name, (t, w) in aktien.items():
            ids.append(f"{br}/{name}"); eltern.append(br); groesse.append(w)
            farbwert.append(aend.get(t) or 0); texte.append(pct(aend.get(t)))
    hm = go.Figure(go.Treemap(ids=ids, labels=[i.split("/")[-1] for i in ids], parents=eltern, values=groesse, branchvalues="remainder",
                              text=texte, texttemplate="<b>%{label}</b><br>%{text}", hovertemplate="%{label}: %{text}<extra></extra>",
                              marker=dict(colors=farbwert, cmid=0, cmin=-5, cmax=5, line=dict(color=BG, width=2),
                                          colorscale=[[0, BLUE], [0.5, "#1A2B3C"], [1, GOLD]])))
    hm.update_layout(height=480, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", font=dict(color=FG))
    st.plotly_chart(hm, use_container_width=True, config={"displayModeBar": False})
    reiter = st.tabs(list(BRANCHEN))
    for tab, (br, (etf, _)) in zip(reiter, BRANCHEN.items()):
        with tab:
            meldungen = nachrichten(etf)[-5:][::-1]
            if not meldungen:
                st.caption("Gerade keine Meldungen.")
            for m in meldungen:
                st.markdown(f"**{m['zeit']:%d.%m. %H:%M}** · {m['quelle']} – [{m['titel']}]({m['link']})" if m["link"]
                            else f"**{m['zeit']:%d.%m. %H:%M}** · {m['titel']}")
    st.caption(f"Daten: Yahoo Finance, verzögert bis ca. 15 Min. · aktualisiert {jetzt:%H:%M} Uhr · MSCI World = URTH, "
               f"FTSE All-World = VT, S&P 500 Tech = XLK (ETFs) · Keine Anlageberatung")


col_logo, _ = st.columns([1, 12])
col_logo.image("logo.png", width=44)
board()
