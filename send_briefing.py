"""
send_briefing.py — Version GitHub Actions
Envoie le mail UNE SEULE FOIS et quitte
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

# Import toutes les fonctions de mailer.py
from mailer import run_daily_briefing

# Lance le briefing une seule fois et quitte
run_daily_briefing()
print("Briefing envoye avec succes!")
sys.exit(0)
