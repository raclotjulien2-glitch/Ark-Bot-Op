import discord
from discord.ext import commands
import aiohttp
import os

# ---------- CONFIG VIA ENV ----------
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
BATTLEMETRICS_TOKEN = os.environ.get("BATTLEMETRICS_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# ---------- UTILITAIRES ----------
async def get_json(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers={"Authorization": f"Bearer {BATTLEMETRICS_TOKEN}"}, timeout=5) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except:
            return None

# ---------- /pop minimal ----------
@bot.command()
async def pop(ctx, server_id: str):
    data = await get_json(f"https://api.battlemetrics.com/servers/{server_id}")
    if not data or "data" not in data:
        await ctx.send(f"❌ Impossible de récupérer le serveur {server_id}")
        return
    attrs = data["data"]["attributes"]
    await ctx.send(f"📊 Serveur {attrs.get('name','inconnu')} ({server_id})\n"
                   f"Joueurs : {attrs.get('players',0)}/{attrs.get('maxPlayers',0)}\n"
                   f"Ping : {attrs.get('ping','N/A')} ms")

# ---------- /recon minimal ----------
@bot.command()
async def recon(ctx, player_id: str):
    data = await get_json(f"https://api.battlemetrics.com/players/{player_id}")
    if not data or "data" not in data:
        await ctx.send(f"❌ Impossible de trouver le joueur {player_id}")
        return
    attrs = data["data"]["attributes"]
    name = attrs.get("name","Inconnu")
    platform = attrs.get("platform","N/A")
    status = "En ligne" if attrs.get("status")=="online" else "Hors ligne"
    await ctx.send(f"🔎 {name}\nPlateforme : {platform}\nStatut : {status}")

# ---------- DÉMARRAGE ----------
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")

bot.run(DISCORD_TOKEN)
