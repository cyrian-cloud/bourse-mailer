def update_historique(sh, total_valeur, total_investi):
    try:
        ws_hist = sh.worksheet("Historique")
    except:
        print("  Onglet Historique non trouvé")
        return
    today = datetime.date.today().strftime("%d/%m/%Y")
    pnl = round(float(total_valeur - total_investi), 2)
    pnl_pct = round(float(pnl / total_investi * 100), 2) if total_investi and total_investi > 0 else 0.0
    # Sécurité contre NaN/inf
    if pnl_pct != pnl_pct or abs(pnl_pct) == float('inf'):
        pnl_pct = 0.0
    total_valeur = round(float(total_valeur), 2)
    total_investi = round(float(total_investi), 2)
    pnl = round(float(pnl), 2)
    all_dates = ws_hist.col_values(1)
    if today in all_dates:
        row = all_dates.index(today) + 1
        ws_hist.update(f"A{row}:E{row}", [[today, total_valeur, total_investi, pnl, pnl_pct]])
    else:
        ws_hist.append_row([today, total_valeur, total_investi, pnl, pnl_pct])
    print(f"  Historique: {today} — {total_valeur}€")
