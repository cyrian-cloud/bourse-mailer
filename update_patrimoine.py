"""
update_patrimoine.py — Met à jour le Google Sheet "Patrimoine Cyrian" chaque lundi
- Lit toutes les positions de portfolio.json dynamiquement
- Ajoute automatiquement les nouvelles actions
- Calcule les intérêts Bricks le 8 de chaque mois
"""

import json
import os
import datetime
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials

# ── CONFIG ────────────────────────────────────────────────────────────────
SPREADSHEET_ID   = os.environ.get("GSHEET_PATRIMOINE_ID")
SHEET_NAME       = "Patrimoine"
PORTFOLIO_FILE   = "portfolio.json"

# Lignes fixes dans le sheet (ne pas toucher)
ROW_BOURSE_HEADER = 4   # "BOURSE KEYTRADE"
ROW_BOURSE_START  = 5   # première ligne d'action
ROW_BRICKS        = 18  # ligne Bricks (sera recalculée dynamiquement si besoin)

# Tickers USD (conversion EUR/USD nécessaire)
USD_TICKERS = {"NBIS", "ASTS", "GOOGL", "AMZN", "NVDA", "TSLA", "MSFT", "AAPL", "META", "UBER"}

# Mapping ticker portefeuille → ticker yfinance
YF_TICKER_MAP = {
    "STMPA.PA": "STM.PA",
    "2NN.HA":   "NN.AS",
    "UST.PA":   "ISTA.PA",
}

# Bricks
BRICKS_CAPITAL_INITIAL = 2248.68
BRICKS_TAUX_ANNUEL     = 0.09
BRICKS_FISCALITE       = 0.30

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── FONCTIONS ─────────────────────────────────────────────────────────────

def load_portfolio():
    """Charge portfolio.json — retourne {ticker: {qty, cost}}"""
    with open(PORTFOLIO_FILE, "r") as f:
        data = json.load(f)
    positions = {}
    for ticker, info in data.items():
        qty  = info.get("quantity", info.get("qty", 0))
        cost = info.get("avg_cost", info.get("cost_basis", 0))
        if qty > 0:
            positions[ticker] = {"qty": qty, "cost": cost}
    return positions

def get_yf_ticker(portfolio_ticker):
    """Convertit un ticker portefeuille en ticker yfinance"""
    return YF_TICKER_MAP.get(portfolio_ticker, portfolio_ticker)

def get_prices(portfolio_tickers):
    """Récupère les prix pour tous les tickers"""
    prices = {}
    for pt in portfolio_tickers:
        yf_ticker = get_yf_ticker(pt)
        try:
            hist = yf.Ticker(yf_ticker).history(period="2d")
            if not hist.empty:
                prices[pt] = round(float(hist["Close"].iloc[-1]), 2)
            else:
                prices[pt] = None
                print(f"  Pas de données pour {yf_ticker}")
        except Exception as e:
            print(f"  Erreur {yf_ticker}: {e}")
            prices[pt] = None
    return prices

