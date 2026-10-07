import os
import json
import asyncio
from datetime import datetime, timezone
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
# Optional: set this to the channel ID where update notifications should go.
UPDATE_CHANNEL_ID = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
# Public Fortnite API endpoint.
NEWS_URL = "https://fortnite-api.com/news/br"
STATE_FILE = "state.json"
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "title": None,
            "body": None,
            "image": None,
            "checked_at": None
        }
def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
state = load_state()
class FortniteBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(
            command_prefix="!",
            intents=intents
        )
    async def setup_hook(self):
        await self.tree.sync()
        update_checker.start()
bot = FortniteBot()
async def get_fortnite_news():
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            NEWS_URL,
            headers={"User-Agent": "FortniteDiscordBot/1.0"}
        ) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"Fortnite API returned HTTP {response.status}"
                )
            return await response.json()
def extract_news(data):
    # Fortnite-API.com normally returns a "data" object containing
    # "br" news information.
    news = data.get("data", {})
    if not isinstance(news, dict):
        return None
    # The exact API structure can change, so handle common layouts.
    message = news.get("message")
    image = news.get("image")
    if message:
        return {
            "title": "Fortnite Battle Royale Update",
            "body": message,
            "image": image
        }
    # Some API responses may expose a news list.
    entries = news.get("news")
    if isinstance(entries, list) and entries:
        entry = entries[0]
        if isinstance(entry, dict):
            return {
                "title": entry.get("title", "Fortnite Update"),
                "body": entry.get("body", entry.get("description", "")),
                "image": entry.get("image")
            }
    return None
def make_embed(news):
    embed = discord.Embed(
        title=news["title"],
        description=news["body"][:4000],
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Fortnite Update Tracker")
    if news.get("image"):
        embed.set_image(url=news["image"])
    return embed
async def check_for_update():
    global state
    data = await get_fortnite_news()
    news = extract_news(data)
    if not news:
        return None
    changed = (
        news["title"] != state.get("title")
        or news["body"] != state.get("body")
        or news.get("image") != state.get("image")
    )
    state["checked_at"] = datetime.now(timezone.utc).isoformat()
    if not changed:
        save_state(state)
        return None
    state["title"] = news["title"]
    state["body"] = news["body"]
    state["image"] = news.get("image")
    save_state(state)
    return news
@tasks.loop(minutes=10)
async def update_checker():
    try:
        news = await check_for_update()
        if not news:
            return
        if UPDATE_CHANNEL_ID == 0:
            print("New Fortnite update detected, but UPDATE_CHANNEL_ID is not set.")
            return
        channel = bot.get_channel(UPDATE_CHANNEL_ID)
        if channel is None:
            print("Update channel could not be found.")
            return
        embed = make_embed(news)
        await channel.send(
            content="**New Fortnite update information detected.**",
            embed=embed
        )
    except Exception as e:
        print(f"Update checker error: {e}")
@update_checker.before_loop
async def before_update_checker():
    await bot.wait_until_ready()
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
@bot.tree.command(
    name="status",
    description="Show the latest Fortnite update information."
)
async def status(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        data = await get_fortnite_news()
        news = extract_news(data)
        if not news:
            await interaction.followup.send(
                "I couldn't retrieve the current Fortnite update information."
            )
            return
        embed = make_embed(news)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"/status error: {e}")
        await interaction.followup.send(
            "I couldn't retrieve Fortnite's current update information."
        )
bot.run(DISCORD_TOKEN)
