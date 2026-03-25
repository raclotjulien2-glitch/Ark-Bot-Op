import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime, timedelta
import math
import os

# ---------- CONFIG VIA ENV ----------
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
BATTLEMETRICS_TOKEN = os.environ.get("BATTLEMETRICS_TOKEN")
TRACK_CHANNEL_ID = int(os.environ.get("TRACK_CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# ---------- STOCKAGE ----------
tracked_players = {}  # {player_name: {"online": bool, "server": server_id}}
pop_history = {}      # {server_id: [(timestamp, player_count)]}

# ---------- UTILITAIRES ASYNC ----------
async def get_json(url, session, timeout=5):
    try:
        async with session.get(url, headers={"Authorization": f"Bearer {BATTLEMETRICS_TOKEN}"}, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except asyncio.TimeoutError:
        return None
    except:
        return None

async def get_server_data(server_id, session):
    data = await get_json(f"https://api.battlemetrics.com/servers/{server_id}", session)
    if data and "data" in data:
        return data["data"]["attributes"]
    return None

async def get_server_players(server_id, session):
    data = await get_json(f"https://api.battlemetrics.com/servers/{server_id}/players", session)
    players = []
    if data and "data" in data:
        for p in data["data"]:
            players.append({
                "name": p["attributes"].get("name", "Inconnu"),
                "platform": p["attributes"].get("platform", "N/A")
            })
    return players

# ---------- /pop ----------
@bot.command()
async def pop(ctx, server_id: str):
    async with aiohttp.ClientSession() as session:
        server_data = await get_server_data(server_id, session)
        if not server_data:
            await ctx.send(f"❌ Impossible de récupérer le serveur {server_id}")
            return

        player_count = server_data.get("players", 0)
        max_players = server_data.get("maxPlayers", 0)
        server_name = server_data.get("name", "Serveur inconnu")

        # Historique 24h
        if server_id not in pop_history:
            pop_history[server_id] = []
        pop_history[server_id].append((datetime.utcnow(), player_count))
        pop_history[server_id] = [(t, p) for t, p in pop_history[server_id] if t > datetime.utcnow() - timedelta(hours=24)]

        players_list = await get_server_players(server_id, session)

        # Pagination si >20 joueurs
        page_size = 20
        total_pages = math.ceil(len(players_list)/page_size)
        current_page = 0

        def create_embed(page):
            embed = discord.Embed(title=f"📊 Pop du serveur {server_name} ({server_id})", color=0x00ff00)
            embed.add_field(name="Joueurs connectés", value=f"{player_count}/{max_players}", inline=True)
            embed.add_field(name="Ping", value=f"{server_data.get('ping','N/A')} ms", inline=True)
            start = page*page_size
            end = start+page_size
            if players_list:
                embed.add_field(name=f"Liste joueurs (Page {page+1}/{total_pages})",
                                value="\n".join([f"{p['name']} ({p['platform']})" for p in players_list[start:end]]),
                                inline=False)
            return embed

        message = await ctx.send(embed=create_embed(current_page))
        if total_pages <= 1:
            return

        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️","▶️"] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == "▶️" and current_page+1 < total_pages:
                    current_page += 1
                    await message.edit(embed=create_embed(current_page))
                elif str(reaction.emoji) == "◀️" and current_page > 0:
                    current_page -= 1
                    await message.edit(embed=create_embed(current_page))
                await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                break

# ---------- /graph ----------
@bot.command()
async def graph(ctx, server_id: str):
    if server_id not in pop_history or not pop_history[server_id]:
        await ctx.send("❌ Pas assez de données pour ce serveur.")
        return
    times, counts = zip(*pop_history[server_id])
    max_pop = max(counts)+1
    plt.style.use('seaborn-darkgrid')
    plt.figure(figsize=(10,4))
    plt.plot(times, counts, marker='o', linestyle='-', color='#00ff66', linewidth=2)
    plt.title(f"Évolution du pop - Serveur {server_id}", fontsize=16)
    plt.xlabel("Temps (UTC)", fontsize=12)
    plt.ylabel("Nombre de joueurs", fontsize=12)
    plt.ylim(0,max_pop)
    plt.xticks(rotation=45)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    await ctx.send(file=discord.File(buf, filename=f"graph_{server_id}.png"))

# ---------- /track ----------
@bot.command()
async def track(ctx, player_name: str, server_id: str):
    tracked_players[player_name.lower()] = {"online": False, "server": server_id}
    await ctx.send(f"✅ Tracking activé pour **{player_name}** sur le serveur {server_id}")

# ---------- /recon ----------
@bot.command()
async def recon(ctx, player_id: str):
    async with aiohttp.ClientSession() as session:
        data = await get_json(f"https://api.battlemetrics.com/players/{player_id}", session)
        if not data:
            await ctx.send(f"❌ Impossible de trouver le joueur {player_id}")
            return
        attributes = data["data"]["attributes"]
        player_name = attributes.get("name", "Inconnu")
        platform = attributes.get("platform", "N/A")
        status = "En ligne" if attributes.get("status")=="online" else "Hors ligne"
        current_server = "Aucun"
        servers_info = []
        relationships = data["data"].get("relationships", {})
        if "servers" in relationships and relationships["servers"]["data"]:
            for srv in relationships["servers"]["data"]:
                srv_id = srv["id"]
                srv_name = srv["attributes"].get("name","Serveur inconnu")
                hours_played = round(srv["attributes"].get("timePlayed",0)/60,1)
                servers_info.append(f"{srv_name} ({srv_id}) – {hours_played}h")
                if attributes.get("status")=="online" and attributes.get("server")==srv_id:
                    current_server=f"{srv_name} ({srv_id})"
        embed = discord.Embed(title=f"🔎 Recon joueur : {player_name}", color=0x00ff99)
        embed.add_field(name="Plateforme", value=platform, inline=True)
        embed.add_field(name="Statut", value=status, inline=True)
        embed.add_field(name="Serveur actuel", value=current_server, inline=False)
        if servers_info:
            embed.add_field(name="Serveurs joués", value="\n".join(servers_info[:10]), inline=False)
            if len(servers_info)>10:
                embed.add_field(name="...", value=f"et {len(servers_info)-10} autres serveurs", inline=False)
        await ctx.send(embed=embed)

# ---------- TÂCHE DE SUIVI ----------
@tasks.loop(seconds=60)
async def track_loop():
    if not tracked_players:
        return
    channel = bot.get_channel(TRACK_CHANNEL_ID)
    async with aiohttp.ClientSession() as session:
        for player_name, info in tracked_players.items():
            server_id = info["server"]
            players = await get_server_players(server_id, session)
            found_online = any(p["name"].lower()==player_name for p in players)
            if info["online"] and not found_online:
                await channel.send(f"🔴 **{player_name}** s'est déconnecté du serveur {server_id}")
            elif not info["online"] and found_online:
                p_platform = next(p["platform"] for p in players if p["name"].lower()==player_name)
                await channel.send(f"🟢 **{player_name}** s'est connecté sur le serveur {server_id} ({p_platform})")
            tracked_players[player_name]["online"]=found_online

# ---------- DÉMARRAGE ----------
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")
    track_loop.start()

bot.run(DISCORD_TOKEN)
