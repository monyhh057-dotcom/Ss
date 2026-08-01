import os
import json
import asyncio
import logging

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rolimons-bot")

# ---------------------------------------------------------------- config --

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]  # where auto-broadcasts go
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL_SECONDS", "300"))
STATE_FILE = os.environ.get("STATE_FILE", "known_games.json")
INITIAL_SEND_COUNT = int(os.environ.get("INITIAL_SEND_COUNT", "10"))
MAX_HISTORY = 12  # user+assistant turns kept per chat, keeps token usage bounded

GAMELIST_URL = "https://api.rolimons.com/games/v1/gamelist"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
PLACE_TO_UNIVERSE_URL = "https://apis.roblox.com/universes/v1/places/{}/universe"
GAME_ICONS_URL = "https://thumbnails.roblox.com/v1/games/icons"

ROLIMONS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.rolimons.com/",
}

CHAT_SYSTEM_PROMPT = (
    "انت مساعد داخل بوت تيليكرام شخصي لمستخدم اسمه Zeze، متخصص بمتابعة مابات "
    "(ألعاب) روبلوكس عن طريق موقع Rolimons. جاوب بنفس لغة المستخدم (عربي أو "
    "انجليزي) بأسلوب طبيعي ومباشر، بدون حشو. عندك أداة search_rolimons_game، "
    "استخدمها لما حد يسأل عن ماب معين بالاسم بدل ما تختلق معلومات عنه. لأي "
    "حديث أو سؤال عام ثاني جاوب بشكل طبيعي زي أي محادثة عادية."
)

SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_rolimons_game",
        "description": "يبحث عن ماب (لعبة روبلوكس) بالاسم داخل قائمة Rolimons ويرجع أقرب النتائج المطابقة.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "جزء من اسم اللعبة المطلوب البحث عنها"}
            },
            "required": ["query"],
        },
    },
}

_known_ids = None  # in-memory cache of the last-seen game id set, backed by STATE_FILE


# --------------------------------------------------------------- state io --

def load_known_ids():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    return None


def save_known_ids(ids):
    with open(STATE_FILE, "w") as f:
        json.dump(list(ids), f)


