"""
widget.py - Widget bureau Watchlist & Portefeuille
- Position haut gauche au demarrage
- Resume portefeuille fixe en haut
- Zone scrollable pour portefeuille + watchlist
- Boutons Acheter / Vendre / Alertes
- Refresh toutes les 5 minutes
- Mail immediat si alerte franchie
"""

import tkinter as tk
import yfinance as yf
import threading
import json
import os
import smtplib
import subprocess
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

# ── CONFIG ────────────────────────────────────────────────────────────────────
SENDER_EMAIL    = "cyrianhage188@gmail.com"
SENDER_PASSWORD = "afmp gjha uian cawb"
RECEIVER_EMAIL  = "cyrian.hage@hotmail.com"
BASE            = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_FILE  = os.path.join(BASE, "watchlist.json")
PORTFOLIO_FILE  = os.path.join(BASE, "portfolio.json")
REFRESH_SECS    = 300

# ── COULEURS ──────────────────────────────────────────────────────────────────
BG      = "#0a0c12"
BG_CARD = "#12151e"
BG_IN   = "#1a1d28"
BG_HDR  = "#080a10"
ACCENT  = "#00e5b0"
BLUE    = "#4f8ef7"
RED     = "#ff4560"
GREEN   = "#00e5b0"
YELLOW  = "#ffd166"
TEXT    = "#e8eaf0"
DIM     = "#3a3f50"
BORDER  = "#1e2235"
BORDER2 = "#2a2f45"

# ── FICHIERS ──────────────────────────────────────────────────────────────────
def load_watchlist():
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE) as f:
                d = json.load(f)
            if isinstance(d, list):
                return {t: {"alert_high": None, "alert_low": None} for t in d}
            return d
    except Exception:
        pass
    return {}

def save_watchlist(wl):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(wl, f, indent=2)

def load_portfolio():
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(p, f, indent=2)

def git_push_portfolio(message=""):
    """Push portfolio.json sur GitHub après chaque transaction"""
    try:
        repo_dir = BASE
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        commit_msg = f"portfolio: {message} — {now}" if message else f"portfolio: mise a jour {now}"
        subprocess.run(["git", "-C", repo_dir, "add", "portfolio.json"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "commit", "-m", commit_msg],
                       check=True, capture_output=True)
        # Pull --rebase avant push pour eviter les conflits
        subprocess.run(["git", "-C", repo_dir, "pull", "--rebase"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "push"],
                       check=True, capture_output=True)
        print(f"[Git] Push OK — {commit_msg}")
    except subprocess.CalledProcessError as e:
        print(f"[Git] Rien à pusher ou erreur: {e.stderr.decode()[:80] if e.stderr else 'ok'}")
    except Exception as e:
        print(f"[Git] Erreur inattendue: {e}")

def load_strategies():
    sf = os.path.join(BASE, "strategies.json")
    try:
        if os.path.exists(sf):
            with open(sf) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def remove_strategy(ticker):
    sf = os.path.join(BASE, "strategies.json")
    try:
        strats = load_strategies()
        if ticker in strats:
            del strats[ticker]
            with open(sf, "w") as f:
                json.dump(strats, f, indent=2)
    except Exception:
        pass

# ── DONNEES MARCHE ────────────────────────────────────────────────────────────
def get_quick_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist  = stock.history(period="3mo")
        info  = stock.info
        if hist.empty:
            return None
        close = hist["Close"]
        price = round(float(close.iloc[-1]), 2)
        prev  = round(float(close.iloc[-2]), 2)
        chg   = round(((price - prev) / prev) * 100, 2)
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rsi   = round(float((100 - (100 / (1 + gain / loss))).iloc[-1]), 1)
        ma20  = round(float(close.rolling(20).mean().iloc[-1]), 2)
        ma50  = round(float(close.rolling(50).mean().iloc[-1]), 2)
        if rsi < 35 and price > ma20:
            sig, sc = "ACHAT", GREEN
        elif rsi > 65 or price < ma20:
            sig, sc = "PRUDENCE", RED
        elif price > ma20 and ma20 > ma50:
            sig, sc = "HAUSSIER", GREEN
        else:
            sig, sc = "NEUTRE", YELLOW
        name = info.get("shortName", ticker)[:20]
        return {"ticker": ticker, "name": name, "price": price,
                "change": chg, "rsi": rsi, "ma20": ma20,
                "signal": sig, "signal_color": sc}
    except Exception:
        return None

