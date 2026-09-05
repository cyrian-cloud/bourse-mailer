"""
update_patrimoine.py — Met à jour le Google Sheet "Patrimoine Cyrian"
- Chaque lundi : prix actions mis à jour
- Le 8 du mois : intérêts Bricks
- Le 1er du mois : +30€ investi ING
- À chaque run : ligne ajoutée dans Historique
"""

import json
import os
import datetime
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials

# ── CONFIG ────────────────────────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("GSHEET_PATRIMOINE_ID")
SHEET_NAME     = "Patrimoine"
PORTFOLIO_FILE = "portfolio.json"

USD_TICKERS = {"NBIS","ASTS","GOOGL","AMZN","NVDA","TSLA","MSFT","AAPL","META","UBER"}

YF_TICKER_MAP = {
    "2NN.HA": "NN.AS",
}

BRICKS_CAPITAL_INITIAL = 2248.68
BRICKS_TAUX_ANNUEL     = 0.09
BRICKS_FISCALITE       = 0.30

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
        cost = info.get("avg_cost", info.get("cost_basis", info.get("cost", 0)))
        if qty > 0:
            positions[ticker] = {"qty": qty, "cost": cost}
    return positions

def get_yf_ticker(portfolio_ticker):
    return YF_TICKER_MAP.get(portfolio_ticker, portfolio_ticker)

def get_prices(portfolio_tickers):
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

def get_sheet_tickers(ws):
    existing = {}
    all_values = ws.col_values(1)
    for i, val in enumerate(all_values):
        row = i + 1
        if row < 5: continue
        if not val or not val.strip(): continue
        if val.strip() in ["ÉPARGNE","EPARGNE","ALTERNATIFS","PATRIMOINE TOTAL",
                           "TOTAL BOURSE","TOTAL ÉPARGNE","TOTAL ALTERNATIFS","TOTAL GLOBAL"]:
            break
        clean = val.strip()
        for suffix in [" (x1)"," (x2)"," (x3)"," (x4)"," (x5)"," (x6)",
                       " (x7)"," (x8)"," (x9)"," (x10)"," (x11)"," (x12)"]:
            clean = clean.replace(suffix,"")
        clean = clean.strip()
        if clean and clean != "BOURSE KEYTRADE":
            existing[clean] = row
    return existing

def find_insert_row(ws):
    all_values = ws.col_values(1)
    for i, val in enumerate(all_values):
        row = i + 1
        if val and val.strip() in ["TOTAL BOURSE","ÉPARGNE","EPARGNE"]:
            return row
    return 13

def update_bourse(ws, positions, prices, eur_usd):
    updates = []
    total_valeur  = 0.0
    total_investi = 0.0

    existing = get_sheet_tickers(ws)
    print(f"  Tickers dans le sheet: {list(existing.keys())}")

    for ticker, pos in positions.items():
        qty   = pos["qty"]
        cost  = pos["cost"]
        price = prices.get(ticker)

        if price is None:
            print(f"  {ticker:12} — prix non disponible")
            continue

        is_usd = ticker in USD_TICKERS or pos.get("currency","") == "USD"

        if is_usd:
            valeur_eur  = round(float(price * qty / eur_usd), 2)
            investi_eur = round(float(cost  * qty / eur_usd), 2)
        else:
            valeur_eur  = round(float(price * qty), 2)
            investi_eur = round(float(cost  * qty), 2)

        total_valeur  += valeur_eur
        total_investi += investi_eur
        pnl_pct = round((valeur_eur - investi_eur) / investi_eur * 100, 1) if investi_eur else 0.0

        row = None
        for sheet_ticker, sheet_row in existing.items():
            if ticker.upper() == sheet_ticker.upper():
                row = sheet_row; break
            if ticker == "STMPA.PA" and "STMPA" in sheet_ticker.upper(): row = sheet_row; break
            if ticker == "2NN.HA" and "2NN" in sheet_ticker.upper(): row = sheet_row; break
            if ticker == "UST.PA" and "UST" in sheet_ticker.upper(): row = sheet_row; break

        label = f"  {ticker} (x{qty})"

        if row:
            updates.append({"range": f"A{row}", "values": [[label]]})
            updates.append({"range": f"B{row}", "values": [[valeur_eur]]})
            updates.append({"range": f"C{row}", "values": [[investi_eur]]})
            print(f"  MAJ  {ticker:12} x{qty} @ {price:.2f} → {valeur_eur:.2f}€ ({pnl_pct:+.1f}%)")
        else:
            insert_row = find_insert_row(ws)
            updates.append({"range": f"A{insert_row}", "values": [[label]]})
            updates.append({"range": f"B{insert_row}", "values": [[valeur_eur]]})
            updates.append({"range": f"C{insert_row}", "values": [[investi_eur]]})
            existing[ticker] = insert_row
            print(f"  NEW  {ticker:12} x{qty} @ {price:.2f} → {valeur_eur:.2f}€ ligne {insert_row}")

    return updates, total_valeur, total_investi

