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
UPDATE_INTERVAL = 300  # seconds
SPEED_VARIATION = 0.05
POSITIONS_FILE = "fleet_positions.json"
REAL_SHIP_ID = "al_awda"
MAX_SPEED_FACTOR = 1.08
MIN_DISTANCE_NM = 0.03
MAX_DISTANCE_NM = 0.6

FLOCK_PERIOD = 240.0
FAN_AMPLITUDE_NM = 0.25
CONVERGENCE_STRENGTH = 0.14
SLOT_OSCILLATION_BEARING = 6.0
SLOT_OSCILLATION_DISTANCE = 0.12
LEADER_SWAP_CHANCE = 0.02

# ----------------------
# GHOST NAMES & RENDEZVOUS
# ----------------------
GHOST_NAMES = ["Ma’an", "Navaren", "Al Quds", "Ramallah", "Ode", "Miami"]
CYPRUS_NAMES = ["Gaza City", "Freedom", "Argo", "Brune", "Inman"]
RENDEZVOUS_POINTS = [
    {"name": "Cyprus", "lat": 35.16, "lon": 33.36, "ships": 5, "names": CYPRUS_NAMES},
    {"name": "Koufonisi", "lat": 36.9335, "lon": 25.6020, "ships": 2, "names": ["Serenity", "Puppet"]},
    {"name": "Tunisia", "lat": 36.8189, "lon": 10.3050, "ships": 3, "names": ["Serene", "Union", "Elite III"]},
    {"name": "Italy", "lat": 37.0600, "lon": 15.2930, "ships": 2, "names": GHOST_NAMES[3:5]}
]

# ----------------------
# GLOBAL STATE
# ----------------------
GHOST_STATES = {}
LAST_LEADER_CHECK = time.time()

# ----------------------
# HELPERS
# ----------------------
def read_position():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", 10111))
        s.settimeout(10)
        true_heading = None
        while True:
            raw = s.recv(4096).decode(errors="ignore")
            for line in raw.splitlines():
                if line.startswith("$HDT") or line.startswith("$HDG"):
                    try:
                        true_heading = float(line.split(",")[1])
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
                    hdg = true_heading if true_heading is not None else (cog if cog is not None else 0.0)
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

def deg_normalize(angle):
    return (angle + 180) % 360 - 180

def assign_role():
    r = random.random()
    if r < 0.12: return "leader"
    if r < 0.28: return "rear"
    return "flank"

# ----------------------
# INITIALIZE GHOSTS
# ----------------------
def initialize_ghost_states():
    fleet = load_positions()
    for ghost_id, positions in fleet.items():
        if ghost_id == REAL_SHIP_ID: continue
        if positions:
            last_pos = positions[-1]
            slot_bearing = random.uniform(-40, 40)
            slot_distance = random.uniform(MIN_DISTANCE_NM, MAX_DISTANCE_NM)
            GHOST_STATES[ghost_id] = {
                "name": last_pos.get("name", ghost_id),
                "lat": last_pos["lat"],
                "lon": last_pos["lon"],
                "slot_bearing": slot_bearing,
                "slot_distance": slot_distance,
                "phase": random.uniform(0, 2*math.pi),
                "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION),
                "hdg": last_pos.get("heading", 0.0) or 0.0,
                "role": assign_role(),
                "last_burst": 0.0
            }

# ----------------------
# MOVE GHOST
# ----------------------
def move_ghost(real_lat, real_lon, sog, hdg, ghost_id):
    state = GHOST_STATES[ghost_id]
    now = time.time()
    hdg = hdg or 0.0
    state["hdg"] = state.get("hdg", hdg) or hdg

    # Speed & burst
    state["speed_bias"] += random.uniform(-0.004, 0.004)
    state["speed_bias"] = max(0.90, min(1.10, state["speed_bias"]))
    target_speed = min(sog * state["speed_bias"], sog * MAX_SPEED_FACTOR)
    if target_speed < 0.08: target_speed = 0.08
    burst_multiplier = 1.0
    if random.random() < 0.01 and now - state.get("last_burst", 0) > 600:
        burst_multiplier = 1.12 + random.random()*0.06
        state["last_burst"] = now
    ghost_speed = target_speed * burst_multiplier

    # Flock + oscillation
    flock_phase = (now / FLOCK_PERIOD) * 2 * math.pi
    group_fan = math.sin(flock_phase)
    fan_offset = group_fan * FAN_AMPLITUDE_NM
    oscill_bearing = math.sin(now*0.6 + state["phase"]) * SLOT_OSCILLATION_BEARING
    oscill_distance = math.sin(now*0.35 + state["phase"]) * SLOT_OSCILLATION_DISTANCE

    # Role offsets
    role = state.get("role", "flank")
    role_distance_bias = role_bearing_bias = 0.0
    role_speed_bias = 1.0
    if role == "leader":
        role_distance_bias, role_bearing_bias, role_speed_bias = -0.08, -6, 1.02
    elif role == "rear":
        role_distance_bias, role_bearing_bias, role_speed_bias = 0.12, 6, 0.98
    elif role == "flank":
        role_distance_bias = random.uniform(-0.04, 0.04)
        role_bearing_bias = random.uniform(-8, 8)

    # Dynamic position
    dynamic_distance = max(MIN_DISTANCE_NM, min(MAX_DISTANCE_NM + FAN_AMPLITUDE_NM,
                                               state["slot_distance"] + fan_offset + oscill_distance + role_distance_bias))
    dynamic_bearing = state["slot_bearing"] + oscill_bearing + role_bearing_bias
    total_bearing = (hdg + dynamic_bearing) % 360
    br = math.radians(total_bearing)
    target_lat = real_lat + (dynamic_distance * math.cos(br))/60.0
    target_lon = real_lon + (dynamic_distance * math.sin(br))/(60.0*math.cos(math.radians(real_lat)))

    # Movement vector
    dlat = target_lat - state["lat"]
    dlon = target_lon - state["lon"]
    bearing_to_target = math.degrees(math.atan2(dlon, dlat)) % 360
    current_hdg = state.get("hdg") or hdg
    angle_diff = deg_normalize(bearing_to_target - current_hdg)
    heading_adjust = angle_diff * CONVERGENCE_STRENGTH + random.uniform(-0.9, 0.9)
    new_hdg = (current_hdg + heading_adjust) % 360
    state["hdg"] = new_hdg

    move_dist_deg = ghost_speed * (UPDATE_INTERVAL / 3600.0) / 60.0
    move_rad = math.radians(new_hdg)
    delta_lat = move_dist_deg * math.cos(move_rad)
    delta_lon = move_dist_deg * math.sin(move_rad) / max(0.0001, math.cos(math.radians(state["lat"])))

    # Attraction
    state["lat"] += delta_lat + dlat*0.28*0.03
    state["lon"] += delta_lon + dlon*0.28*0.03
    ghost_speed *= role_speed_bias

    # Leader swap
    global LAST_LEADER_CHECK
    if now - LAST_LEADER_CHECK > 600 and random.random() < LEADER_SWAP_CHANCE:
        LAST_LEADER_CHECK = now
        ids = list(GHOST_STATES.keys())
        if ids:
            chosen = random.choice(ids)
            for gid, s in GHOST_STATES.items():
                if gid == chosen:
                    s["role"] = "leader"
                elif s.get("role") == "leader":
                    s["role"] = assign_role()

    return state["lat"], state["lon"], round(ghost_speed,2), round(new_hdg,1)

