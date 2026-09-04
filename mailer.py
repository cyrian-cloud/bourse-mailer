"""
mailer.py — Briefing boursier automatique chaque matin a 7h00
Envoie un mail HTML avec analyse technique + actualites + suggestion hebdo
"""

import smtplib, schedule, time, requests, sys, os, json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from email.utils import formatdate

sys.path.append(os.path.dirname(__file__))
from analyzer import technical_analysis, fundamental_analysis

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SENDER_EMAIL    = "cyrianhage188@gmail.com"
SENDER_PASSWORD = "afmp gjha uian cawb"
RECEIVER_EMAIL  = "cyrian.hage@hotmail.com"

PORTFOLIO = {
    "STMPA.PA": {"cost": 23.38,  "qty": 3,  "currency": "EUR"},
    "TTE.PA":   {"cost": 51.03,  "qty": 3,  "currency": "EUR"},
    "2NN.HA":   {"cost": 54.68,  "qty": 5,  "currency": "EUR"},
    "UST.PA":   {"cost": 82.56,  "qty": 5,  "currency": "EUR"},
    "ASTS":     {"cost": 101.00, "qty": 4,  "currency": "USD", "pending": True},
    "NBIS":     {"cost": 38.51,  "qty": 8,  "currency": "USD"},
}

ASTS_STRATEGY = {"entry": 101.0, "stop_loss": 85.0, "target": 125.0}
SEND_TIME = "07:00"

TICKER_SEARCH_NAMES = {
    "STMPA.PA": "STMicroelectronics",
    "TTE.PA":   "TotalEnergies",
    "2NN.HA":   "2G Energy",
    "UST.PA":   "Amundi Nasdaq-100 ETF",
    "ASTS":     "AST SpaceMobile",
    "NBIS":     "Nebius Group",
}

# ─── SUGGESTIONS POOL ─────────────────────────────────────────────────────────
SUGGESTIONS_POOL = [
    {"ticker": "NOVO-B.CO", "nom": "Novo Nordisk",  "secteur": "Sante / Pharma",
     "raison": "Leader mondial Ozempic/diabete. Secteur defensif absent de ton portefeuille. Dividende + croissance.",
     "risque": "Faible-Moyen", "budget": "~50 EUR/action", "emoji": "💊"},
    {"ticker": "BNP.PA",    "nom": "BNP Paribas",   "secteur": "Finance / Banque",
     "raison": "Banque europeenne solide avec dividende ~7%. Aucune exposition finance dans ton portefeuille.",
     "risque": "Moyen",       "budget": "~60 EUR/action", "emoji": "🏦"},
    {"ticker": "VIE.PA",    "nom": "Veolia",         "secteur": "Eau / Environnement",
     "raison": "Leader mondial traitement eau et dechets. Dividende ~5%, tres defensif. Secteur absent.",
     "risque": "Faible",      "budget": "~30 EUR/action", "emoji": "🌊"},
    {"ticker": "AIR.PA",    "nom": "Airbus",          "secteur": "Aeronautique / Defense",
     "raison": "Carnet de commandes record 8 ans. Secteur defense en forte croissance en Europe.",
     "risque": "Moyen",       "budget": "~170 EUR/action", "emoji": "✈️"},
    {"ticker": "PLTR",      "nom": "Palantir",        "secteur": "IA / Defense US",
     "raison": "IA appliquee defense et gouvernements. Profil different de NBIS. Croissance forte.",
     "risque": "Eleve",       "budget": "~120 USD/action", "emoji": "🛡️"},
    {"ticker": "MC.PA",     "nom": "LVMH",            "secteur": "Luxe / Consommation",
     "raison": "Leader mondial luxe, tres defensif, dividende solide. Aucune exposition luxe actuellement.",
     "risque": "Faible-Moyen","budget": "~600 EUR/action — 1 titre ou ETF luxe", "emoji": "👜"},
    {"ticker": "ASML.AS",   "nom": "ASML",            "secteur": "Semi-conducteurs premium",
     "raison": "Monopole mondial machines lithographie EUV. Complementaire a STMPA, positionnement different.",
     "risque": "Moyen",       "budget": "~650 EUR/action — ETF ou fractionnaire", "emoji": "🔬"},
    {"ticker": "OR.PA",     "nom": "L'Oreal",         "secteur": "Consommation / Beaute",
     "raison": "Valeur refuge consommation premium. Croissance Asie + dividende regulier. Tres defensif.",
     "risque": "Faible",      "budget": "~380 EUR/action — attendre repli", "emoji": "💄"},
]

