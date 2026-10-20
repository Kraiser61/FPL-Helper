# ⚽ FPL Helper & Strategy Assistant

**An intelligent Fantasy Premier League assistant that calculates the best weekly transfers, starting lineups, and chip strategies to maximize your squad's rank.**

---

## 📌 Overview

Managing a Fantasy Premier League (FPL) team requires balancing player form, fixture swings, budgets, and long-term planning. **FPL Helper** takes the stress and guesswork out of manager decisions by transforming complex league statistics into clear, actionable advice.

Instead of spending hours debating transfer moves or captain choices, FPL Helper analyzes player performance forecasts and upcoming match difficulty across an 8-week horizon. It recommends optimal transfer plans, chooses your highest-potential starting eleven, and helps you schedule high-impact chips like Wildcard and Free Hit at the perfect moment.

---

## ✨ Key Highlights

* **📈 Multi-Gameweek Strategy:** Looks up to 8 gameweeks ahead to recommend a forward-thinking transfer roadmap rather than just reacting to the previous week's points.
* **🎯 Optimal Starting XI & Captaincy:** Automatically selects the strongest starting lineup and vice/captain picks to maximize your weekly points return.
* **🃏 Smart Chip Timing:** Analyzes upcoming fixture swings to advise exactly when to play your Wildcard, Free Hit, Bench Boost, or Triple Captain.
* **📱 iOS Shortcuts & Mobile Cards:** Get your personalized team advice on your iPhone or mobile device with a single tap, formatted into clean, glanceable visual cards.
* **🖥️ Modern Desktop Interface:** An easy-to-use desktop dashboard for managers who want to browse fixtures, visualize squad rotations, and review strategy recommendations.
* **⚡ Automated Data Updates:** Pulls the latest Premier League fixture information, team news, and projection models automatically before every deadline.

---

## 🚀 Getting Started

### Prerequisites
* [Python](https://www.python.org/) 3.11 or higher
* Git

### Local Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/Kraiser61/FPL-Helper.git
   cd FPL-Helper
   ```

2. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Launch the desktop application:
   ```bash
   python main.py
   ```

### Headless Analysis
If you only want to generate the latest strategy report without opening the visual interface:
```bash
python export_fpl_analysis.py
```

---

## 📱 Mobile Integration (iOS Shortcuts)

You can view your weekly team recommendations directly on your phone using the Apple Shortcuts app:
1. Open the **Shortcuts** app on your iPhone.
2. Add an action to fetch your generated analysis data (`data/fpl_analysis.json`).
3. Display the interactive cards for instant transfer and lineup suggestions on matchday.

---

## 📄 License
This project is built for personal FPL strategy analysis.
