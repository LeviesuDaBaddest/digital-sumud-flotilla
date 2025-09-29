import socket
import json
import time
import subprocess
import os
import random
import math

# ----------------------
# CONFIG
# ----------------------
NUM_GHOSTS = 11 # Original ghosts
UPDATE_INTERVAL = 600  # seconds
SPEED_VARIATION = 0.08
POSITIONS_FILE = "fleet_positions.json"
REAL_SHIP_ID = "al_awda"

# ----------------------
# CUSTOM GHOST NAMES
# ----------------------
GHOST_NAMES = ["Ma’an", "Navaren", "Al Quds", "Ramallah", "Ode", "Miami", "Gaza City", "Freedom", "Argo", "Brune", "Inman"]

RENDEZVOUS_NAMES = {
    "Tunisia": ["Tunisia1", "Tunisia2", "Tunisia3"],
    "Italy": ["Italy1", "Italy2"]
}

# ----------------------
# RENDEZVOUS POINTS
# ----------------------
RENDEZVOUS = [
   {"name": "Tunisia", "lat": 36.8,  "lon": 10.17, "ships": 3},
    {"name": "Italy",   "lat": 37.5,  "lon": 15.1, "ships": 2}
]

# ----------------------
# GLOBAL STATE
# ----------------------
GHOST_STATES = {}  # Tracks ghosts
USED_NAMES = set()  # Tracks which names are already spawned

# ----------------------
# HELPER FUNCTIONS
# ----------------------
def read_position():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", 10111))
        s.settimeout(10)
        true_heading = None
        while True:
            raw = s.recv(1024).decode(errors="ignore")
            for line in raw.splitlines():
                if line.startswith("$HDT"):
                    try: true_heading = float(line.split(",")[1])
                    except: pass
                elif line.startswith("$HDG"):
                    try: true_heading = float(line.split(",")[1])
                    except: pass
                elif line.startswith("$GPRMC"):
                    parts = line.split(",")
                    if len(parts) < 9: continue
                    lat_raw, lat_dir = parts[3], parts[4]
                    lon_raw, lon_dir = parts[5], parts[6]
                    if not lat_raw or not lon_raw: continue
                    lat = float(lat_raw[:2]) + float(lat_raw[2:])/60.0
                    lon = float(lon_raw[:3]) + float(lon_raw[3:])/60.0
                    if lat_dir.upper() == "S": lat = -lat
                    if lon_dir.upper() == "W": lon = -lon
                    sog = float(parts[7]) if parts[7] else 0.0
                    cog = float(parts[8]) if parts[8] else 0.0
                    hdg = true_heading if true_heading is not None else cog
                    return lat, lon, sog, hdg
    except Exception as e:
        print("❌ NMEA read error:", e)
    return None, None, 0.0, 0.0

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_positions(fleet):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(fleet, f, indent=2)

def haversine_nm(lat1, lon1, lat2, lon2):
    R_nm = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R_nm * c

# ----------------------
# INITIALIZE GHOSTS
# ----------------------
def initialize_ghost_states():
    fleet = load_positions()
    for ghost_id, positions in fleet.items():
        if ghost_id == REAL_SHIP_ID: continue
        if positions:
            last_pos = positions[-1]
            name = last_pos.get("name", ghost_id)
            GHOST_STATES[ghost_id] = {
                "name": name,
                "lat": last_pos["lat"],
                "lon": last_pos["lon"],
                "rel_bearing": random.uniform(0, 360),
                "rel_distance": random.uniform(0.05, 0.8),
                "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION),
                "heading_jitter": random.uniform(-5, 5),
                "current_nudge": random.uniform(-0.02, 0.02)
            }
            USED_NAMES.add(name)

# ----------------------
# MOVE GHOST
# ----------------------
def move_ghost(real_lat, real_lon, sog, hdg, ghost_id):
    state = GHOST_STATES[ghost_id]

    if "lat" not in state or "lon" not in state:
        state["lat"] = real_lat + random.uniform(-0.02, 0.02)
        state["lon"] = real_lon + random.uniform(-0.02, 0.02)

    state["speed_bias"] += random.uniform(-0.01, 0.01)
    state["speed_bias"] = max(0.85, min(1.15, state["speed_bias"]))
    state["heading_jitter"] += random.uniform(-0.5, 0.5)
    state["heading_jitter"] = max(-15, min(15, state["heading_jitter"]))
    state["current_nudge"] += random.uniform(-0.005, 0.005)
    state["current_nudge"] = max(-0.03, min(0.03, state["current_nudge"]))

    burst_factor = random.uniform(1.0, 1.3)
    ghost_speed = max(0.05, sog * state["speed_bias"] * burst_factor)
    dist_deg = ghost_speed * (UPDATE_INTERVAL / 3600) / 60
    move_heading = hdg + state["heading_jitter"]
    rad = math.radians(move_heading)

    delta_lat = dist_deg * math.cos(rad) + state["current_nudge"]
    delta_lon = dist_deg * math.sin(rad) / max(0.1, math.cos(math.radians(state["lat"]))) + state["current_nudge"]

    state["lat"] += delta_lat
    state["lon"] += delta_lon
    ghost_hdg = (hdg + state["heading_jitter"]) % 360

    return state["lat"], state["lon"], ghost_speed, ghost_hdg