# ── MAILS ─────────────────────────────────────────────────────────────────────
def send_mail(subject, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL
    msg["Date"]    = formatdate(localtime=True)
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(SENDER_EMAIL, SENDER_PASSWORD)
            s.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
    except Exception:
        pass

def make_alert_html(ticker, price, atype, threshold):
    d = "HAUSSE" if atype == "high" else "BAISSE"
    e = "🚀" if atype == "high" else "🔻"
    c = "#27ae60" if atype == "high" else "#e74c3c"
    ts = datetime.now().strftime("%d/%m/%Y a %H:%M")
    return (
        '<!DOCTYPE html><html><body style="font-family:sans-serif;background:#f0f2f5;padding:20px;">'
        '<div style="max-width:480px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;">'
        '<div style="background:#0a0c12;padding:18px;text-align:center;">'
        '<div style="font-size:30px;">' + e + '</div>'
        '<div style="color:white;font-size:18px;font-weight:bold;">ALERTE ' + d + '</div></div>'
        '<div style="padding:22px;text-align:center;">'
        '<div style="font-size:26px;font-weight:bold;">' + ticker + '</div>'
        '<div style="font-size:34px;font-weight:bold;color:' + c + ';margin:10px 0;">$' + str(price) + '</div>'
        '<div style="font-size:13px;color:#666;">Seuil atteint : <strong>$' + str(threshold) + '</strong></div>'
        '<div style="font-size:11px;color:#aaa;margin-top:14px;">' + ts + '</div>'
        '</div></div></body></html>'
    )

def make_transaction_html(action, ticker, qty, price, total, avg=None):
    is_buy = (action == "ACHAT")
    c  = "#27ae60" if is_buy else "#e74c3c"
    e  = "🛒" if is_buy else "💰"
    ts = datetime.now().strftime("%d/%m/%Y a %H:%M")
    items = [
        ("Ticker",       ticker),
        ("Quantite",     str(qty) + " titres"),
        ("Prix unitaire","$" + str(price)),
        ("Montant",      "$" + str(round(total, 2))),
    ]
    if avg:
        items.append(("Cout moyen", "$" + str(round(avg, 2))))
    rows = ""
    for i, (k, v) in enumerate(items):
        bg = ' style="background:#f8f9fa;"' if i % 2 else ""
        mc = "color:" + c + ";" if k == "Montant" else ""
        rows += (
            "<tr" + bg + '><td style="padding:8px;color:#666;">' + k + "</td>"
            '<td style="padding:8px;font-weight:bold;text-align:right;' + mc + '">' + v + "</td></tr>"
        )
    return (
        '<!DOCTYPE html><html><body style="font-family:sans-serif;background:#f0f2f5;padding:20px;">'
        '<div style="max-width:480px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;">'
        '<div style="background:#0a0c12;padding:18px;text-align:center;">'
        '<div style="font-size:30px;">' + e + '</div>'
        '<div style="color:white;font-size:18px;font-weight:bold;">' + action + ' EXECUTE</div></div>'
        '<div style="padding:22px;">'
        '<table style="width:100%;border-collapse:collapse;">' + rows + '</table>'
        '<div style="font-size:11px;color:#aaa;margin-top:14px;text-align:center;">' + ts + '</div>'
        '</div></div></body></html>'
    )

# ── WIDGET ────────────────────────────────────────────────────────────────────
class WatchlistWidget:
    def __init__(self, root):
        self.root      = root
        self.watchlist = load_watchlist()
        self.portfolio = load_portfolio()
        self.cache     = {}
        self.alerted   = set()
        self._setup_window()
        self._build_ui()
        self._start_refresh()

    # ── FENETRE ───────────────────────────────────────────────────────────────
    def _setup_window(self):
        self.root.title("Portfolio")
        self.root.overrideredirect(False)
        self.root.attributes("-topmost", False)
        self.root.attributes("-alpha", 0.97)
        self.root.configure(bg=BG)
        self.root.geometry("355x640+8+8")
        self.root.resizable(True, True)
        self.root.lower()
        self.root.bind("<FocusIn>", lambda e: self.root.lower())

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Barre titre
        tb = tk.Frame(self.root, bg=BG_HDR)
        tb.pack(fill="x")
        tk.Label(tb, text="  PORTFOLIO", font=("Consolas", 10, "bold"),
                 bg=BG_HDR, fg=ACCENT).pack(side="left", pady=7)
        self.time_lbl = tk.Label(tb, text="", font=("Consolas", 8),
                                  bg=BG_HDR, fg=DIM)
        self.time_lbl.pack(side="right", padx=10)
        self.status_lbl = tk.Label(tb, text="", font=("Consolas", 8),
                                    bg=BG_HDR, fg=DIM)
        self.status_lbl.pack(side="right")

        # Resume fixe
        self.summary_frame = tk.Frame(self.root, bg="#0d1018",
                                       highlightbackground=BORDER2,
                                       highlightthickness=1)
        self.summary_frame.pack(fill="x", padx=8, pady=(6, 4))
        self._build_summary()

        # Input ticker
        inp = tk.Frame(self.root, bg=BG_IN,
                       highlightbackground=BORDER2, highlightthickness=1)
        inp.pack(fill="x", padx=8, pady=(0, 6))
        self.var = tk.StringVar()
        self.entry = tk.Entry(inp, textvariable=self.var,
                               font=("Consolas", 9), bg=BG_IN, fg=DIM,
                               insertbackground=ACCENT, relief="flat", bd=7)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.insert(0, "Ajouter ticker...")
        self.entry.bind("<FocusIn>",  self._clear_ph)
        self.entry.bind("<FocusOut>", self._restore_ph)
        self.entry.bind("<Return>",   self._add)
        ab = tk.Label(inp, text=" + ", font=("Consolas", 10, "bold"),
                       bg=ACCENT, fg=BG, cursor="hand2", padx=6, pady=4)
        ab.pack(side="right")
        ab.bind("<Button-1>", self._add)

        # Zone scrollable
        sc = tk.Frame(self.root, bg=BG)
        sc.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = tk.Canvas(sc, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(sc, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.cards_frame = tk.Frame(self.canvas, bg=BG)
        self.cw = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.cards_frame.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
            lambda e: self.canvas.itemconfig(self.cw, width=e.width))
        self.canvas.bind("<MouseWheel>",
            lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def _clear_ph(self, e):
        if "Ajouter" in self.var.get():
            self.entry.delete(0, "end")
            self.entry.config(fg=TEXT)

    def _restore_ph(self, e):
        if not self.var.get():
            self.entry.insert(0, "Ajouter ticker...")
            self.entry.config(fg=DIM)

    # ── RESUME ────────────────────────────────────────────────────────────────
    def _build_summary(self):
        for w in self.summary_frame.winfo_children():
            w.destroy()
        pf = load_portfolio()
        total_inv = 0
        total_val = 0
        for ticker, meta in pf.items():
            cost = meta.get("cost", 0)
            qty  = meta.get("qty", 0)
            total_inv += cost * qty
            data = self.cache.get(ticker)
            total_val += (data["price"] * qty) if data else (cost * qty)
        gain     = total_val - total_inv
        gain_pct = (gain / total_inv * 100) if total_inv > 0 else 0
        gc       = GREEN if gain_pct >= 0 else RED
        arrow    = "▲" if gain_pct >= 0 else "▼"

        row = tk.Frame(self.summary_frame, bg="#0d1018")
        row.pack(fill="x", padx=10, pady=8)

        for label, value, color in [
            ("INVESTI",  "$" + "{:,.0f}".format(total_inv), TEXT),
            ("VALEUR",   "$" + "{:,.0f}".format(total_val), TEXT),
            ("PERF",     arrow + " " + "{:.1f}".format(abs(gain_pct)) + "%", gc),
        ]:
            col = tk.Frame(row, bg="#0d1018")
            col.pack(side="left", expand=True)
            tk.Label(col, text=label, font=("Consolas", 7),
                     bg="#0d1018", fg=DIM).pack()
            tk.Label(col, text=value, font=("Consolas", 11, "bold"),
                     bg="#0d1018", fg=color).pack()
            if label != "PERF":
                tk.Frame(row, bg=BORDER2, width=1).pack(side="left", fill="y", padx=4)

        sub = tk.Frame(self.summary_frame, bg="#0d1018")
        sub.pack(fill="x", padx=10, pady=(0, 8))
        tk.Label(sub,
                 text=str(len(pf)) + " positions  |  P&L: " + "{:+,.0f}".format(gain) + "$",
                 font=("Consolas", 8), bg="#0d1018", fg=DIM).pack()

    # ── RENDER ────────────────────────────────────────────────────────────────
    def _render(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()
        self._update_time()
        self._build_summary()
        self.portfolio = load_portfolio()

        if self.portfolio:
            self._section("PORTEFEUILLE  (" + str(len(self.portfolio)) + ")")
            for t in self.portfolio:
                self._make_card(t, True)

        wl_only = [t for t in self.watchlist if t not in self.portfolio]
        if wl_only:
            self._section("WATCHLIST  (" + str(len(wl_only)) + ")")
            for t in wl_only:
                self._make_card(t, False)

        if not self.portfolio and not self.watchlist:
            tk.Label(self.cards_frame,
                     text="Aucun ticker\nTape un symbole ci-dessus",
                     font=("Consolas", 9), bg=BG, fg=DIM,
                     justify="center").pack(pady=30)

    def _section(self, text):
        f = tk.Frame(self.cards_frame, bg=BG)
        f.pack(fill="x", pady=(8, 2))
        tk.Label(f, text=text, font=("Consolas", 7, "bold"),
                 bg=BG, fg=DIM).pack(side="left")
        tk.Frame(f, bg=BORDER2, height=1).pack(
            side="left", fill="x", expand=True, padx=6, pady=5)

    def _make_card(self, ticker, is_portfolio):
        data    = self.cache.get(ticker)
        pf_data = self.portfolio.get(ticker, {})
        wl_meta = self.watchlist.get(ticker, {})

        card = tk.Frame(self.cards_frame, bg=BG_CARD,
                        highlightbackground=BLUE if is_portfolio else BORDER2,
                        highlightthickness=1)
        card.pack(fill="x", pady=2)
        for w in [card]:
            w.bind("<MouseWheel>",
                   lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Ligne 1 : ticker + prix
        r1 = tk.Frame(card, bg=BG_CARD)
        r1.pack(fill="x", padx=10, pady=(7, 2))
        tk.Label(r1, text=ticker, font=("Consolas", 10, "bold"),
                 bg=BG_CARD, fg=BLUE if is_portfolio else TEXT).pack(side="left")
        if not is_portfolio:
            dl = tk.Label(r1, text="✕", font=("Consolas", 9),
                          bg=BG_CARD, fg=DIM, cursor="hand2")
            dl.pack(side="right")
            dl.bind("<Button-1>", lambda e, t=ticker: self._remove(t))

        if data:
            tk.Label(r1, text="$" + str(data["price"]),
                     font=("Consolas", 10, "bold"),
                     bg=BG_CARD, fg=TEXT).pack(side="right", padx=(0, 6))

            # Ligne 2 : nom + variation + PV
            r2 = tk.Frame(card, bg=BG_CARD)
            r2.pack(fill="x", padx=10, pady=(0, 2))
            tk.Label(r2, text=data["name"], font=("Consolas", 8),
                     bg=BG_CARD, fg=DIM).pack(side="left")
            chg = data["change"]
            cc  = GREEN if chg >= 0 else RED
            tk.Label(r2,
                     text=("▲" if chg >= 0 else "▼") + " " + "{:.2f}".format(abs(chg)) + "%",
                     font=("Consolas", 8, "bold"), bg=BG_CARD, fg=cc).pack(side="right")
            if is_portfolio and pf_data:
                cost = pf_data.get("cost", 0)
                qty  = pf_data.get("qty", 0)
                pv   = ((data["price"] - cost) / cost * 100) if cost > 0 else 0
                pvc  = GREEN if pv >= 0 else RED
                tk.Label(r2,
                         text="PV " + "{:+.1f}".format(pv) + "% x" + str(qty),
                         font=("Consolas", 8), bg=BG_CARD, fg=pvc).pack(side="right", padx=8)

            # Ligne 3 : RSI + signal + boutons
            r3 = tk.Frame(card, bg=BG_CARD)
            r3.pack(fill="x", padx=10, pady=(2, 7))
            tk.Label(r3, text="RSI " + str(data["rsi"]),
                     font=("Consolas", 7), bg=BG_CARD, fg=DIM).pack(side="left")
            sf = tk.Frame(r3, bg=data["signal_color"])
            sf.pack(side="left", padx=4)
            tk.Label(sf, text=" " + data["signal"] + " ",
                     font=("Consolas", 7, "bold"),
                     bg=data["signal_color"], fg=BG).pack()

            bf = tk.Frame(r3, bg=BG_CARD)
            bf.pack(side="right")

            if is_portfolio:
                sl = tk.Label(bf, text="VENDRE",
                              font=("Consolas", 7, "bold"),
                              bg=RED, fg=TEXT, cursor="hand2", padx=5, pady=2)
                sl.pack(side="right", padx=2)
                sl.bind("<Button-1>", lambda e, t=ticker: self._sell_dialog(t))

            bl = tk.Label(bf, text="ACHETER",
                          font=("Consolas", 7, "bold"),
                          bg=GREEN, fg=BG, cursor="hand2", padx=5, pady=2)
            bl.pack(side="right", padx=2)
            bl.bind("<Button-1>", lambda e, t=ticker: self._buy_dialog(t))

            if not is_portfolio:
                ah = wl_meta.get("alert_high")
                al = wl_meta.get("alert_low")
                alc = YELLOW if (ah or al) else DIM
                all_btn = tk.Label(bf, text="🔔",
                                   font=("Consolas", 9),
                                   bg=BG_CARD, fg=alc, cursor="hand2")
                all_btn.pack(side="right", padx=2)
                all_btn.bind("<Button-1>", lambda e, t=ticker: self._set_alert(t))
        else:
            tk.Label(r1, text="chargement...",
                     font=("Consolas", 8), bg=BG_CARD, fg=DIM).pack(side="right", padx=8)
            tk.Frame(card, bg=BG_CARD, height=4).pack()

    # ── ACTIONS ───────────────────────────────────────────────────────────────
    def _add(self, e=None):
        raw = self.var.get().strip().upper()
        if raw and "AJOUTER" not in raw and raw not in self.watchlist:
            self.watchlist[raw] = {"alert_high": None, "alert_low": None}
            save_watchlist(self.watchlist)
            self.entry.delete(0, "end")
            self.status_lbl.config(text="Chargement " + raw + "...", fg=ACCENT)
            threading.Thread(target=self._load_one, args=(raw,), daemon=True).start()

    def _remove(self, ticker):
        if ticker in self.watchlist:
            del self.watchlist[ticker]
        if ticker in self.cache:
            del self.cache[ticker]
        save_watchlist(self.watchlist)
        self._render()

    def _load_one(self, ticker):
        d = get_quick_data(ticker)
        if d:
            self.cache[ticker] = d
            self._check_alerts(ticker, d)
        self.root.after(0, self._render)
        self.root.after(0, lambda: self.status_lbl.config(text=""))

    def _check_alerts(self, ticker, data):
        meta  = self.watchlist.get(ticker, {})
        price = data["price"]
        ah    = meta.get("alert_high")
        al    = meta.get("alert_low")
        if ah and price >= ah and ticker + "_high" not in self.alerted:
            self.alerted.add(ticker + "_high")
            html = make_alert_html(ticker, price, "high", ah)
            threading.Thread(
                target=send_mail,
                args=("🚀 ALERTE HAUSSE : " + ticker + " a $" + str(price), html),
                daemon=True).start()
            self.root.after(0, lambda: self.status_lbl.config(
                text="Alerte hausse " + ticker + "!", fg=GREEN))
        if al and price <= al and ticker + "_low" not in self.alerted:
            self.alerted.add(ticker + "_low")
            html = make_alert_html(ticker, price, "low", al)
            threading.Thread(
                target=send_mail,
                args=("🔻 ALERTE BAISSE : " + ticker + " a $" + str(price), html),
                daemon=True).start()
            self.root.after(0, lambda: self.status_lbl.config(
                text="Alerte baisse " + ticker + "!", fg=RED))

    # ── DIALOGS ───────────────────────────────────────────────────────────────
    def _buy_dialog(self, ticker):
        data = self.cache.get(ticker)
        dlg  = tk.Toplevel(self.root)
        dlg.title("Achat — " + ticker)
        dlg.configure(bg=BG)
        dlg.geometry("260x230")
        dlg.grab_set()

        tk.Label(dlg, text="ACHAT — " + ticker,
                 font=("Consolas", 10, "bold"), bg=BG, fg=GREEN).pack(pady=(14, 2))
        if data:
            tk.Label(dlg, text="Cours : $" + str(data["price"]),
                     font=("Consolas", 8), bg=BG, fg=DIM).pack()

        tk.Label(dlg, text="Prix achat ($)",
                 font=("Consolas", 9), bg=BG, fg=TEXT).pack(pady=(10, 2))
        pv = tk.StringVar(value=str(data["price"]) if data else "")
        tk.Entry(dlg, textvariable=pv, font=("Consolas", 10),
                 bg=BG_IN, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", bd=6, width=14).pack()

        tk.Label(dlg, text="Quantite",
                 font=("Consolas", 9), bg=BG, fg=TEXT).pack(pady=(8, 2))
        qv = tk.StringVar(value="1")
        tk.Entry(dlg, textvariable=qv, font=("Consolas", 10),
                 bg=BG_IN, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", bd=6, width=14).pack()

        err = tk.Label(dlg, text="", font=("Consolas", 8), bg=BG, fg=RED)
        err.pack()

        def confirm():
            try:
                p = float(pv.get())
                q = int(qv.get())
                if p <= 0 or q <= 0:
                    raise ValueError
                pf = load_portfolio()
                if ticker in pf:
                    oq  = pf[ticker]["qty"]
                    oc  = pf[ticker]["cost"]
                    nq  = oq + q
                    nc  = round((oc * oq + p * q) / nq, 4)
                    pf[ticker]["qty"]  = nq
                    pf[ticker]["cost"] = nc
                    avg = nc
                else:
                    pf[ticker] = {"cost": p, "qty": q, "currency": "USD"}
                    avg = p
                if "pending" in pf.get(ticker, {}):
                    del pf[ticker]["pending"]
                save_portfolio(pf)
                # Auto-push GitHub pour sync avec GitHub Actions
                threading.Thread(
                    target=git_push_portfolio,
                    args=(f"achat {q}x {ticker} a ${p}",),
                    daemon=True).start()
                remove_strategy(ticker)
                if ticker in self.watchlist:
                    del self.watchlist[ticker]
                    save_watchlist(self.watchlist)
                if ticker in self.cache:
                    del self.cache[ticker]
                html = make_transaction_html("ACHAT", ticker, q, p, p * q, avg)
                threading.Thread(
                    target=send_mail,
                    args=("🛒 ACHAT " + str(q) + "x " + ticker + " a $" + str(p), html),
                    daemon=True).start()
                self.status_lbl.config(text="Achat " + ticker + " enregistre! (sync GitHub...)", fg=GREEN)
                dlg.destroy()
                self._render()
            except ValueError:
                err.config(text="Valeurs invalides")

        tk.Button(dlg, text="Confirmer", font=("Consolas", 9, "bold"),
                  bg=GREEN, fg=BG, relief="flat", padx=14, pady=6,
                  cursor="hand2", command=confirm).pack(pady=10)

    def _sell_dialog(self, ticker):
        data  = self.cache.get(ticker)
        pfd   = self.portfolio.get(ticker, {})
        dlg   = tk.Toplevel(self.root)
        dlg.title("Vente — " + ticker)
        dlg.configure(bg=BG)
        dlg.geometry("260x250")
        dlg.grab_set()

        tk.Label(dlg, text="VENTE — " + ticker,
                 font=("Consolas", 10, "bold"), bg=BG, fg=RED).pack(pady=(14, 2))
        if data:
            tk.Label(dlg, text="Cours : $" + str(data["price"]),
                     font=("Consolas", 8), bg=BG, fg=DIM).pack()
        if pfd and data:
            pv2 = ((data["price"] - pfd.get("cost", 0)) / pfd.get("cost", 1) * 100)
            gc  = GREEN if pv2 >= 0 else RED
            tk.Label(dlg,
                     text=str(pfd.get("qty", 0)) + " titres | PV " + "{:+.1f}".format(pv2) + "%",
                     font=("Consolas", 8), bg=BG, fg=gc).pack()

        tk.Label(dlg, text="Prix vente ($)",
                 font=("Consolas", 9), bg=BG, fg=TEXT).pack(pady=(10, 2))
        price_v = tk.StringVar(value=str(data["price"]) if data else "")
        tk.Entry(dlg, textvariable=price_v, font=("Consolas", 10),
                 bg=BG_IN, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", bd=6, width=14).pack()

        max_q = pfd.get("qty", 0)
        tk.Label(dlg, text="Quantite (max " + str(max_q) + ")",
                 font=("Consolas", 9), bg=BG, fg=TEXT).pack(pady=(8, 2))
        qty_v = tk.StringVar(value=str(max_q))
        tk.Entry(dlg, textvariable=qty_v, font=("Consolas", 10),
                 bg=BG_IN, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", bd=6, width=14).pack()

        err = tk.Label(dlg, text="", font=("Consolas", 8), bg=BG, fg=RED)
        err.pack()

        def confirm():
            try:
                p = float(price_v.get())
                q = int(qty_v.get())
                if p <= 0 or q <= 0 or q > max_q:
                    raise ValueError
                pf        = load_portfolio()
                remaining = pf[ticker]["qty"] - q
                if remaining <= 0:
                    del pf[ticker]
                else:
                    pf[ticker]["qty"] = remaining
                save_portfolio(pf)
                # Auto-push GitHub pour sync avec GitHub Actions
                threading.Thread(
                    target=git_push_portfolio,
                    args=(f"vente {q}x {ticker} a ${p}",),
                    daemon=True).start()
                # Si tous les titres vendus, supprime la strategie
                if remaining <= 0:
                    remove_strategy(ticker)
                html = make_transaction_html("VENTE", ticker, q, p, p * q)
                threading.Thread(
                    target=send_mail,
                    args=("💰 VENTE " + str(q) + "x " + ticker + " a $" + str(p), html),
                    daemon=True).start()
                self.status_lbl.config(text="Vente " + ticker + " enregistree! (sync GitHub...)", fg=YELLOW)
                dlg.destroy()
                self._render()
            except ValueError:
                err.config(text="Valeur invalide")

        tk.Button(dlg, text="Confirmer", font=("Consolas", 9, "bold"),
                  bg=RED, fg=TEXT, relief="flat", padx=14, pady=6,
                  cursor="hand2", command=confirm).pack(pady=10)

    def _set_alert(self, ticker):
        meta = self.watchlist.get(ticker, {})
        data = self.cache.get(ticker)
        dlg  = tk.Toplevel(self.root)
        dlg.title("Alertes — " + ticker)
        dlg.configure(bg=BG)
        dlg.geometry("260x200")
        dlg.grab_set()

        tk.Label(dlg, text="Alertes — " + ticker,
                 font=("Consolas", 10, "bold"), bg=BG, fg=ACCENT).pack(pady=(14, 2))
        if data:
            tk.Label(dlg, text="Cours : $" + str(data["price"]),
                     font=("Consolas", 8), bg=BG, fg=DIM).pack()

        tk.Label(dlg, text="Alerte HAUSSE ($)",
                 font=("Consolas", 9), bg=BG, fg=GREEN).pack(pady=(10, 2))
        hv = tk.StringVar(value=str(meta.get("alert_high") or ""))
        tk.Entry(dlg, textvariable=hv, font=("Consolas", 10),
                 bg=BG_IN, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", bd=6, width=14).pack()

        tk.Label(dlg, text="Alerte BAISSE ($)",
                 font=("Consolas", 9), bg=BG, fg=RED).pack(pady=(8, 2))
        lv = tk.StringVar(value=str(meta.get("alert_low") or ""))
        tk.Entry(dlg, textvariable=lv, font=("Consolas", 10),
                 bg=BG_IN, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", bd=6, width=14).pack()

        def save():
            try:
                h = float(hv.get()) if hv.get().strip() else None
                l = float(lv.get()) if lv.get().strip() else None
                if ticker not in self.watchlist:
                    self.watchlist[ticker] = {}
                self.watchlist[ticker]["alert_high"] = h
                self.watchlist[ticker]["alert_low"]  = l
                save_watchlist(self.watchlist)
                self.alerted.discard(ticker + "_high")
                self.alerted.discard(ticker + "_low")
                dlg.destroy()
                self._render()
            except Exception:
                pass

        tk.Button(dlg, text="Enregistrer", font=("Consolas", 9, "bold"),
                  bg=ACCENT, fg=BG, relief="flat", padx=14, pady=6,
                  cursor="hand2", command=save).pack(pady=10)

    # ── REFRESH ───────────────────────────────────────────────────────────────
    def _update_time(self):
        self.time_lbl.config(text=datetime.now().strftime("%H:%M"))

    def _start_refresh(self):
        def initial():
            all_t = list(set(list(self.portfolio.keys()) + list(self.watchlist.keys())))
            for t in all_t:
                d = get_quick_data(t)
                if d:
                    self.cache[t] = d
                    self._check_alerts(t, d)
            self.root.after(0, self._render)
            self.root.after(0, lambda: self.status_lbl.config(text=""))
        self.status_lbl.config(text="Chargement...", fg=ACCENT)
        threading.Thread(target=initial, daemon=True).start()
        self._schedule_next()

    def _schedule_next(self):
        def refresh():
            self.root.after(0, lambda: self.status_lbl.config(text="Refresh...", fg=DIM))
            pf    = load_portfolio()
            all_t = list(set(list(pf.keys()) + list(self.watchlist.keys())))
            for t in all_t:
                d = get_quick_data(t)
                if d:
                    self.cache[t] = d
                    self._check_alerts(t, d)
            self.root.after(0, self._render)
            self.root.after(0, lambda: self.status_lbl.config(text=""))
            self.root.after(REFRESH_SECS * 1000, self._schedule_next)
        self.root.after(
            REFRESH_SECS * 1000,
            lambda: threading.Thread(target=refresh, daemon=True).start())


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    WatchlistWidget(root)
    root.mainloop()