# ----------------------
# SPAWN GHOSTS IMMEDIATELY
# ----------------------
def spawn_one_ghost(real_lat, real_lon):
    used_names = {s["name"] for s in GHOST_STATES.values()}
    # Fleet ghosts
    for name in GHOST_NAMES:
        if name not in used_names:
            ghost_id = f"ghost_{name.lower().replace(' ','_')}"
            GHOST_STATES[ghost_id] = {
                "name": name,
                "lat": real_lat + random.uniform(-0.008,0.008),
                "lon": real_lon + random.uniform(-0.008,0.008),
                "slot_bearing": random.uniform(-32,32),
                "slot_distance": random.uniform(MIN_DISTANCE_NM, MAX_DISTANCE_NM),
                "phase": random.uniform(0,2*math.pi),
                "speed_bias": 1 + random.uniform(-SPEED_VARIATION,SPEED_VARIATION),
                "hdg": 0.0,
                "role": assign_role(),
                "last_burst": 0.0
            }
            print(f"👻 Spawned named ghost {name}")
            break
    # Rendezvous ghosts
    for point in RENDEZVOUS_POINTS:
        distance_nm = haversine_nm(real_lat, real_lon, point["lat"], point["lon"])
        if distance_nm < 150:
            names = point.get("names", [])
            for i in range(point["ships"]):
                ghost_id = f"{point['name'].lower()}_{i+1}"
                if ghost_id not in GHOST_STATES:
                    name = names[i % len(names)] if names else ghost_id
                    GHOST_STATES[ghost_id] = {
                        "name": name,
                        "lat": real_lat + random.uniform(-0.008,0.008),
                        "lon": real_lon + random.uniform(-0.008,0.008),
                        "slot_bearing": random.uniform(-32,32),
                        "slot_distance": random.uniform(MIN_DISTANCE_NM, MAX_DISTANCE_NM),
                        "phase": random.uniform(0,2*math.pi),
                        "speed_bias": 1 + random.uniform(-SPEED_VARIATION,SPEED_VARIATION),
                        "hdg": 0.0,
                        "role": assign_role(),
                        "last_burst": 0.0
                    }
                    print(f"👻 Spawned rendezvous ghost {name} at {point['name']}")

# ----------------------
# UPDATE & APPEND
# ----------------------
def generate_or_update_ghosts(real_lat, real_lon, sog, hdg, fleet):
    for ghost_id, state in list(GHOST_STATES.items()):
        fleet.setdefault(ghost_id, [])
        new_lat, new_lon, ghost_speed, ghost_hdg = move_ghost(real_lat, real_lon, sog, hdg, ghost_id)
        fleet[ghost_id].append({
            "lat": new_lat,
            "lon": new_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True,
            "name": state["name"],
            "speed": ghost_speed,
            "heading": ghost_hdg
        })
    return fleet

def append_positions(real_lat, real_lon, sog, hdg):
    fleet = load_positions()
    fleet.setdefault(REAL_SHIP_ID, []).append({
        "lat": real_lat,
        "lon": real_lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ghost": False,
        "name": "Al Awda",
        "speed": round(sog,2),
        "heading": round(hdg or 0.0,1)
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
    print("🚀 Starting Virtual Voyage To Gaza Tracker (alive flotilla)...")
    initialize_ghost_states()
    while True:
        lat, lon, sog, hdg = read_position()
        if lat and lon:
            append_positions(lat, lon, sog, hdg)
            push_to_git()
        print(f"⏲️ Sleeping {UPDATE_INTERVAL} seconds...")
        time.sleep(UPDATE_INTERVAL)

