import os
import requests

# Fetch secret keys from GitHub Action environment variables
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def check_and_post_odds():
    if not ODDS_API_KEY or not DISCORD_WEBHOOK_URL:
        print("Missing API key or Webhook URL in environment variables!")
        return

    # Fetch live odds from The Odds API
    url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=h2h"
    response = requests.get(url)

    if response.status_code != 200:
        print(f"Failed to fetch odds: {response.status_code}")
        return

    games = response.json()

    if not games:
        print("No active games found right now.")
        return

    # Post a summary alert to Discord
    payload = {
        "username": "Pick Desk Auto Bot",
        "embeds": [
            {
                "title": "⚡ Pick Desk Auto System Active!",
                "description": f"Successfully scanned {len(games)} upcoming games.",
                "color": 3066993,  # Green
                "footer": {"text": "Pick Desk Auto Analytics"}
            }
        ]
    }

    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    print("Discord post status code:", res.status_code)

if __name__ == "__main__":
    check_and_post_odds()
