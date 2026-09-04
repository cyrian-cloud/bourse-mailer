"""
update_patrimoine.py — Met à jour le Google Sheet "Patrimoine" chaque lundi
avec les prix actuels des actions depuis yfinance + portfolio.json
+ calcule les intérêts Bricks le 8 de chaque mois
"""

import json
import os
import datetime
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials

# ── CONFIG ────────────────────────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("GSHEET_PATRIMOINE_ID")
SHEET_NAME = "Patrimoine"
PORTFOLIO_FILE = "portfolio.json"

# Bricks config
BRICKS_CAPITAL_INITIAL = 2248.68   # capital investi
BRICKS_TAUX_ANNUEL = 0.09          # 9% brut/an
BRICKS_TAUX_MENSUEL = BRICKS_TAUX_ANNUEL / 12
BRICKS_FISCALITE = 0.30            # 30% précompte belge
BRICKS_ROW = 16                    # ligne dans le Google Sheet

# Bourse — mapping portfolio.json → yfinance ticker + ligne Google Sheet
TICKER_CONFIG = {
    "STMPA.PA": {"yf": "STM.PA",  "row": 6,  "usd": False},
    "TTE.PA":   {"yf": "TTE.PA",  "row": 7,  "usd": False},
    "2NN.HA":   {"yf": "NN.AS",   "row": 8,  "usd": False},
    "UST.PA":   {"yf": "ISTA.PA", "row": 9,  "usd": False},
    "NBIS":     {"yf": "NBIS",    "row": 10, "usd": True},
    "ASTS":     {"yf": "ASTS",    "row": 11, "usd": True},
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── FONCTIONS ─────────────────────────────────────────────────────────────

def load_portfolio():
    with open(PORTFOLIO_FILE, "r") as f:
        data = json.load(f)
    positions = {}
    for ticker, info in data.items():
        qty  = info.get("quantity", info.get("qty", 0))
        cost = info.get("avg_cost", info.get("cost_basis", 0))
        positions[ticker] = {"qty": qty, "cost": cost}
    return positions

def get_prices(yf_tickers):
    prices = {}
    for ticker in yf_tickers:
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            prices[ticker] = round(hist["Close"].iloc[-1], 2) if not hist.empty else None
        except Exception as e:
            print(f"Erreur prix {ticker}: {e}")
            prices[ticker] = None
    return prices

def get_eur_usd():
    try:
        hist = yf.Ticker("EURUSD=X").history(period="2d")
        if not hist.empty:
            return round(hist["Close"].iloc[-1], 4)
    except:
        pass
    return 1.08

def connect_gsheet():
    creds_json = os.environ.get("GSHEET_CREDENTIALS")
    if not creds_json:
        raise ValueError("GSHEET_CREDENTIALS secret manquant")
    creds = Credentials.from_service_account_info(
        json.loads(creds_json), scopes=SCOPES
    )
    return gspread.authorize(creds)

def calcul_bricks(capital_actuel):
    """
    Calcule les intérêts Bricks du mois.
    - 9% brut annuel → 0.75% mensuel
    - 30% précompte belge déduit
    - Retourne (brut_mensuel, net_mensuel, capital_apres)
    """
    brut  = round(capital_actuel * BRICKS_TAUX_MENSUEL, 2)
    impot = round(brut * BRICKS_FISCALITE, 2)
    net   = round(brut - impot, 2)
    capital_apres = round(capital_actuel + net, 2)
    return brut, net, impot, capital_apres

def update_bourse(ws, positions, prices, eur_usd):
    """Met à jour les valeurs bourse dans le sheet"""
    updates = []
    total_valeur = 0
    total_investi = 0

    for portfolio_ticker, cfg in TICKER_CONFIG.items():
        pos   = positions.get(portfolio_ticker, {})
        qty   = pos.get("qty", 0)
        cost  = pos.get("cost", 0)
        price = prices.get(cfg["yf"])

        if price is None or qty == 0:
            continue

        if cfg["usd"]:
            valeur_eur  = round(price * qty / eur_usd, 2)
            investi_eur = round(cost  * qty / eur_usd, 2)
        else:
            valeur_eur  = round(price * qty, 2)
            investi_eur = round(cost  * qty, 2)

        total_valeur  += valeur_eur
        total_investi += investi_eur

        updates.append({"range": f"B{cfg['row']}", "values": [[valeur_eur]]})
        updates.append({"range": f"C{cfg['row']}", "values": [[investi_eur]]})
        pnl_pct = round((valeur_eur - investi_eur) / investi_eur * 100, 1) if investi_eur else 0
        print(f"  {portfolio_ticker:12} {qty} × {price:.2f} = {valeur_eur:.2f}€  ({pnl_pct:+.1f}%)")

    # Ordres en attente ligne 12
    updates.append({"range": "B12", "values": [[550]]})

    return updates, total_valeur, total_investi

def update_bricks(ws, updates):
    """
    Calcule et met à jour Bricks le 8 du mois.
    Lit le capital actuel depuis le sheet (cellule B16),
    ajoute les intérêts nets, met à jour B16 et log dans C16.
    """
    today = datetime.date.today()
    if today.day != 8:
        print(f"  Pas le 8 du mois ({today.day}) — Bricks ignoré")
        return updates

    print(f"\n=== CALCUL BRICKS — {today.strftime('%d/%m/%Y')} ===")

    # Lire capital actuel depuis le sheet
    try:
        val = ws.cell(BRICKS_ROW, 2).value
        capital_actuel = float(str(val).replace(",", ".").replace(" ", "")) if val else BRICKS_CAPITAL_INITIAL
    except:
        capital_actuel = BRICKS_CAPITAL_INITIAL

    brut, net, impot, capital_apres = calcul_bricks(capital_actuel)

    print(f"  Capital actuel : {capital_actuel:.2f}€")
    print(f"  Intérêts bruts : {brut:.2f}€  ({BRICKS_TAUX_ANNUEL*100:.0f}% / 12)")
    print(f"  Précompte 30%  : -{impot:.2f}€")
    print(f"  Intérêts nets  : {net:.2f}€")
    print(f"  Capital après  : {capital_apres:.2f}€")

    # Mise à jour capital Bricks (B16) et derniers intérêts (C16)
    updates.append({"range": f"B{BRICKS_ROW}", "values": [[capital_apres]]})
    updates.append({"range": f"C{BRICKS_ROW}", "values": [[BRICKS_CAPITAL_INITIAL]]})  # investi reste fixe
    updates.append({"range": f"G{BRICKS_ROW}", "values": [[f"+{net:.2f}€ nets ce mois ({today.strftime('%d/%m/%Y')})"]]})

    return updates

def main():
    now   = datetime.datetime.now()
    today = datetime.date.today()
    print(f"=== Mise à jour Patrimoine — {now.strftime('%d/%m/%Y %H:%M')} ===\n")

    # Connexion
    client = connect_gsheet()
    sh     = client.open_by_key(SPREADSHEET_ID)
    ws     = sh.worksheet(SHEET_NAME)

    updates = []

    # ── 1. BOURSE (chaque lundi) ──────────────────────────────────────────
    print("=== BOURSE ===")
    positions = load_portfolio()
    yf_tickers = [cfg["yf"] for cfg in TICKER_CONFIG.values()]
    prices  = get_prices(yf_tickers)
    eur_usd = get_eur_usd()
    print(f"EUR/USD: {eur_usd}")

    bourse_updates, total_valeur, total_investi = update_bourse(ws, positions, prices, eur_usd)
    updates.extend(bourse_updates)

    pnl_total = round(total_valeur - total_investi, 2)
    pnl_pct   = round(pnl_total / total_investi * 100, 1) if total_investi else 0
    print(f"\n  Total bourse  : {total_valeur:.2f}€")
    print(f"  Total investi : {total_investi:.2f}€")
    print(f"  P&L total     : {pnl_total:+.2f}€ ({pnl_pct:+.1f}%)")

    # ── 2. BRICKS (le 8 du mois seulement) ───────────────────────────────
    print("\n=== BRICKS ===")
    updates = update_bricks(ws, updates)

    # ── 3. Timestamp mise à jour ──────────────────────────────────────────
    updates.append({"range": "G1", "values": [[f"Mis à jour: {now.strftime('%d/%m/%Y %H:%M')}"]]})

    # ── 4. Envoi batch au Google Sheet ────────────────────────────────────
    if updates:
        ws.batch_update(updates)
        print(f"\n✅ Google Sheet mis à jour ({len(updates)} cellules)")

    print("=== Terminé ===")

if __name__ == "__main__":
    main()
