import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────
SCREENER_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    "JPM", "JNJ", "V", "PG", "UNH", "HD", "MA", "BAC", "XOM", "PFE",
    "COST", "DIS", "NFLX", "AMD", "INTC", "CSCO", "ADBE", "CRM", "PYPL",
    "UBER", "SPOT", "SHOP"
]

# ─────────────────────────────────────────
#  ANALYSE TECHNIQUE
# ─────────────────────────────────────────
def technical_analysis(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    hist = stock.history(period="6mo")
    if hist.empty:
        return None

    close = hist['Close']
    volume = hist['Volume']

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # Moyennes mobiles
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean() if len(close) >= 200 else pd.Series([None]*len(close))

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    macd_hist = macd - signal

    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    price = close.iloc[-1]
    prev_price = close.iloc[-2]

    # Score technique
    score = 0
    signals = []

    rsi_val = rsi.iloc[-1]
    if rsi_val < 30:
        score += 2
        signals.append("RSI survendu (achat)")
    elif rsi_val > 70:
        score -= 2
        signals.append("RSI suracheté (attention)")
    
    if price > ma20.iloc[-1]:
        score += 1
        signals.append("Au-dessus MA20")
    if ma20.iloc[-1] > ma50.iloc[-1]:
        score += 1
        signals.append("MA20 > MA50 (trend haussier)")
    if macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] < 0:
        score += 2
        signals.append("Croisement MACD haussier")
    if price < bb_lower.iloc[-1]:
        score += 1
        signals.append("Sous bande de Bollinger basse")

    vol_avg = volume.rolling(20).mean().iloc[-1]
    if volume.iloc[-1] > vol_avg * 1.5:
        signals.append("Volume anormal (x1.5)")

    change_1d = ((price - prev_price) / prev_price) * 100
    change_1m = ((price - close.iloc[-21]) / close.iloc[-21]) * 100 if len(close) > 21 else 0

    return {
        "price": round(price, 2),
        "change_1d": round(change_1d, 2),
        "change_1m": round(change_1m, 2),
        "rsi": round(rsi_val, 1),
        "macd": round(macd.iloc[-1], 3),
        "ma20": round(ma20.iloc[-1], 2),
        "ma50": round(ma50.iloc[-1], 2),
        "bb_upper": round(bb_upper.iloc[-1], 2),
        "bb_lower": round(bb_lower.iloc[-1], 2),
        "tech_score": score,
        "signals": signals
    }