def fetch_games():
    resp = requests.get(GAMELIST_URL, headers=ROLIMONS_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()["games"]


# ------------------------------------------------------------ image lookup --

def get_hires_icon(game_id, fallback_icon, size="512x512"):
    """Rolimons only gives a small (~150px) icon, which is why images looked
    blurry. This asks Roblox directly for a real 512x512 icon instead."""
    universe_id = game_id
    try:
        r = requests.get(PLACE_TO_UNIVERSE_URL.format(game_id), timeout=10)
        r.raise_for_status()
        universe_id = r.json().get("universeId", game_id)
    except Exception:
        pass  # game_id might already be a universe id, try it as-is below

    try:
        r = requests.get(
            GAME_ICONS_URL,
            params={"universeIds": universe_id, "size": size, "format": "Png", "isCircular": "false"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data") or []
        if data and data[0].get("state") == "Completed":
            return data[0]["imageUrl"]
    except Exception as e:
        log.warning(f"hi-res icon lookup failed for {game_id}: {e}")

    return fallback_icon  # last resort: rolimons' small icon, better than nothing


# ------------------------------------------------------------------- groq --

def call_groq(messages, tools=None):
    payload = {"model": GROQ_MODEL, "messages": messages, "temperature": 0.6, "max_tokens": 600}
    if tools:
        payload["tools"] = tools
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    r = requests.post(GROQ_URL, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def generate_broadcast_caption(name, players, link):
    system = (
        "انت تكتب كابشن قصير لقناة تيليكرام تعلن عن ماب روبلوكس جديد ظهر على "
        "Rolimons. سطرين لثلاثة، حماسي بس مو مبالغ، بدون هاشتاقات، وبدون أي "
        "معلومة مختلَقة. لازم يتضمن اسم اللعبة بالضبط زي ما انعطى لك. رد "
        "بالكابشن فقط بدون شرح إضافي."
    )
    user = f"اسم اللعبة: {name}\nعدد اللاعبين الحاليين: {players}\nالرابط: {link}"
    try:
        msg = call_groq([{"role": "system", "content": system}, {"role": "user", "content": user}])
        return f"{(msg.get('content') or '').strip()}\n{link}"
    except Exception as e:
        log.warning(f"caption generation failed, using fallback template: {e}")
        return f"🆕 ماب جديد على Rolimons\n{name}\n{link}"


# ----------------------------------------------------------------- search --

def search_games(games, query, limit=5):
    q = query.strip().lower()
    if not q:
        return []
    matches = [(gid, data) for gid, data in games.items() if q in data[0].lower()]
    matches.sort(key=lambda item: len(item[1][0]))  # shorter/closer names first
    return matches[:limit]


# --------------------------------------------------------- telegram: cmds --

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "هلا! أنا بوت بيراقب مابات روبلوكس الجديدة على Rolimons وبيبعتلك أول "
        "ما توصل.\n\n"
        "• /search <اسم> — دور على ماب معين بالاسم\n"
        "• أو اكتبلي عادي زي أي محادثة، وبفهم لحالي لو سألت عن ماب معين"
    )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("اكتب اسم الماب بعد الأمر، مثلاً:\n/search Pet Simulator")
        return

    games = context.bot_data.get("games") or await asyncio.to_thread(fetch_games)
    context.bot_data["games"] = games
    results = search_games(games, query)

    if not results:
        await update.message.reply_text(f'ما لقيت شي يطابق "{query}" بقائمة Rolimons.')
        return

    for gid, (name, players, icon) in results:
        link = f"https://www.roblox.com/games/{gid}"
        hires = await asyncio.to_thread(get_hires_icon, gid, icon)
        try:
            players_fmt = f"{int(players):,}"
        except (TypeError, ValueError):
            players_fmt = str(players)
        await update.message.reply_photo(photo=hires, caption=f"{name}\n👥 {players_fmt}\n{link}")


# ------------------------------------------------------- telegram: chat ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return

    history = context.chat_data.setdefault("history", [])
    history.append({"role": "user", "content": text})
    del history[:-MAX_HISTORY]

    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + history

    try:
        msg = await asyncio.to_thread(call_groq, messages, [SEARCH_TOOL_SCHEMA])
    except Exception as e:
        log.warning(f"groq chat call failed: {e}")
        await update.message.reply_text("في مشكلة بالاتصال بـ Groq حالياً، جرب كمان شوي 🙏")
        return

    tool_calls = msg.get("tool_calls")

    if tool_calls:
        messages.append(msg)
        games = context.bot_data.get("games") or await asyncio.to_thread(fetch_games)
        context.bot_data["games"] = games

        for call in tool_calls:
            if call["function"]["name"] != "search_rolimons_game":
                continue
            try:
                args = json.loads(call["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            results = search_games(games, args.get("query", ""))

            if results:
                gid, (name, players, icon) = results[0]
                link = f"https://www.roblox.com/games/{gid}"
                tool_result = f"الاسم: {name}\nاللاعبين الحاليين: {players}\nالرابط: {link}"
                hires = await asyncio.to_thread(get_hires_icon, gid, icon)
                await update.message.reply_photo(photo=hires, caption=f"{name}\n{link}")
            else:
                tool_result = "ما في نتائج مطابقة بقائمة Rolimons."

            messages.append({"role": "tool", "tool_call_id": call["id"], "content": tool_result})

        try:
            final = await asyncio.to_thread(call_groq, messages)
            reply_text = (final.get("content") or "").strip() or "لقيت النتيجة وبعتهالك فوق 👆"
        except Exception as e:
            log.warning(f"groq follow-up call failed: {e}")
            reply_text = "لقيت النتيجة وبعتهالك فوق 👆"
    else:
        reply_text = (msg.get("content") or "").strip()

    if reply_text:
        history.append({"role": "assistant", "content": reply_text})
        del history[:-MAX_HISTORY]
        await update.message.reply_text(reply_text)


# --------------------------------------------------------- broadcast job --

async def broadcast_new_game(context: ContextTypes.DEFAULT_TYPE, gid, data):
    name, players, icon = data
    link = f"https://www.roblox.com/games/{gid}"
    caption = await asyncio.to_thread(generate_broadcast_caption, name, players, link)
    hires = await asyncio.to_thread(get_hires_icon, gid, icon)
    try:
        await context.bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=hires, caption=caption)
    except Exception as e:
        log.warning(f"failed to broadcast {gid}: {e}")


async def check_new_games(context: ContextTypes.DEFAULT_TYPE):
    global _known_ids

    try:
        games = await asyncio.to_thread(fetch_games)
    except Exception as e:
        log.warning(f"fetch_games failed: {e}")
        return

    context.bot_data["games"] = games

    if _known_ids is None:
        _known_ids = load_known_ids()

    if _known_ids is None:
        # Very first run ever: send a small test batch (newest ids first,
        # since Rolimons doesn't give us an actual "date added" field) so
        # you can confirm everything works, then go quiet until something
        # genuinely new shows up.
        newest_first = sorted(games.keys(), key=lambda gid: int(gid), reverse=True)
        sample = newest_first[:INITIAL_SEND_COUNT]
        log.info(f"[init] first run, sending {len(sample)} games as a test batch")
        for gid in sample:
            await broadcast_new_game(context, gid, games[gid])
        _known_ids = set(games.keys())
        save_known_ids(_known_ids)
        log.info(f"[init] captured {len(_known_ids)} known games")
        return

    current_ids = set(games.keys())
    new_ids = current_ids - _known_ids
    for gid in new_ids:
        log.info(f"[new] {games[gid][0]} ({gid})")
        await broadcast_new_game(context, gid, games[gid])

    _known_ids = current_ids
    save_known_ids(current_ids)


# ------------------------------------------------------------------- main --

async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.warning(f"unhandled error: {context.error}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)

    app.job_queue.run_repeating(check_new_games, interval=CHECK_INTERVAL, first=5)

    log.info("bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