def get_eur_usd():
    try:
        hist = yf.Ticker("EURUSD=X").history(period="2d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
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

def get_existing_tickers(ws):
    """
    Lit le sheet et retourne un dict {ticker: row_number}
    pour toutes les actions déjà présentes dans la section bourse
    """
    existing = {}
    # On lit jusqu'à la ligne 50 pour être sûr
    all_values = ws.col_values(1)  # colonne A
    for i, val in enumerate(all_values):
        row = i + 1
        if row < ROW_BOURSE_START:
            continue
        if val and val.strip() and not val.isupper():
            # C'est probablement un ticker (pas un header en majuscules)
            ticker_clean = val.strip().replace(" (x3)","").replace(" (x5)","").replace(" (x7)","").replace(" (x4)","").replace(" (x2)","").replace(" (x1)","").replace(" (x10)","").replace(" (x8)","").replace(" (x6)","").replace(" (x9)","")
            existing[ticker_clean] = row
        if val and val.strip() in ["TOTAL BOURSE", "EPARGNE", "TOTAL EPARGNE PAT", "ALTERNATIFS"]:
            break  # on s'arrête à la fin de la section bourse
    return existing

def find_next_bourse_row(ws):
    """Trouve la première ligne vide dans la section bourse"""
    all_values = ws.col_values(1)
    for i, val in enumerate(all_values):
        row = i + 1
        if row < ROW_BOURSE_START:
            continue
        if val and val.strip() in ["TOTAL BOURSE", "EPARGNE", "TOTAL EPARGNE PAT"]:
            return row  # insère juste avant le total
    return ROW_BOURSE_START + 10  # fallback

def update_bourse(ws, positions, prices, eur_usd):
    """Met à jour ou ajoute chaque position bourse"""
    updates = []
    total_valeur  = 0
    total_investi = 0

    # Récupère les tickers déjà dans le sheet
    existing = get_existing_tickers(ws)
    print(f"  Tickers existants dans le sheet: {list(existing.keys())}")

    for ticker, pos in positions.items():
        qty   = pos["qty"]
        cost  = pos["cost"]
        price = prices.get(ticker)

        if price is None:
            print(f"  {ticker:12} — prix non disponible, ignoré")
            continue

        is_usd = any(ticker.startswith(t) or ticker == t for t in USD_TICKERS)
        if is_usd:
            valeur_eur  = round(price * qty / eur_usd, 2)
            investi_eur = round(cost  * qty / eur_usd, 2)
        else:
            valeur_eur  = round(price * qty, 2)
            investi_eur = round(cost  * qty, 2)

        total_valeur  += valeur_eur
        total_investi += investi_eur
        pnl_pct = round((valeur_eur - investi_eur) / investi_eur * 100, 1) if investi_eur else 0

        # Cherche si le ticker existe déjà dans le sheet
        row = None
        for existing_ticker, existing_row in existing.items():
            if ticker.upper() in existing_ticker.upper() or existing_ticker.upper() in ticker.upper():
                row = existing_row
                break

        if row:
            # Mise à jour ligne existante
            label = f"{ticker} (x{qty})"
            updates.append({"range": f"A{row}", "values": [[label]]})
            updates.append({"range": f"B{row}", "values": [[valeur_eur]]})
            updates.append({"range": f"C{row}", "values": [[investi_eur]]})
            print(f"  MAJ  {ticker:12} x{qty} @ {price:.2f} = {valeur_eur:.2f}€ ({pnl_pct:+.1f}%)")
        else:
            # Nouvelle action — trouve la prochaine ligne dispo
            next_row = find_next_bourse_row(ws)
            label = f"{ticker} (x{qty})"
            updates.append({"range": f"A{next_row}", "values": [[label]]})
            updates.append({"range": f"B{next_row}", "values": [[valeur_eur]]})
            updates.append({"range": f"C{next_row}", "values": [[investi_eur]]})
            existing[ticker] = next_row  # met à jour le dict local
            print(f"  NEW  {ticker:12} x{qty} @ {price:.2f} = {valeur_eur:.2f}€ → ligne {next_row}")

    # Ordres en attente (ligne fixe juste après les actions)
    next_row = find_next_bourse_row(ws)
    updates.append({"range": f"B{next_row-1}", "values": [[550]]})

    return updates, total_valeur, total_investi

def update_bricks(ws, updates):
    """Calcule les intérêts Bricks le 8 du mois"""
    today = datetime.date.today()
    if today.day != 8:
        print(f"  Pas le 8 du mois ({today.day}) — Bricks ignoré")
        return updates

    print(f"\n=== CALCUL BRICKS — {today.strftime('%d/%m/%Y')} ===")

    # Trouve la ligne Bricks dynamiquement
    bricks_row = ROW_BRICKS
    all_values = ws.col_values(1)
    for i, val in enumerate(all_values):
        if val and "Bricks" in str(val):
            bricks_row = i + 1
            break

    try:
        val = ws.cell(bricks_row, 2).value
        capital = float(str(val).replace(",", ".").replace(" ", "")) if val else BRICKS_CAPITAL_INITIAL
    except:
        capital = BRICKS_CAPITAL_INITIAL

    brut   = round(capital * BRICKS_TAUX_ANNUEL / 12, 2)
    impot  = round(brut * BRICKS_FISCALITE, 2)
    net    = round(brut - impot, 2)
    capital_apres = round(capital + net, 2)

    print(f"  Capital actuel : {capital:.2f}€")
    print(f"  Intérêts bruts : {brut:.2f}€  (9%/12)")
    print(f"  Précompte 30%  : -{impot:.2f}€")
    print(f"  Intérêts nets  : +{net:.2f}€")
    print(f"  Capital après  : {capital_apres:.2f}€")

    updates.append({"range": f"B{bricks_row}", "values": [[capital_apres]]})
    updates.append({"range": f"C{bricks_row}", "values": [[BRICKS_CAPITAL_INITIAL]]})
    updates.append({"range": f"G{bricks_row}", "values": [[f"+{net:.2f}€ nets ({today.strftime('%d/%m/%Y')})"]]})

    return updates

def main():
    now = datetime.datetime.now()
    print(f"=== Mise à jour Patrimoine — {now.strftime('%d/%m/%Y %H:%M')} ===\n")

    # Connexion
    client = connect_gsheet()
    sh     = client.open_by_key(SPREADSHEET_ID)
    ws     = sh.worksheet(SHEET_NAME)

    updates = []

    # ── BOURSE ──
    print("=== BOURSE ===")
    positions  = load_portfolio()
    print(f"  Positions chargées: {list(positions.keys())}")
    prices     = get_prices(list(positions.keys()))
    eur_usd    = get_eur_usd()
    print(f"  EUR/USD: {eur_usd}\n")

    bourse_updates, total_valeur, total_investi = update_bourse(ws, positions, prices, eur_usd)
    updates.extend(bourse_updates)

    pnl = round(total_valeur - total_investi, 2)
    pnl_pct = round(pnl / total_investi * 100, 1) if total_investi else 0
    print(f"\n  Total bourse  : {total_valeur:.2f}€")
    print(f"  P&L total     : {pnl:+.2f}€ ({pnl_pct:+.1f}%)")

    # ── BRICKS ──
    print("\n=== BRICKS ===")
    updates = update_bricks(ws, updates)

    # ── TIMESTAMP ──
    updates.append({"range": "G1", "values": [[f"Mis à jour: {now.strftime('%d/%m/%Y %H:%M')}"]]})

    # ── ENVOI AU SHEET ──
    if updates:
        ws.batch_update(updates)
        print(f"\n✅ {len(updates)} cellules mises à jour")

    print("=== Terminé ===")

if __name__ == "__main__":
    main()