# ─────────────────────────────────────────
#  ANALYSE FONDAMENTALE
# ─────────────────────────────────────────
def fundamental_analysis(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    info = stock.info

    def safe_get(key, default=None):
        val = info.get(key, default)
        return val if val not in [None, 'N/A', float('inf')] else default

    pe = safe_get('trailingPE')
    fwd_pe = safe_get('forwardPE')
    pb = safe_get('priceToBook')
    ps = safe_get('priceToSalesTrailing12Months')
    roe = safe_get('returnOnEquity')
    roa = safe_get('returnOnAssets')
    profit_margin = safe_get('profitMargins')
    debt_equity = safe_get('debtToEquity')
    current_ratio = safe_get('currentRatio')
    rev_growth = safe_get('revenueGrowth')
    earnings_growth = safe_get('earningsGrowth')
    market_cap = safe_get('marketCap')
    dividend_yield = safe_get('dividendYield')
    sector = safe_get('sector', 'N/A')
    name = safe_get('longName', ticker)

    # Score fondamental
    score = 0
    signals = []

    if pe and pe < 20:
        score += 1
        signals.append(f"P/E attractif ({pe:.1f})")
    elif pe and pe > 40:
        score -= 1
        signals.append(f"P/E élevé ({pe:.1f})")

    if fwd_pe and pe and fwd_pe < pe:
        score += 1
        signals.append("Croissance bénéfices attendue")

    if roe and roe > 0.15:
        score += 2
        signals.append(f"ROE excellent ({roe*100:.1f}%)")

    if profit_margin and profit_margin > 0.20:
        score += 1
        signals.append(f"Marge nette forte ({profit_margin*100:.1f}%)")

    if debt_equity and debt_equity < 50:
        score += 1
        signals.append("Faible endettement")
    elif debt_equity and debt_equity > 200:
        score -= 1
        signals.append("Endettement élevé")

    if rev_growth and rev_growth > 0.10:
        score += 1
        signals.append(f"Croissance CA: +{rev_growth*100:.1f}%")

    def fmt(val, pct=False, suffix=""):
        if val is None:
            return "N/A"
        if pct:
            return f"{val*100:.1f}%"
        if suffix == "B" and val:
            return f"${val/1e9:.1f}B"
        return f"{val:.2f}"

    return {
        "name": name,
        "sector": sector,
        "market_cap": fmt(market_cap, suffix="B"),
        "pe": fmt(pe),
        "fwd_pe": fmt(fwd_pe),
        "pb": fmt(pb),
        "roe": fmt(roe, pct=True),
        "profit_margin": fmt(profit_margin, pct=True),
        "debt_equity": fmt(debt_equity),
        "rev_growth": fmt(rev_growth, pct=True),
        "dividend_yield": fmt(dividend_yield, pct=True),
        "fund_score": score,
        "signals": signals
    }

# ─────────────────────────────────────────
#  ANALYSE COMPLÈTE D'UNE ACTION
# ─────────────────────────────────────────
def analyze_stock(ticker: str):
    ticker = ticker.upper()
    print(f"\n{'='*60}")
    print(f"  📊 ANALYSE COMPLÈTE : {ticker}")
    print(f"{'='*60}")

    print("\n⏳ Récupération des données...")
    tech = technical_analysis(ticker)
    fund = fundamental_analysis(ticker)

    if not tech:
        print("❌ Impossible de récupérer les données pour ce ticker.")
        return

    print(f"\n🏢 {fund['name']} — {fund['sector']}")
    print(f"   Market Cap: {fund['market_cap']}")

    print(f"\n📈 PRIX & PERFORMANCE")
    print(f"   Prix actuel : ${tech['price']}")
    print(f"   Variation 1j : {tech['change_1d']:+.2f}%")
    print(f"   Variation 1m : {tech['change_1m']:+.2f}%")

    print(f"\n🔧 ANALYSE TECHNIQUE  (score: {tech['tech_score']:+d})")
    print(f"   RSI         : {tech['rsi']} {'🟢 Survendu' if tech['rsi'] < 30 else '🔴 Suracheté' if tech['rsi'] > 70 else '⚪ Neutre'}")
    print(f"   MACD        : {tech['macd']}")
    print(f"   MA20 / MA50 : ${tech['ma20']} / ${tech['ma50']}")
    print(f"   Bollinger   : ${tech['bb_lower']} — ${tech['bb_upper']}")
    for s in tech['signals']:
        print(f"   ✦ {s}")

    print(f"\n💰 ANALYSE FONDAMENTALE  (score: {fund['fund_score']:+d})")
    print(f"   P/E (trail/fwd) : {fund['pe']} / {fund['fwd_pe']}")
    print(f"   P/B             : {fund['pb']}")
    print(f"   ROE             : {fund['roe']}")
    print(f"   Marge nette     : {fund['profit_margin']}")
    print(f"   Dette/Equity    : {fund['debt_equity']}")
    print(f"   Croissance CA   : {fund['rev_growth']}")
    print(f"   Dividende       : {fund['dividend_yield']}")
    for s in fund['signals']:
        print(f"   ✦ {s}")

    total_score = tech['tech_score'] + fund['fund_score']
    print(f"\n🎯 SCORE GLOBAL : {total_score:+d}/10")
    if total_score >= 6:
        verdict = "🟢 OPPORTUNITÉ INTÉRESSANTE"
    elif total_score >= 3:
        verdict = "🟡 NEUTRE — À SURVEILLER"
    elif total_score >= 0:
        verdict = "🟠 PRUDENCE"
    else:
        verdict = "🔴 ÉVITER"
    print(f"   {verdict}")
    print(f"\n⚠️  Ceci n'est pas un conseil financier.")

# ─────────────────────────────────────────
#  SCREENER — TOP OPPORTUNITÉS
# ─────────────────────────────────────────
def run_screener(tickers=None, top_n=10):
    if tickers is None:
        tickers = SCREENER_TICKERS

    print(f"\n{'='*60}")
    print(f"  🔍 SCREENER WALL STREET — {len(tickers)} actions analysées")
    print(f"{'='*60}\n")

    results = []
    for i, ticker in enumerate(tickers):
        print(f"  Analyse {ticker}... ({i+1}/{len(tickers)})", end='\r')
        try:
            tech = technical_analysis(ticker)
            fund = fundamental_analysis(ticker)
            if tech and fund:
                total = tech['tech_score'] + fund['fund_score']
                results.append({
                    "ticker": ticker,
                    "name": fund['name'][:25],
                    "price": tech['price'],
                    "change_1d": tech['change_1d'],
                    "rsi": tech['rsi'],
                    "pe": fund['pe'],
                    "roe": fund['roe'],
                    "score": total
                })
        except:
            pass

    results.sort(key=lambda x: x['score'], reverse=True)

    print(f"\n🏆 TOP {top_n} OPPORTUNITÉS\n")
    print(f"{'Ticker':<8} {'Nom':<26} {'Prix':>8} {'1j%':>6} {'RSI':>6} {'P/E':>6} {'ROE':>7} {'Score':>6}")
    print("-" * 80)

    for r in results[:top_n]:
        print(f"{r['ticker']:<8} {r['name']:<26} ${r['price']:>7} {r['change_1d']:>+5.1f}% {r['rsi']:>5.1f} {r['pe']:>6} {r['roe']:>7} {r['score']:>+5d}")

    print(f"\n📉 TOP {top_n//2} À ÉVITER\n")
    print(f"{'Ticker':<8} {'Nom':<26} {'Prix':>8} {'Score':>6}")
    print("-" * 50)
    for r in results[-top_n//2:]:
        print(f"{r['ticker']:<8} {r['name']:<26} ${r['price']:>7} {r['score']:>+5d}")

    print(f"\n⚠️  Ceci n'est pas un conseil financier.")
    return results

# ─────────────────────────────────────────
#  MAIN — MENU INTERACTIF
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  💹 WALL STREET ANALYZER — Powered by Claude")
    print("="*60)
    print("\n  1. Analyser une action spécifique")
    print("  2. Lancer le screener (top opportunités)")
    print("  3. Les deux\n")

    choice = input("Ton choix (1/2/3) : ").strip()

    if choice in ["1", "3"]:
        tickers_input = input("\nEntre les tickers séparés par virgule (ex: AAPL,MSFT,TSLA) : ")
        tickers = [t.strip().upper() for t in tickers_input.split(",")]
        for t in tickers:
            analyze_stock(t)

    if choice in ["2", "3"]:
        custom = input("\nTickers personnalisés pour le screener ? (Enter pour liste par défaut) : ").strip()
        if custom:
            custom_list = [t.strip().upper() for t in custom.split(",")]
            run_screener(custom_list)
        else:
            run_screener()