def update_bricks(ws, updates):
    today = datetime.date.today()
    if today.day != 8:
        print(f"  Pas le 8 du mois ({today.day}) — Bricks ignoré")
        return updates

    print(f"\n=== CALCUL BRICKS — {today.strftime('%d/%m/%Y')} ===")

    bricks_row = 18
    all_values = ws.col_values(1)
    for i, val in enumerate(all_values):
        if val and "Bricks" in str(val):
            bricks_row = i + 1
            break

    try:
        val = ws.cell(bricks_row, 2).value
        capital = float(str(val).replace(",",".").replace(" ","").replace("€","")) if val else BRICKS_CAPITAL_INITIAL
    except:
        capital = BRICKS_CAPITAL_INITIAL

    brut   = round(capital * BRICKS_TAUX_ANNUEL / 12, 2)
    impot  = round(brut * BRICKS_FISCALITE, 2)
    net    = round(brut - impot, 2)
    capital_apres = round(capital + net, 2)

    print(f"  Capital : {capital:.2f}€ → net:+{net:.2f}€ → {capital_apres:.2f}€")

    updates.append({"range": f"B{bricks_row}", "values": [[capital_apres]]})
    updates.append({"range": f"C{bricks_row}", "values": [[BRICKS_CAPITAL_INITIAL]]})
    updates.append({"range": f"G{bricks_row}", "values": [[f"+{net:.2f}€ nets ({today.strftime('%d/%m/%Y')})"]]})

    return updates

def update_ing(ws, updates):
    today = datetime.date.today()
    if today.day != 1:
        print(f"  Pas le 1er du mois ({today.day}) — ING ignoré")
        return updates

    print(f"\n=== ING INVEST — {today.strftime('%d/%m/%Y')} ===")

    ing_row = None
    all_values = ws.col_values(1)
    for i, val in enumerate(all_values):
        if val and "ING" in str(val):
            ing_row = i + 1
            break

    if not ing_row:
        print("  Ligne ING non trouvée")
        return updates

    try:
        val = ws.cell(ing_row, 3).value
        investi = float(str(val).replace(",",".").replace(" ","").replace("€","")) if val else 1400.0
    except:
        investi = 1400.0

    nouvel_investi = round(investi + 30.0, 2)
    updates.append({"range": f"C{ing_row}", "values": [[nouvel_investi]]})
    print(f"  ING investi: {investi:.2f}€ → {nouvel_investi:.2f}€ (+30€)")

    return updates

def update_historique(sh, total_valeur, total_investi):
    try:
        ws_hist = sh.worksheet("Historique")
    except:
        print("  Onglet Historique non trouvé")
        return

    today = datetime.date.today().strftime("%d/%m/%Y")
    total_valeur  = round(float(total_valeur), 2)
    total_investi = round(float(total_investi), 2)
    pnl = round(float(total_valeur - total_investi), 2)

    if total_investi > 0:
        pnl_pct = round(float(pnl / total_investi * 100), 2)
    else:
        pnl_pct = 0.0

    # Sécurité NaN/inf
    if pnl_pct != pnl_pct or abs(pnl_pct) == float('inf'):
        pnl_pct = 0.0

    all_dates = ws_hist.col_values(1)
    if today in all_dates:
        row = all_dates.index(today) + 1
        ws_hist.update(f"A{row}:E{row}", [[today, total_valeur, total_investi, pnl, pnl_pct]])
        print(f"  Historique mis à jour: {today} — {total_valeur}€")
    else:
        ws_hist.append_row([today, total_valeur, total_investi, pnl, pnl_pct])
        print(f"  Historique nouvelle entrée: {today} — {total_valeur}€")

def main():
    now = datetime.datetime.now()
    print(f"=== Mise à jour Patrimoine — {now.strftime('%d/%m/%Y %H:%M')} ===\n")

    client = connect_gsheet()
    sh     = client.open_by_key(SPREADSHEET_ID)
    ws     = sh.worksheet(SHEET_NAME)

    updates = []

    # ── BOURSE ──
    print("=== BOURSE ===")
    positions  = load_portfolio()
    print(f"  Positions: {list(positions.keys())}")
    prices     = get_prices(list(positions.keys()))
    eur_usd    = get_eur_usd()
    print(f"  EUR/USD: {eur_usd}\n")

    bourse_updates, total_valeur, total_investi = update_bourse(ws, positions, prices, eur_usd)
    updates.extend(bourse_updates)

    pnl = round(total_valeur - total_investi, 2)
    pnl_pct = round(pnl / total_investi * 100, 1) if total_investi else 0
    print(f"\n  Total bourse  : {total_valeur:.2f}€")
    print(f"  Total investi : {total_investi:.2f}€")
    print(f"  P&L           : {pnl:+.2f}€ ({pnl_pct:+.1f}%)")

    # ── HISTORIQUE ──
    print("\n=== HISTORIQUE ===")
    update_historique(sh, total_valeur, total_investi)

    # ── BRICKS ──
    print("\n=== BRICKS ===")
    updates = update_bricks(ws, updates)

    # ── ING ──
    print("\n=== ING ===")
    updates = update_ing(ws, updates)

    # ── TIMESTAMP ──
    updates.append({"range": "G1", "values": [[f"Mis à jour: {now.strftime('%d/%m/%Y %H:%M')}"]]})

    # ── ENVOI ──
    if updates:
        ws.batch_update(updates)
        print(f"\n✅ {len(updates)} cellules mises à jour")

    print("=== Terminé ===")

if __name__ == "__main__":
    main()
