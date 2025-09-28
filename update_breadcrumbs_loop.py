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
NUM_GHOSTS = 4  # Original ghosts
UPDATE_INTERVAL = 600  # seconds
SPEED_VARIATION = 0.08
POSITIONS_FILE = "fleet_positions.json"
REAL_SHIP_ID = "al_awda"
PHASED_SPAWN_INTERVAL = 600

# ----------------------
# CUSTOM GHOST NAMES
# ----------------------
GHOST_NAMES = ["Ma’an", "Navaren", "Al Quds", "Ramallah"]
CYPRUS_NAMES = ["Gaza City", "Freedom", "Argo", "Brune", "Inman"]

# ----------------------
# RENDEZVOUS POINTS
# ----------------------
RENDEZVOUS = [
    {"name": "Cyprus",  "lat": 35.16, "lon": 33.36, "ships": 5, "spawned": False},
    {"name": "Tunisia", "lat": 36.8,  "lon": 10.17, "ships": 3, "spawned": False},
    {"name": "Italy",   "lat": 37.5,  "lon": 15.1, "ships": 2, "spawned": False}
]

# ----------------------
# GLOBAL STATE
# ----------------------
GHOST_STATES = {}
PHASED_SPAWN_QUEUE = {}
LAST_SPAWN_TIME = {}

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
# MOVE GHOST
# ----------------------
def move_ghost(real_lat, real_lon, sog, hdg, ghost_id):
    if ghost_id not in GHOST_STATES:
        GHOST_STATES[ghost_id] = {
            "rel_bearing": random.uniform(0, 360),
            "rel_distance": random.uniform(0.05, 0.8),
            "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION),
            "heading_jitter": random.uniform(-5, 5),
            "current_nudge": random.uniform(-0.02, 0.02)
        }
    state = GHOST_STATES[ghost_id]
    state["speed_bias"] += random.uniform(-0.01, 0.01)
    state["speed_bias"] = max(0.85, min(1.15, state["speed_bias"]))
    state["heading_jitter"] += random.uniform(-0.5, 0.5)
    state["heading_jitter"] = max(-15, min(15, state["heading_jitter"]))
    state["current_nudge"] += random.uniform(-0.005, 0.005)
    state["current_nudge"] = max(-0.03, min(0.03, state["current_nudge"]))

    ghost_speed = sog * state["speed_bias"]
    dist_deg = ghost_speed * (UPDATE_INTERVAL / 3600) / 60
    move_heading = hdg + state["heading_jitter"]
    rad = math.radians(move_heading)
    delta_lat = dist_deg * math.cos(rad) + state["current_nudge"]
    delta_lon = dist_deg * math.sin(rad) / max(0.1, math.cos(math.radians(real_lat))) + state["current_nudge"]

    rel_rad = math.radians(hdg + state["rel_bearing"])
    rel_lat = state["rel_distance"] * math.cos(rel_rad) / 60.0
    rel_lon = state["rel_distance"] * math.sin(rel_rad) / (60.0 * math.cos(math.radians(real_lat)))

    new_lat = real_lat + rel_lat + delta_lat
    new_lon = real_lon + rel_lon + delta_lon
    ghost_hdg = (hdg + state["heading_jitter"]) % 360

    return new_lat, new_lon, ghost_speed, ghost_hdg

# ----------------------
# SPAWN SINGLE SHIP NEAR ORIGIN
# ----------------------
def spawn_single_ship(origin_lat, origin_lon, ghost_id, ship_name):
    if ghost_id not in GHOST_STATES:
        GHOST_STATES[ghost_id] = {
            "rel_bearing": random.uniform(0, 360),
            "rel_distance": random.uniform(0.05, 0.6),
            "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION),
            "heading_jitter": random.uniform(-5, 5),
            "current_nudge": random.uniform(-0.02, 0.02)
        }
    state = GHOST_STATES[ghost_id]
    rel_rad = math.radians(state["rel_bearing"])
    rel_lat = state["rel_distance"] * math.cos(rel_rad) / 60.0
    rel_lon = state["rel_distance"] * math.sin(rel_rad) / (60.0 * math.cos(math.radians(origin_lat)))
    return origin_lat + rel_lat, origin_lon + rel_lon

