import requests
import time
import json
import os

GAMELIST_URL = "https://api.rolimons.com/games/v1/gamelist"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL_SECONDS", "300"))
STATE_FILE = os.environ.get("STATE_FILE", "known_games.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.rolimons.com/",
}

CAPTION_SYSTEM_PROMPT = (
    "انت تكتب كابشن قصير لقناة تيليكرام تعلن عن ماب (لعبة روبلوكس) جديد ظهر على "
    "موقع Rolimons. اكتب بالعربي، سطرين لثلاثة كحد أقصى، بأسلوب حماسي بس مو مبالغ فيه، "
    "بدون هاشتاقات، وبدون اختلاق معلومات مو معطاة لك عن اللعبة. لازم يتضمن اسم اللعبة "
    "بالضبط زي ما انعطى لك. رد بالكابشن فقط، بدون أي شرح إضافي."
)


def load_known_ids():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    return None  # None = first run, no state yet


def save_known_ids(ids):
    with open(STATE_FILE, "w") as f:
        json.dump(list(ids), f)


def fetch_games():
    resp = requests.get(GAMELIST_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()["games"]


def generate_caption(name, players, game_link):
    """Ask Groq to write the caption instead of using a fixed template."""
    user_msg = (
        f"اسم اللعبة: {name}\n"
        f"عدد اللاعبين الحاليين: {players}\n"
        f"الرابط: {game_link}"
    )
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": CAPTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "max_tokens": 150,
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    try:
        r = requests.post(GROQ_URL, json=payload, headers=headers, timeout=20)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        return f"{text}\n{game_link}"
    except Exception as e:
        print(f"[warn] Groq caption failed, falling back to template: {e}")
        return f"🆕 ماب جديد على Rolimons\n{name}\n{game_link}"


def send_telegram_photo(game_id, name, players, icon_url):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    game_link = f"https://www.roblox.com/games/{game_id}"
    caption = generate_caption(name, players, game_link)
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": icon_url,
        "caption": caption,
    }
    r = requests.post(url, data=payload, timeout=15)
    if not r.ok:
        print(f"[warn] failed to send for {game_id}: {r.text}")


def main():
    known_ids = load_known_ids()

    if known_ids is None:
        # First run ever: just capture the current state, don't spam
        # the channel with every existing game.
        games = fetch_games()
        known_ids = set(games.keys())
        save_known_ids(known_ids)
        print(f"[init] captured {len(known_ids)} existing games, will only report new ones from now on")

    print(f"[start] watching for new games every {CHECK_INTERVAL}s")

    while True:
        try:
            games = fetch_games()
            current_ids = set(games.keys())
            new_ids = current_ids - known_ids

            for gid in new_ids:
                name, players, icon = games[gid]
                print(f"[new] {name} ({gid})")
                send_telegram_photo(gid, name, players, icon)

            known_ids = current_ids
            save_known_ids(known_ids)
        except Exception as e:
            print(f"[error] {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
