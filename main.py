import discord
from discord.ext import commands, tasks
import requests
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime, timedelta

# ---------- CONFIG ----------
DISCORD_TOKEN = "TON_DISCORD_TOKEN"
BATTLEMETRICS_TOKEN = "TON_TOKEN_BATTLEMETRICS"
TRACK_CHANNEL_ID = 123456789012345678  # ID du salon Discord pour notifications

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# ---------- STOCKAGE ----------
tracked_players = {}   # { "pseudo": {"online": bool, "server": server_id} }
pop_history = {}       # { server_id: [(timestamp, player_count), ...] }

# ---------- UTILITAIRES ----------
def get_server_data(server_id):
    url = f"https://api.battlemetrics.com/servers/{server_id}"
    headers = {"Authorization": f"Bearer {BATTLEMETRICS_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return None
    return resp.json()["data"]["attributes"]

def get_server_players(server_id):
    url = f"https://api.battlemetrics.com/servers/{server_id}/players"
    headers = {"Authorization": f"Bearer {BATTLEMETRICS_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return []
    players = []
    for p in resp.json().get("data", []):
        name = p["attributes"].get("name", "Inconnu")
        platform = p["attributes"].get("platform", "N/A")
        players.append({"name": name, "platform": platform})
    return players

# ---------- COMMANDE /pop ----------
@bot.command()
async def pop(ctx, server_id: str):
    """Affiche le nombre de joueurs et détails d'un serveur officiel ASA."""
    server_data = get_server_data(server_id)
    if not server_data:
        await ctx.send(f"❌ Impossible de récupérer les infos serveur {server_id}")
        return

    player_count = server_data.get("players", 0)
    max_players = server_data.get("maxPlayers", 0)
    server_name = server_data.get("name", "Serveur inconnu")
    ping = server_data.get("ping", "N/A")

    # Historique
    if server_id not in pop_history:
        pop_history[server_id] = []
    pop_history[server_id].append((datetime.utcnow(), player_count))
    pop_history[server_id] = [(t, p) for t, p in pop_history[server_id] if t > datetime.utcnow() - timedelta(hours=24)]

    players_list = get_server_players(server_id)

    embed = discord.Embed(title=f"📊 Pop du serveur {server_name} ({server_id})", color=0x00ff00)
    embed.add_field(name="Joueurs connectés", value=f"{player_count}/{max_players}", inline=True)
    embed.add_field(name="Ping", value=f"{ping} ms", inline=True)

    if players_list:
        lines = [f"{p['name']} ({p['platform']})" for p in players_list[:20]]
        embed.add_field(name="Liste joueurs", value="\n".join(lines), inline=False)
        if len(players_list) > 20:
            embed.add_field(name="...", value=f"et {len(players_list)-20} autres...", inline=False)

    await ctx.send(embed=embed)

# ---------- COMMANDE /track ----------
@bot.command()
async def track(ctx, player_name: str, server_id: str):
    """Active le suivi d'un joueur sur un serveur officiel ASA."""
    tracked_players[player_name.lower()] = {"online": False, "server": server_id}
    await ctx.send(f"✅ Tracking activé pour **{player_name}** sur le serveur {server_id}")

# ---------- COMMANDE /graph ----------
@bot.command()
async def graph(ctx, server_id: str):
    """Affiche un graphique de l'évolution du pop sur 24h."""
    if server_id not in pop_history or not pop_history[server_id]:
        await ctx.send("❌ Pas assez de données pour ce serveur.")
        return

    times, counts = zip(*pop_history[server_id])
    plt.figure(figsize=(10,4))
    plt.plot(times, counts, marker='o', linestyle='-', color='green')
    plt.title(f"Évolution du pop - Serveur {server_id}")
    plt.xlabel("Temps (UTC)")
    plt.ylabel("Nombre de joueurs")
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    await ctx.send(file=discord.File(buf, filename=f"graph_{server_id}.png"))

# ---------- COMMANDE /recon ----------
@bot.command()
async def recon(ctx, player_id: str):
    """Recherche un joueur via Xbox/PSN/Steam et indique serveur actuel et historique."""
    url = f"https://api.battlemetrics.com/players/{player_id}"
    headers = {"Authorization": f"Bearer {BATTLEMETRICS_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        await ctx.send(f"❌ Impossible de trouver le joueur avec l'ID {player_id}")
        return

    data = response.json()["data"]
    attributes = data["attributes"]
    player_name = attributes.get("name", "Inconnu")
    platform = attributes.get("platform", "N/A")
    status = "En ligne" if attributes.get("status") == "online" else "Hors ligne"

    # Serveurs récents
    servers_info = []
    current_server = "Aucun"
    relationships = data.get("relationships", {})
    if "servers" in relationships and relationships["servers"]["data"]:
        for srv in relationships["servers"]["data"]:
            srv_id = srv["id"]
            srv_name = srv["attributes"].get("name", "Serveur inconnu")
            time_played = srv["attributes"].get("timePlayed", 0)
            hours_played = round(time_played / 60, 1)
            servers_info.append(f"{srv_name} ({srv_id}) – {hours_played}h")
            # Vérification serveur actuel
            if attributes.get("status") == "online" and attributes.get("server") == srv_id:
                current_server = f"{srv_name} ({srv_id})"

    embed = discord.Embed(title=f"🔎 Recon joueur : {player_name}", color=0x00ff99)
    embed.add_field(name="Plateforme", value=platform, inline=True)
    embed.add_field(name="Statut", value=status, inline=True)
    embed.add_field(name="Serveur actuel", value=current_server, inline=False)
    if servers_info:
        embed.add_field(name="Serveurs joués", value="\n".join(servers_info[:10]), inline=False)
        if len(servers_info) > 10:
            embed.add_field(name="...", value=f"et {len(servers_info)-10} autres serveurs", inline=False)
    
    await ctx.send(embed=embed)

# ---------- TÂCHE DE SUIVI ----------
@tasks.loop(seconds=60)
async def track_loop():
    if not tracked_players:
        return
    channel = bot.get_channel(TRACK_CHANNEL_ID)
    for player_name, info in tracked_players.items():
        server_id = info["server"]
        players = get_server_players(server_id)
        found_online = any(p["name"].lower() == player_name for p in players)

        if info["online"] and not found_online:
            await channel.send(f"🔴 **{player_name}** s'est déconnecté du serveur {server_id}")
        elif not info["online"] and found_online:
            p_platform = next(p["platform"] for p in players if p["name"].lower() == player_name)
            await channel.send(f"🟢 **{player_name}** s'est connecté sur le serveur {server_id} ({p_platform})")

        tracked_players[player_name]["online"] = found_online

# ---------- DÉMARRAGE ----------
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")
    track_loop.start()

bot.run(DISCORD_TOKEN)