# ----------------------
# GENERATE OR UPDATE ALL GHOSTS
# ----------------------
def generate_or_update_ghosts(real_lat, real_lon, sog, hdg, fleet):
    all_ghost_ids = [f"ghost_{i}" for i in range(1, NUM_GHOSTS+1)]
    # Include all phased ghosts currently spawned
    for queue in PHASED_SPAWN_QUEUE.values():
        all_ghost_ids.extend([ship["id"] for ship in queue])

    for ghost_id in all_ghost_ids:
        # Determine ghost name
        if ghost_id.startswith("ghost_"):
            name = GHOST_NAMES[int(ghost_id.split("_")[1]) - 1]
        else:
            # Look up name from phased queue if necessary
            name = None
            for queue in PHASED_SPAWN_QUEUE.values():
                for ship in queue:
                    if ship["id"] == ghost_id:
                        name = ship["name"]
                        break
        name = name or ghost_id

        fleet.setdefault(ghost_id, [])
        new_lat, new_lon, ghost_speed, ghost_hdg = move_ghost(real_lat, real_lon, sog, hdg, ghost_id)
        fleet[ghost_id].append({
            "lat": new_lat,
            "lon": new_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True,
            "name": name,
            "speed": round(ghost_speed, 2),
            "heading": round(ghost_hdg, 1)
        })
    return fleet

# ----------------------
# CHECK RENDEZVOUS
# ----------------------
def check_rendezvous(real_lat, real_lon, fleet):
    now = time.time()
    for point in RENDEZVOUS:
        distance_nm = haversine_nm(real_lat, real_lon, point["lat"], point["lon"])
        if distance_nm < 40:
            if point["name"] not in PHASED_SPAWN_QUEUE:
                names = CYPRUS_NAMES if point["name"] == "Cyprus" else [f"{point['name']} Ship {i}" for i in range(point["ships"])]
                PHASED_SPAWN_QUEUE[point["name"]] = [{"id": f"{point['name'].lower()}_{i+1}", "name": names[i]} for i in range(point["ships"])]
                LAST_SPAWN_TIME[point["name"]] = now - PHASED_SPAWN_INTERVAL

            queue = PHASED_SPAWN_QUEUE[point["name"]]
            if queue and now - LAST_SPAWN_TIME[point["name"]] >= PHASED_SPAWN_INTERVAL:
                ship = queue.pop(0)
                initial_lat, initial_lon = spawn_single_ship(real_lat, real_lon, ship["id"], ship["name"])
                # Immediately "latch" ghost by adding to fleet and GHOST_STATES
                fleet.setdefault(ship["id"], []).append({
                    "lat": initial_lat,
                    "lon": initial_lon,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "ghost": True,
                    "name": ship["name"],
                    "speed": 0.0,
                    "heading": 0.0
                })
                move_ghost(real_lat, real_lon, 0.0, 0.0, ship["id"])  # Initialize movement state
                LAST_SPAWN_TIME[point["name"]] = now
            elif not queue:
                point["spawned"] = True

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
        "speed": round(sog,2),
        "heading": round(hdg,1)
    })
    fleet = generate_or_update_ghosts(real_lat, real_lon, sog, hdg, fleet)
    check_rendezvous(real_lat, real_lon, fleet)
    save_positions(fleet)
    print(f"📌 Appended real ship + {NUM_GHOSTS} ghost ships + phased ships.")

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
    while True:
        lat, lon, sog, hdg = read_position()
        if lat and lon:
            append_positions(lat, lon, sog, hdg)
            push_to_git()
        print(f"⏲️ Sleeping {UPDATE_INTERVAL} seconds...")
        time.sleep(UPDATE_INTERVAL)