RISQUE_COLORS = {
    "Faible": "#27ae60", "Faible-Moyen": "#2980b9",
    "Moyen": "#f39c12",  "Eleve": "#e74c3c"
}

# ─── ACTUALITES ───────────────────────────────────────────────────────────────
def get_news(ticker, max_items=3):
    try:
        import urllib.parse
        from xml.etree import ElementTree as ET
        query = TICKER_SEARCH_NAMES.get(ticker, ticker)
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=fr&gl=FR&ceid=FR:fr"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(resp.content)
        news = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "").strip()
            link  = item.findtext("link", "").strip()
            if " - " in title:
                title = title.rsplit(" - ", 1)[0].strip()
            if title:
                news.append({"title": title, "link": link})
        return news
    except Exception:
        return []

# ─── WATCHLIST ────────────────────────────────────────────────────────────────
def load_watchlist():
    wf = os.path.join(os.path.dirname(__file__), "watchlist.json")
    try:
        if os.path.exists(wf):
            with open(wf, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return list(data.keys())
    except Exception:
        pass
    return []

def load_strategies():
    sf = os.path.join(os.path.dirname(__file__), "strategies.json")
    try:
        if os.path.exists(sf):
            with open(sf, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def load_portfolio_file():
    pf = os.path.join(os.path.dirname(__file__), "portfolio.json")
    try:
        if os.path.exists(pf):
            with open(pf, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None

# ─── SUGGESTION HEBDO ─────────────────────────────────────────────────────────
def generate_weekly_suggestion():
    week_num = datetime.now().isocalendar()[1]
    s = SUGGESTIONS_POOL[week_num % len(SUGGESTIONS_POOL)]
    rc = RISQUE_COLORS.get(s["risque"], "#f39c12")

    price_block = ""
    try:
        tech = technical_analysis(s["ticker"])
        if tech:
            price_block = (
                '<div style="font-size:12px;color:#ccc;margin-bottom:8px;">'
                'Cours actuel : <strong>' + str(tech["price"]) + '</strong>'
                ' | Variation 1j : ' + ("{:+.2f}".format(tech["change_1d"])) + '%'
                '</div>'
            )
    except Exception:
        pass

    news = get_news(s["ticker"])
    news_items = "".join([
        '<li style="margin:3px 0;"><a href="' + n["link"] + '" style="color:#4f8ef7;font-size:12px;">' + n["title"] + '</a></li>'
        for n in news[:2]
    ]) or '<li style="color:#999;font-size:12px;">Aucune actualite recente</li>'

    return (
        '<div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);border-radius:12px;padding:20px;margin:16px 0;color:white;">'
        '<div style="font-size:13px;color:#aaa;margin-bottom:4px;">💡 IDEE DE LA SEMAINE</div>'
        '<div style="font-size:18px;font-weight:bold;margin-bottom:2px;">'
        + s["emoji"] + " " + s["nom"] + ' <span style="color:#aaa;font-size:14px;">(' + s["ticker"] + ')</span></div>'
        '<div style="font-size:12px;color:#4f8ef7;margin-bottom:12px;">' + s["secteur"] + '</div>'
        '<div style="background:rgba(255,255,255,0.08);border-radius:8px;padding:12px;margin-bottom:12px;">'
        '<div style="font-size:13px;line-height:1.5;">' + s["raison"] + '</div></div>'
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;">'
        '<div style="background:rgba(255,255,255,0.06);padding:8px 12px;border-radius:6px;font-size:12px;">💰 ' + s["budget"] + '</div>'
        '<div style="background:' + rc + '22;border:1px solid ' + rc + ';padding:8px 12px;border-radius:6px;font-size:12px;color:' + rc + ';">⚡ Risque ' + s["risque"] + '</div>'
        '</div>'
        + price_block +
        '<div style="font-size:12px;color:#aaa;margin-bottom:4px;">Actualites :</div>'
        '<ul style="margin:0;padding-left:16px;">' + news_items + '</ul>'
        '<div style="font-size:11px;color:#555;margin-top:12px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.1);">'
        '⚠️ Suggestion basee sur la diversification. Pas un conseil financier.</div>'
        '</div>'
    )

# ─── GENERATION HTML ──────────────────────────────────────────────────────────

# ─── CONSEIL ACHAT/CONSERVER/VENDRE ──────────────────────────────────────────
def generate_advice(ticker, tech, fund, meta):
    """Genere un conseil clair avec raison pour chaque action."""
    if not tech:
        return ("SURVEILLER", "#f39c12", "Donnees insuffisantes pour conseiller.")

    price     = tech["price"]
    rsi       = tech["rsi"]
    cost      = meta.get("cost", 0)
    pending   = meta.get("pending", False)
    gain_pct  = ((price - cost) / cost * 100) if cost > 0 else 0
    score     = tech["tech_score"] + fund["fund_score"]
    ma20      = tech["ma20"]

    # Logique conseil
    reasons = []

    # Cas ordre en attente
    if pending:
        return ("EN ATTENTE", "#4f8ef7", "Ordre d'achat en cours. Attends l'execution avant d'agir.")

    # Forte plus-value + RSI surachete = envisager vente partielle
    if gain_pct > 100 and rsi > 65:
        reasons.append("plus-value exceptionnelle (+{:.0f}%)".format(gain_pct))
        reasons.append("RSI eleve ({})".format(rsi))
        return ("VENDRE PARTIEL", "#ff4560",
                "Position tres profitable. " + " et ".join(reasons) + ". Securise une partie des gains.")

    # RSI survendu + prix sous MA20 = opportunite achat
    if rsi < 35 and price < ma20:
        return ("ACHETER", "#00e5b0",
                "RSI survendu ({}) et prix sous MA20. Signal d'achat technique fort.".format(rsi))

    # Score eleve = conserver
    if score >= 4:
        reasons.append("score technique/fondamental fort ({}/10)".format(score))
        if gain_pct > 20:
            reasons.append("bonne plus-value ({:+.1f}%)".format(gain_pct))
        return ("CONSERVER", "#00e5b0", "Situation favorable. " + ", ".join(reasons) + ".")

    # En perte + tendance baissiere = prudence
    if gain_pct < -10 and price < ma20:
        return ("PRUDENCE", "#ffd166",
                "Position en perte ({:+.1f}%) et prix sous MA20. Surveille de pres.".format(gain_pct))

    # Neutre par defaut
    if gain_pct > 0:
        return ("CONSERVER", "#00e5b0",
                "Position positive ({:+.1f}%). Pas de signal fort pour agir.".format(gain_pct))
    else:
        return ("SURVEILLER", "#f39c12",
                "Position neutre. Attends un signal clair avant d'agir.")

def generate_html(portfolio_data, watchlist_data=None):
    today = datetime.now().strftime("%A %d %B %Y")
    G = "#27ae60"; R = "#e74c3c"; O = "#f39c12"; B = "#2980b9"
    DARK = "#1a1a2e"; LIGHT = "#f8f9fa"

    rows_html = ""; alerts_html = ""
    total_invested = 0; total_value = 0

    for item in portfolio_data:
        ticker = item["ticker"]; tech = item["tech"]
        fund = item["fund"]; meta = item["meta"]; news = item["news"]
        if not tech:
            continue

        price = tech["price"]; chg = tech["change_1d"]
        cc = G if chg >= 0 else R; arrow = "▲" if chg >= 0 else "▼"
        cost = meta["cost"]; qty = meta["qty"]
        gain_pct = ((price - cost) / cost) * 100 if cost > 0 else 0
        gc = G if gain_pct >= 0 else R
        total_invested += cost * qty; total_value += price * qty

        score = tech["tech_score"] + fund["fund_score"]
        if score >= 6:   verdict, vc = "🟢 OPPORTUNITE", G
        elif score >= 3: verdict, vc = "🟡 SURVEILLER",  O
        elif score >= 0: verdict, vc = "🟠 PRUDENCE",    "#e67e22"
        else:            verdict, vc = "🔴 EVITER",      R

        pending = '<span style="background:' + O + ';color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">ORDRE EN ATTENTE</span>' if meta.get("pending") else ""

        if ticker == "ASTS" and not meta.get("pending"):
            if price <= ASTS_STRATEGY["stop_loss"]:
                alerts_html += '<div style="background:#ffeaea;border-left:4px solid ' + R + ';padding:12px;margin:8px 0;border-radius:4px;">🚨 <strong>ALERTE STOP-LOSS ASTS :</strong> Prix (' + str(price) + '$) a atteint ton stop-loss (' + str(ASTS_STRATEGY["stop_loss"]) + '$). <strong>Vends immediatement.</strong></div>'
            elif price >= ASTS_STRATEGY["target"]:
                alerts_html += '<div style="background:#eafff0;border-left:4px solid ' + G + ';padding:12px;margin:8px 0;border-radius:4px;">🎯 <strong>OBJECTIF ATTEINT ASTS :</strong> Prix (' + str(price) + '$) a atteint ta cible (' + str(ASTS_STRATEGY["target"]) + '$). Pense a vendre.</div>'

        signals_html = "".join(["<li>" + sig + "</li>" for sig in tech["signals"] + fund["signals"]])
        news_html = "".join(['<li><a href="' + n["link"] + '" style="color:' + B + ';">' + n["title"] + '</a></li>' for n in news]) or '<li style="color:#999;">Aucune actualite</li>'
        advice, advice_color, advice_reason = generate_advice(ticker, tech, fund, meta)

        rows_html += (
            '<div style="background:white;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
            '<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #eee;padding-bottom:12px;margin-bottom:12px;">'
            '<div><span style="font-size:20px;font-weight:bold;color:' + DARK + ';">' + ticker + '</span>' + pending + '<div style="color:#666;font-size:12px;margin-top:2px;">' + fund["name"][:40] + '</div></div>'
            '<div style="text-align:right;"><div style="font-size:22px;font-weight:bold;">$' + str(price) + '</div>'
            '<div style="color:' + cc + ';font-weight:bold;">' + arrow + ' ' + "{:.2f}".format(abs(chg)) + '% aujourd\'hui</div></div></div>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">'
            '<div style="background:' + LIGHT + ';padding:10px;border-radius:8px;">'
            '<div style="font-size:11px;color:#888;margin-bottom:4px;">POSITION</div>'
            '<div style="font-size:13px;"><b>' + str(qty) + ' titres</b> @ $' + str(cost) + '</div>'
            '<div style="font-size:12px;color:#888;">Investi : $' + "{:,.0f}".format(cost * qty) + '</div>'
            '<div style="font-size:12px;color:#888;">Valeur : $' + "{:,.0f}".format(price * qty) + '</div>'
            '<div style="font-size:13px;font-weight:bold;color:' + gc + ';margin-top:4px;">' + ("{:+.1f}".format(gain_pct)) + '% | ' + ("{:+,.0f}".format((price - cost) * qty)) + '$</div>'
            '</div>'
            '<div style="background:' + LIGHT + ';padding:10px;border-radius:8px;">'
            '<div style="font-size:11px;color:#888;margin-bottom:4px;">TECHNIQUE</div>'
            '<div style="font-size:13px;">RSI : <b>' + str(tech["rsi"]) + '</b> — ' + ("Survendu" if tech["rsi"] < 30 else "Surachete" if tech["rsi"] > 70 else "Neutre") + '</div>'
            '<div style="font-size:12px;color:#888;">MA20 : $' + str(tech["ma20"]) + '</div>'
            '<div style="font-size:13px;font-weight:bold;color:' + vc + ';margin-top:4px;">Score ' + ("{:+d}".format(score)) + '/10 — ' + verdict + '</div>'
            '</div>'
            '</div>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">'
            '<div><div style="font-size:12px;font-weight:bold;color:#555;margin-bottom:4px;">Signaux</div>'
            '<ul style="margin:0;padding-left:16px;font-size:12px;color:#333;">' + signals_html + '</ul></div>'
            '<div><div style="font-size:12px;font-weight:bold;color:#555;margin-bottom:4px;">Actualites</div>'
            '<ul style="margin:0;padding-left:16px;font-size:12px;">' + news_html + '</ul></div></div>'
            '<div style="margin:12px 0 4px 0;padding:12px 14px;background:' + advice_color + '18;border-left:4px solid ' + advice_color + ';border-radius:6px;">'
            '<div style="font-weight:bold;font-size:14px;color:' + advice_color + ';">' + advice + '</div>'
            '<div style="font-size:12px;color:#444;margin-top:4px;">' + advice_reason + '</div>'
            '</div></div>'
        )

    total_gain_pct = ((total_value - total_invested) / total_invested * 100) if total_invested > 0 else 0
    tgc = G if total_gain_pct >= 0 else R

    # Strategies dynamiques depuis strategies.json
    strategies = load_strategies()
    strategies_html = ""
    if strategies:
        for sticker, strat in strategies.items():
            lines = []
            if strat.get("entree"):
                lines.append("Entree : <strong>" + str(strat["entree"]) + "$</strong>")
            if strat.get("stop_loss"):
                lines.append("Stop-loss : <strong>" + str(strat["stop_loss"]) + "$</strong>")
            if strat.get("objectif"):
                lines.append("Objectif : <strong>" + str(strat["objectif"]) + "$</strong>")
            details = " | ".join(lines)
            strategies_html += (
                '<div style="background:#eef4ff;border:1px solid ' + B + ';border-radius:8px;padding:14px;margin:8px 0;">'
                '<strong>Strategie active — ' + sticker + '</strong><br>'
                '<span style="font-size:13px;">' + (details + "<br>" if details else "")
                + (strat.get("catalyseurs", "")) + '</span>'
                + ('<div style="font-size:11px;color:#e74c3c;margin-top:4px;">Regle : ' + strat["regle"] + '</div>' if strat.get("regle") else "")
                + '</div>'
            )
    asts_reminder = strategies_html

    # Watchlist
    watchlist_block = ""
    if watchlist_data:
        wl_cards = ""
        for item in watchlist_data:
            t = item["ticker"]; tech = item["tech"]; fund = item["fund"]; news = item["news"]
            if not tech:
                continue
            price = tech["price"]; chg = tech["change_1d"]
            cc2 = G if chg >= 0 else R; arrow2 = "▲" if chg >= 0 else "▼"
            score2 = tech["tech_score"] + fund["fund_score"]
            if score2 >= 6:   v2, vc2 = "🟢 OPPORTUNITE", G
            elif score2 >= 3: v2, vc2 = "🟡 SURVEILLER",  O
            else:              v2, vc2 = "🔴 EVITER",      R
            ni = "".join(['<li><a href="' + n["link"] + '" style="color:' + B + ';font-size:12px;">' + n["title"] + '</a></li>' for n in news]) or '<li style="color:#999;">Aucune actualite</li>'
            wl_cards += (
                '<div style="background:white;border-radius:8px;padding:14px;margin:8px 0;border-left:3px solid ' + B + ';box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
                '<div style="display:flex;justify-content:space-between;margin-bottom:6px;">'
                '<span style="font-weight:bold;color:' + DARK + ';">' + t + '</span>'
                '<span style="font-size:13px;color:' + cc2 + ';">' + arrow2 + ' ' + "{:.2f}".format(abs(chg)) + '% | $' + str(price) + ' | Score ' + ("{:+d}".format(score2)) + '/10</span></div>'
                '<div style="font-size:12px;color:#555;margin-bottom:4px;">' + v2 + '</div>'
                '<ul style="margin:4px 0;padding-left:16px;font-size:12px;">' + ni + '</ul></div>'
            )
        if wl_cards:
            watchlist_block = (
                '<div style="background:white;border-radius:12px;padding:16px;margin:16px 0;box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
                '<div style="font-size:14px;font-weight:bold;color:' + DARK + ';margin-bottom:8px;">👁️ WATCHLIST</div>'
                + wl_cards + '</div>'
            )

    # Suggestion hebdo (lundi uniquement)
    suggestion_block = generate_weekly_suggestion() if datetime.now().weekday() == 0 else ""

    html = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
        '<body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#f0f2f5;margin:0;padding:20px;">'
        '<div style="max-width:700px;margin:0 auto;">'
        '<div style="background:' + DARK + ';color:white;padding:24px;border-radius:12px;margin-bottom:16px;text-align:center;">'
        '<div style="font-size:24px;font-weight:bold;">Briefing Portefeuille</div>'
        '<div style="color:#aaa;margin-top:4px;">' + today + ' — 7h00</div></div>'
        '<div style="background:white;border-radius:12px;padding:16px;margin-bottom:8px;display:grid;grid-template-columns:1fr 1fr;gap:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
        '<div style="text-align:center;"><div style="font-size:12px;color:#888;">VALEUR TOTALE (approx.)</div>'
        '<div style="font-size:20px;font-weight:bold;">$' + "{:,.0f}".format(total_value) + '</div></div>'
        '<div style="text-align:center;"><div style="font-size:12px;color:#888;">GAIN TOTAL</div>'
        '<div style="font-size:20px;font-weight:bold;color:' + tgc + ';">' + ("{:+.1f}".format(total_gain_pct)) + '%</div></div></div>'
        + alerts_html + asts_reminder + rows_html
        + watchlist_block + suggestion_block
        + '<div style="text-align:center;color:#aaa;font-size:11px;margin-top:20px;padding:12px;">⚠️ Pas un conseil financier — Genere automatiquement</div>'
        '</div></body></html>'
    )
    return html

# ─── ENVOI MAIL ───────────────────────────────────────────────────────────────
def send_email(html_content):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Briefing Portefeuille — " + datetime.now().strftime("%d/%m/%Y")
    msg["From"] = SENDER_EMAIL; msg["To"] = RECEIVER_EMAIL
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(html_content, "html"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("[" + datetime.now().strftime("%H:%M:%S") + "] Mail envoye a " + RECEIVER_EMAIL)
    except Exception as e:
        print("[" + datetime.now().strftime("%H:%M:%S") + "] Erreur : " + str(e))

# ─── TACHE PRINCIPALE ─────────────────────────────────────────────────────────
def run_daily_briefing():
    print("\n[" + datetime.now().strftime("%H:%M:%S") + "] Generation du briefing...")

    # Charge portfolio depuis fichier si disponible
    portfolio = load_portfolio_file() or PORTFOLIO
    portfolio_data = []
    for ticker, meta in portfolio.items():
        print("  -> Analyse " + ticker + "...")
        portfolio_data.append({
            "ticker": ticker, "tech": technical_analysis(ticker),
            "fund": fundamental_analysis(ticker), "meta": meta, "news": get_news(ticker)
        })

    watchlist = load_watchlist()
    watchlist_data = []
    for ticker in watchlist:
        if ticker not in PORTFOLIO:
            print("  -> Watchlist " + ticker + "...")
            watchlist_data.append({
                "ticker": ticker, "tech": technical_analysis(ticker),
                "fund": fundamental_analysis(ticker),
                "meta": {"cost": 0, "qty": 0, "watchlist": True}, "news": get_news(ticker)
            })

    html = generate_html(portfolio_data, watchlist_data)
    send_email(html)

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  BRIEFING BOURSIER AUTOMATIQUE")
    print("  Envoi programme chaque jour a " + SEND_TIME)
    print("=" * 50)
    print("\n  Test d'envoi immediat...")
    run_daily_briefing()
    schedule.every().day.at(SEND_TIME).do(run_daily_briefing)
    print("\n  Scheduler actif — prochain envoi a " + SEND_TIME)
    while True:
        schedule.run_pending()
        time.sleep(30)
