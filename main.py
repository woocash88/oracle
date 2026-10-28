import os
import sqlite3
from datetime import datetime, timedelta

import discord
from discord import app_commands
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALLOWED_CHANNELS_RAW = os.getenv("ALLOWED_CHANNELS", "")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is missing in .env")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing in .env")

# Parse the comma-separated channel IDs into a set of ints
ALLOWED_CHANNELS: set[int] = set()
for part in ALLOWED_CHANNELS_RAW.split(","):
    part = part.strip()
    if part:
        ALLOWED_CHANNELS.add(int(part))

# ── SQLite setup ──────────────────────────────────────────────────────────

conn = sqlite3.connect("chat_history.db")
cursor = conn.cursor()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   DATETIME NOT NULL,
        channel_id  INTEGER NOT NULL,
        author      TEXT    NOT NULL,
        content     TEXT    NOT NULL
    )
    """
)
conn.commit()

# ── Gemini setup ──────────────────────────────────────────────────────────

genai_client = genai.Client(api_key=GEMINI_API_KEY)

def build_prompt(spice: str, target_user: discord.User | discord.Member | None = None) -> str:
    if target_user:
        base_structure = (
            f"Analyze the following messages sent by the user **{target_user.display_name}** ({target_user.name}) "
            "and create a personal summary of their chat activity in Polish.\n\n"
            "Format requirements:\n"
            "**1. Główne tematy i wypowiedzi**\n"
            "Summarize what they were talking about or complaining/excited about.\n\n"
            "**2. Styl komunikacji i nastawienie**\n"
            "Describe their vibe, tone, and overall presence in the chat.\n\n"
            "Keep the entire response under 1800 characters. Do NOT include the ===PART2=== delimiter."
        )
    else:
        base_structure = (
            "Analyze the following chat log and create a summary in Polish strictly divided into 4 specific points, "
            "separated into two parts by the delimiter ===PART2===.\n\n"
            "Your output format MUST strictly follow this layout:\n\n"
            "**1. Główny temat**\n"
            "Write the main topic text here in normal font.\n\n"
            "**2. Aktywni użytkownicy**\n"
            "- User 1: short description\n"
            "- User 2: short description\n\n"
            "===PART2===\n\n"
            "**3. Kontrowersje**\n"
            "Write the controversies text here in normal font.\n\n"
            "**4. Ogólna atmosfera**\n"
            "Write the general vibe text here in normal font.\n\n"
            "Formatting Rules:\n"
            "- Bold ONLY the section titles (e.g., **1. Główny temat**). The content under each title must be in standard, unbolded text.\n"
            "- In section 2 (Aktywni użytkownicy), list the users strictly using bullet points with dashes ('-'), NOT numbered lists.\n"
            "- Part 1 (points 1 & 2 before the delimiter) must stay under 1500 characters.\n"
            "- Part 2 (points 3 & 4 after the delimiter) must stay under 1500 characters.\n"
            "- Do NOT use the delimiter ===PART2=== anywhere else in the response."
        )
    
    spice_instructions = {
        "standard": f"{base_structure}\n\nStyle requirement: Write an objective, neutral summary.",
        "roast": f"{base_structure}\n\nStyle requirement: Write a sarcastic, satirical summary. Roast the user(s) playfully.",
        "unfiltered": f"{base_structure}\n\nStyle requirement: Write a very edgy, unfiltered, highly sarcastic summary in Polish with profanity allowed. Treat it like a roast among close friends.",
    }
    return spice_instructions.get(spice, spice_instructions["standard"])

# ── Discord bot setup ─────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

class ChatSummaryBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"Failed to sync slash commands: {e}")

    async def on_message(self, message: discord.Message):
        # Ignore bots (including self)
        if message.author.bot:
            return

        # Only track allowed channels
        if message.channel.id not in ALLOWED_CHANNELS:
            return

        cursor.execute(
            "INSERT INTO messages (timestamp, channel_id, author, content) VALUES (?, ?, ?, ?)",
            (message.created_at, message.channel.id, str(message.author), message.content),
        )
        conn.commit()


client = ChatSummaryBot()


# ── Slash command: /podsumowanie ──────────────────────────────────────────

@client.tree.command(
    name="podsumowanie",
    description="Generuje podsumowanie czatu z ostatnich X dni.",
)
@app_commands.describe(
    days="Liczba dni wstecz (domyślnie 1)",
    channel="Kanał do podsumowania (domyślnie bieżący)",
    spice="Styl podsumowania (domyślnie standard)",
    user="Opcjonalnie: podsumuj tylko wypowiedzi wybranego użytkownika",
)
@app_commands.choices(spice=[
    app_commands.Choice(name="Standard", value="standard"),
    app_commands.Choice(name="Satyryczny / Roast", value="roast"),
    app_commands.Choice(name="Ostre / Bez Cenzury", value="unfiltered"),
])
async def podsumowanie(
    interaction: discord.Interaction,
    days: int = 1,
    channel: discord.TextChannel = None,
    spice: str = "standard",
    user: discord.User = None,
):
    # Defer immediately so we don't hit Discord's 3-second timeout
    await interaction.response.defer()

    target_channel = channel if channel else interaction.channel
    if target_channel.id not in ALLOWED_CHANNELS:
        await interaction.followup.send(
            "❌ Ten kanał nie jest śledzony – nie mam dla niego historii wiadomości."
        )
        return

    cutoff = datetime.utcnow() - timedelta(days=days)

    if user:
        # SQLite matches string author e.g. "username" or "username#1234"
        cursor.execute(
            "SELECT timestamp, author, content FROM messages "
            "WHERE channel_id = ? AND timestamp >= ? AND (author = ? OR author LIKE ?||'#%') "
            "ORDER BY timestamp ASC",
            (target_channel.id, cutoff, str(user), str(user.name)),
        )
    else:
        cursor.execute(
            "SELECT timestamp, author, content FROM messages "
            "WHERE channel_id = ? AND timestamp >= ? "
            "ORDER BY timestamp ASC",
            (target_channel.id, cutoff),
        )
    
    rows = cursor.fetchall()

    if not rows:
        target_name = f"użytkownika {user.mention}" if user else "tego kanału"
        await interaction.followup.send(
            f"Brak wiadomości w bazie danych dla {target_name} w podanym okresie."
        )
        return

    # Format into a single text blob
    lines = []
    for ts, author, content in rows:
        lines.append(f"[{ts}] {author}: {content}")
    chat_log = "\n".join(lines)

    prompt = build_prompt(spice, target_user=user)

    # Send to Gemini
    try:
        response = genai_client.models.generate_content(
            model="gemini-3.5-flash",
            contents=f"{prompt}\n\n{chat_log}",
        )
        summary = response.text
    except Exception as e:
        await interaction.followup.send(
            f"❌ Wystąpił błąd podczas generowania podsumowania: {e}"
        )
        return

    # Try to split by the requested delimiter first (for full-channel summaries)
    DELIMITER = "===PART2==="
    if DELIMITER in summary:
        part_1, part_2 = summary.split(DELIMITER, 1)
        part_1 = part_1.strip()
        part_2 = part_2.strip()
        await interaction.followup.send(part_1)
        await interaction.followup.send(part_2)
    elif len(summary) <= 1900:
        await interaction.followup.send(summary)
    else:
        # Fallback: split cleanly on the last paragraph boundary under 1900 chars
        split_at = summary.rfind("\n", 0, 1900)
        if split_at == -1:
            split_at = summary.rfind(". ", 0, 1900)
        if split_at == -1:
            split_at = 1900
        part_1 = summary[: split_at + 1].strip()
        part_2 = summary[split_at + 1 :].strip()
        await interaction.followup.send(part_1)
        await interaction.followup.send(part_2)


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)