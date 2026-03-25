import discord
from discord import app_commands
import asyncio
import requests
import json
import os
from datetime import datetime
import matplotlib.pyplot as plt

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DATA_FILE = "data.json"

# ----------- DATA STORAGE -----------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ----------- FAKE SERVER QUERY (REMPLACABLE PAR API) -----------

def get_server_data(server_id):
    # Simulation (remplaçable par vraie API type Battlemetrics)
    import random
    players = random.randint(0, 70)

    fake_names = [f"Player{i}" for i in range(players)]

    return {
        "players": players,
        "names": fake_names,
        "ping": random.randint(30, 120),
        "status": "Online"
    }

# ----------- COMMAND /POP -----------

@tree.command(name="pop", description="Infos serveur ASA")
async def pop(interaction: discord.Interaction, server: str):
    await interaction.response.defer()

    data = get_server_data(server)

    msg = f"📡 Serveur {server}\n"
    msg += f"👥 Joueurs: {data['players']}\n"
    msg += f"📶 Ping: {data['ping']}ms\n"
    msg += f"📍 Status: {data['status']}\n\n"

    msg += "🧍 Joueurs:\n"
    msg += "\n".join(data['names'][:20])

    await interaction.followup.send(msg)

# ----------- COMMAND /GRAPH -----------

@tree.command(name="graph", description="Graph population serveur")
async def graph(interaction: discord.Interaction, server: str):
    await interaction.response.defer()

    data = load_data()

    if server not in data:
        await interaction.followup.send("Pas encore de données.")
        return

    history = data[server]

    times = [entry["time"] for entry in history]
    pops = [entry["pop"] for entry in history]

    plt.figure()
    plt.plot(times, pops)
    plt.xticks(rotation=45)

    filename = f"{server}.png"
    plt.savefig(filename)
    plt.close()

    await interaction.followup.send(file=discord.File(filename))

# ----------- COMMAND /TRACK -----------

@tree.command(name="track", description="Tracker un joueur")
async def track(interaction: discord.Interaction, pseudo: str):
    await interaction.response.send_message(f"🔍 Tracking activé pour {pseudo}")

    data = load_data()
    data.setdefault("track", []).append(pseudo)
    save_data(data)

# ----------- BACKGROUND LOOP -----------

async def tracker_loop():
    await client.wait_until_ready()

    while not client.is_closed():
        data = load_data()

        server_id = "example"

        server = get_server_data(server_id)

        data.setdefault(server_id, [])
        data[server_id].append({
            "time": datetime.now().strftime("%H:%M"),
            "pop": server["players"]
        })

        # TRACK PLAYERS
        tracked = data.get("track", [])

        for name in server["names"]:
            if name in tracked:
                print(f"[ALERTE] {name} détecté !")

        save_data(data)

        await asyncio.sleep(60)

# ----------- READY -----------

@client.event
async def on_ready():
    await tree.sync()
    print(f"Connecté en tant que {client.user}")
    client.loop.create_task(tracker_loop())

client.run(TOKEN)
