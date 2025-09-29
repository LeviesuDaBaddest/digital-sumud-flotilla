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
UPDATE_INTERVAL = 600  # seconds
SPEED_VARIATION = 0.05  # smaller variation for smoother speeds
POSITIONS_FILE = "fleet_positions.json"
REAL_SHIP_ID = "al_awda"
MAX_SPEED_FACTOR = 1.05  # ghosts cannot exceed 105% of real ship speed
MIN_DISTANCE_NM = 0.05  # minimum distance offset from real ship
MAX_DISTANCE_NM = 0.5   # maximum distance offset from real ship

# ----------------------
# CUSTOM GHOST NAMES
# ----------------------
GHOST_NAMES = ["Ma’an", "Navaren", "Al Quds", "Ramallah", "Ode", "Miami"]
CYPRUS_NAMES = ["Gaza City", "Freedom", "Argo", "Brune", "Inman"]
RENDEZVOUS_POINTS = [
    {"name": "Cyprus",  "lat": 35.16, "lon": 33.36, "ships": 5, "names": CYPRUS_NAMES},
    {"name": "Tunisia", "lat": 36.8,  "lon": 10.17, "ships": 3, "names": GHOST_NAMES[:3]},
    {"name": "Italy",   "lat": 37.5,  "lon": 15.1, "ships": 2, "names": GHOST_NAMES[3:5]}
]

# ----------------------
# GLOBAL STATE
# ----------------------
GHOST_STATES = {}  # track ghosts and movement offsets

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
                if line.startswith("$HDT") or line.startswith("$HDG"):
                    try:
                        true_heading = float(line.split(",")[1])
                    except:
                        pass
                elif line.startswith("$GPRMC"):
                    parts = line.split(",")
                    if len(parts) < 9:
                        continue
                    lat_raw, lat_dir = parts[3], parts[4]
                    lon_raw, lon_dir = parts[5], parts[6]
                    if not lat_raw or not lon_raw:
                        continue
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
        except:
            return {}
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
# INITIALIZE GHOSTS FROM LAST POSITIONS
# ----------------------
def initialize_ghost_states():
    fleet = load_positions()
    for ghost_id, positions in fleet.items():
        if ghost_id == REAL_SHIP_ID:
            continue
        if positions:
            last_pos = positions[-1]
            GHOST_STATES[ghost_id] = {
                "name": last_pos.get("name", ghost_id),
                "lat": last_pos["lat"],
                "lon": last_pos["lon"],
                "distance_offset": random.uniform(MIN_DISTANCE_NM, MAX_DISTANCE_NM),
                "bearing_offset": random.uniform(0, 360),
                "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION)
            }

# ----------------------
# MOVE GHOST SMOOTHLY
# ----------------------
def move_ghost(real_lat, real_lon, sog, hdg, ghost_id):
    state = GHOST_STATES[ghost_id]
    # speed with minor variation
    state["speed_bias"] += random.uniform(-0.01, 0.01)
    state["speed_bias"] = max(0.95, min(1.05, state["speed_bias"]))
    ghost_speed = sog * state["speed_bias"]
    ghost_speed = min(ghost_speed, sog * MAX_SPEED_FACTOR)

    # calculate offset position
    rad = math.radians(state["bearing_offset"])
    offset_lat = state["distance_offset"] * math.cos(rad) / 60
    offset_lon = state["distance_offset"] * math.sin(rad) / (60 * math.cos(math.radians(real_lat)))

    # move ghost towards real ship plus offset
    dist_deg = ghost_speed * (UPDATE_INTERVAL / 3600) / 60
    move_rad = math.radians(hdg)
    delta_lat = dist_deg * math.cos(move_rad)
    delta_lon = dist_deg * math.sin(move_rad) / max(0.01, math.cos(math.radians(state["lat"])))

    state["lat"] += delta_lat + offset_lat
    state["lon"] += delta_lon + offset_lon
    ghost_hdg = hdg
    return state["lat"], state["lon"], ghost_speed, ghost_hdg

# ----------------------
# SPAWN ONE NEW GHOST IF IN RENDEZVOUS
# ----------------------
def spawn_one_ghost(real_lat, real_lon):
    for point in RENDEZVOUS_POINTS:
        distance_nm = haversine_nm(real_lat, real_lon, point["lat"], point["lon"])
        if distance_nm < 40:
            for i in range(point["ships"]):
                ghost_id = f"{point['name'].lower()}_{i+1}"
                if ghost_id not in GHOST_STATES:
                    name = point["names"][i % len(point["names"])]
                    GHOST_STATES[ghost_id] = {
                        "name": name,
                        "lat": real_lat + random.uniform(-0.01, 0.01),
                        "lon": real_lon + random.uniform(-0.01, 0.01),
                        "distance_offset": random.uniform(MIN_DISTANCE_NM, MAX_DISTANCE_NM),
                        "bearing_offset": random.uniform(0, 360),
                        "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION)
                    }
                    print(f"👻 Spawned ghost {name} at {point['name']}")
                    return  # only one per update

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
    if result.returncode != 0:
        print("⚠️ Nothing to commit")
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