# ----------------------
# SPAWN ONE NEW GHOST
# ----------------------
def spawn_one_ghost(real_lat, real_lon):
    # Spawn from original ghosts first
    for name in GHOST_NAMES:
        if name not in USED_NAMES:
            ghost_id = f"ghost_{name.lower()}"
            GHOST_STATES[ghost_id] = {
                "name": name,
                "lat": real_lat + random.uniform(-0.02, 0.02),
                "lon": real_lon + random.uniform(-0.02, 0.02),
                "rel_bearing": random.uniform(0, 360),
                "rel_distance": random.uniform(0.05, 0.8),
                "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION),
                "heading_jitter": random.uniform(-5, 5),
                "current_nudge": random.uniform(-0.02, 0.02)
            }
            USED_NAMES.add(name)
            print(f"👻 Spawned {name}")
            return

    # Then spawn rendezvous ghosts if inside a point
    for point in RENDEZVOUS:
        distance_nm = haversine_nm(real_lat, real_lon, point["lat"], point["lon"])
        if distance_nm < 40:
            names = RENDEZVOUS_NAMES.get(point["name"], [])
            for i, name in enumerate(names[:point["ships"]]):
                ghost_id = f"{point['name'].lower()}_{i+1}"
                if ghost_id not in GHOST_STATES and name not in USED_NAMES:
                    GHOST_STATES[ghost_id] = {
                        "name": name,
                        "lat": real_lat + random.uniform(-0.02, 0.02),
                        "lon": real_lon + random.uniform(-0.02, 0.02),
                        "rel_bearing": random.uniform(0, 360),
                        "rel_distance": random.uniform(0.05, 0.8),
                        "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION),
                        "heading_jitter": random.uniform(-5, 5),
                        "current_nudge": random.uniform(-0.02, 0.02)
                    }
                    USED_NAMES.add(name)
                    print(f"👻 Spawned {name} at {point['name']}")
                    return

# ----------------------
# GENERATE OR UPDATE ALL GHOSTS
# ----------------------
def generate_or_update_ghosts(real_lat, real_lon, sog, hdg, fleet):
    for ghost_id, state in GHOST_STATES.items():
        fleet.setdefault(ghost_id, [])
        new_lat, new_lon, ghost_speed, ghost_hdg = move_ghost(real_lat, real_lon, sog, hdg, ghost_id)
        fleet[ghost_id].append({
            "lat": new_lat,
            "lon": new_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True,
            "name": state["name"],
            "speed": round(ghost_speed, 2),
            "heading": round(ghost_hdg, 1)
        })
    return fleet

# ----------------------
# APPEND POSITIONS
# ----------------------
def append_positions(real_lat, real_lon, sog, hdg):
    fleet = load_positions()
    fleet.setdefault(REAL_SHIP_ID, []).append({
        "lat": real_lat,
        "lon": real_lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ghost": False,
        "name": "Al Awda",
        "speed": round(sog, 2),
        "heading": round(hdg, 1)
    })
    spawn_one_ghost(real_lat, real_lon)
    fleet = generate_or_update_ghosts(real_lat, real_lon, sog, hdg, fleet)
    save_positions(fleet)
    print(f"📌 Appended real ship + {len(GHOST_STATES)} ghost ships.")

# ----------------------
# GIT PUSH
# ----------------------
def push_to_git():
    subprocess.run(["git","add","-A"])
    result = subprocess.run(["git","commit","-m","🛰️ Auto-update with heartbeat"])
    if result.returncode != 0: print("⚠️ Nothing to commit")
    subprocess.run(["git","push"])
    print("📤 Pushed to GitHub.")

# ----------------------
# MAIN LOOP
# ----------------------
if __name__ == "__main__":
    print("🚀 Starting Virtual Voyage To Gaza Tracker...")
    initialize_ghost_states()
    while True:
        lat, lon, sog, hdg = read_position()
        if lat and lon:
            append_positions(lat, lon, sog, hdg)
            push_to_git()
        print(f"⏲️ Sleeping {UPDATE_INTERVAL} seconds...")
        time.sleep(UPDATE_INTERVAL)
