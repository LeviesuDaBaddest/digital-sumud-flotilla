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
SPEED_VARIATION = 0.05  # smaller variation for smoother speeds
POSITIONS_FILE = "fleet_positions.json"
REAL_SHIP_ID = "al_awda"
MAX_SPEED_FACTOR = 1.05  # ghosts cannot exceed 105% of real ship speed
MIN_DISTANCE_NM = 0.05  # minimum distance offset from real ship
MAX_DISTANCE_NM = 0.5   # maximum distance offset from real ship

# Group/flock behaviour
FLOCK_PERIOD = 300.0            # seconds: how long one breathe/fan cycle takes
FAN_AMPLITUDE_NM = 0.25         # how wide the group fans out (nm)
CONVERGENCE_STRENGTH = 0.12     # how aggressively ghosts steer back to slot
SLOT_OSCILLATION_BEARING = 8.0  # degrees of bearing oscillation per ghost
SLOT_OSCILLATION_DISTANCE = 0.18  # nm of distance oscillation per ghost

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

def deg_normalize(angle):
    """Normalize to [-180, 180)"""
    a = (angle + 180) % 360 - 180
    return a

# ----------------------
# INITIALIZE GHOSTS FROM LAST POSITIONS
# ----------------------
def initialize_ghost_states():
    fleet = load_positions()
    # If there are existing ghost entries in the JSON, reuse them (but assign formation slots)
    for ghost_id, positions in fleet.items():
        if ghost_id == REAL_SHIP_ID:
            continue
        if positions:
            last_pos = positions[-1]
            # each ghost gets:
            # - name (friendly)
            # - lat/lon resume
            # - slot_bearing + slot_distance (formation slot relative to real ship heading)
            # - phase for oscillations so they aren't all identical
            slot_bearing = random.uniform(-60, 60)  # prefer behind/around the ship
            slot_distance = random.uniform(MIN_DISTANCE_NM, MAX_DISTANCE_NM)
            GHOST_STATES[ghost_id] = {
                "name": last_pos.get("name", ghost_id),
                "lat": last_pos["lat"],
                "lon": last_pos["lon"],
                "slot_bearing": slot_bearing,
                "slot_distance": slot_distance,
                "phase": random.uniform(0, 2*math.pi),
                "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION),
                "hdg": last_pos.get("heading", 0.0)
            }

# ----------------------
# MOVE GHOST: breathing + converge + gentle pursuit
# ----------------------
def move_ghost(real_lat, real_lon, sog, hdg, ghost_id):
    state = GHOST_STATES[ghost_id]
    now = time.time()

    # small speed bias variation but constrained
    state["speed_bias"] += random.uniform(-0.005, 0.005)
    state["speed_bias"] = max(0.92, min(1.08, state["speed_bias"]))

    # natural ghost speed, smoothed and capped relative to real ship
    ghost_speed = sog * state["speed_bias"]
    ghost_speed = min(ghost_speed, sog * MAX_SPEED_FACTOR)
    if ghost_speed < 0.1:
        ghost_speed = 0.1

    # group-wide fan factor (sinusoidal)
    flock_phase = (now / FLOCK_PERIOD) * 2 * math.pi
    group_fan = math.sin(flock_phase)  # -1..1
    fan_offset = group_fan * FAN_AMPLITUDE_NM

    # per-ghost oscillation (gives breathing + individual variation)
    oscill_bearing = math.sin(now * 0.6 + state["phase"]) * SLOT_OSCILLATION_BEARING
    oscill_distance = math.sin(now * 0.35 + state["phase"]) * SLOT_OSCILLATION_DISTANCE

    # dynamic slot = base slot + group fan + per-ghost oscillation
    dynamic_distance = max(MIN_DISTANCE_NM, min(MAX_DISTANCE_NM + FAN_AMPLITUDE_NM,
                                               state["slot_distance"] + fan_offset + oscill_distance))
    dynamic_bearing = state["slot_bearing"] + oscill_bearing

    # convert dynamic slot relative to real ship heading (so formation rotates with ship)
    total_bearing = (hdg + dynamic_bearing) % 360
    rad = math.radians(total_bearing)
    target_lat = real_lat + (dynamic_distance * math.cos(rad)) / 60.0
    target_lon = real_lon + (dynamic_distance * math.sin(rad)) / (60.0 * math.cos(math.radians(real_lat)))

    # compute vector from ghost to target
    dlat = target_lat - state["lat"]
    dlon = target_lon - state["lon"]
    # bearing to target (atan2 with lon, lat)
    bearing_to_target = math.degrees(math.atan2(dlon, dlat)) % 360

    # compute smallest angle difference from ghost heading to bearing_to_target
    current_hdg = state.get("hdg", hdg)
    angle_diff = deg_normalize(bearing_to_target - current_hdg)

    # adjust heading gradually toward the target (convergence)
    heading_adjust = angle_diff * CONVERGENCE_STRENGTH
    # add tiny random jitter to avoid robotic motion
    heading_adjust += random.uniform(-0.7, 0.7)
    new_hdg = (current_hdg + heading_adjust) % 360
    state["hdg"] = new_hdg

    # move ghost forward along its heading by ghost_speed (converted to degrees)
    move_dist_deg = ghost_speed * (UPDATE_INTERVAL / 3600) / 60.0
    move_rad = math.radians(new_hdg)
    delta_lat = move_dist_deg * math.cos(move_rad)
    delta_lon = move_dist_deg * math.sin(move_rad) / max(0.0001, math.cos(math.radians(state["lat"])))

    # Apply a small attraction toward the target (so they don't just orbit)
    attraction_strength = 0.35  # how much of the target vector to apply per update (0..1)
    state["lat"] += delta_lat + dlat * attraction_strength * 0.02
    state["lon"] += delta_lon + dlon * attraction_strength * 0.02

    return state["lat"], state["lon"], ghost_speed, new_hdg

# ----------------------
# SPAWN ONE NEW GHOST IF IN RENDEZVOUS
# ----------------------
def spawn_one_ghost(real_lat, real_lon):
    # We'll spawn only one ghost per update. Choose original ghosts first (if any missing names),
    # then rendezvous ghosts.
    # Determine used friendly names
    used_names = {s["name"] for s in GHOST_STATES.values()}

    # Spawn original named ghosts first (if any not present)
    for name in GHOST_NAMES:
        if name not in used_names:
            # create a stable ID using the name
            ghost_id = f"ghost_{name.lower().replace(' ', '_')}"
            # slot around the ship: prefer behind (negative bearing) with small spread
            slot_bearing = random.uniform(-35, 35) * -1  # slightly behind by default
            slot_distance = random.uniform(MIN_DISTANCE_NM, MAX_DISTANCE_NM)
            GHOST_STATES[ghost_id] = {
                "name": name,
                "lat": real_lat + random.uniform(-0.01, 0.01),
                "lon": real_lon + random.uniform(-0.01, 0.01),
                "slot_bearing": slot_bearing,
                "slot_distance": slot_distance,
                "phase": random.uniform(0, 2*math.pi),
                "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION),
                "hdg": None
            }
            print(f"👻 Spawned named ghost {name}")
            return

    # Spawn rendezvous ghosts if inside a point
    for point in RENDEZVOUS_POINTS:
        distance_nm = haversine_nm(real_lat, real_lon, point["lat"], point["lon"])
        if distance_nm < 40:
            names = point.get("names", [])
            for i in range(point["ships"]):
                # ID unique per rendezvous slot
                ghost_id = f"{point['name'].lower()}_{i+1}"
                if ghost_id not in GHOST_STATES:
                    name = names[i % len(names)] if names else ghost_id
                    # assign slot_bearing spread across the formation so they don't all stack
                    base_bearing = -20 + (i - (point["ships"]-1)/2) * 12  # spread across +/- ~30deg
                    slot_bearing = base_bearing + random.uniform(-6, 6)
                    slot_distance = random.uniform(MIN_DISTANCE_NM, MAX_DISTANCE_NM)
                    GHOST_STATES[ghost_id] = {
                        "name": name,
                        "lat": real_lat + random.uniform(-0.01, 0.01),
                        "lon": real_lon + random.uniform(-0.01, 0.01),
                        "slot_bearing": slot_bearing,
                        "slot_distance": slot_distance,
                        "phase": random.uniform(0, 2*math.pi),
                        "speed_bias": 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION),
                        "hdg": None
                    }
                    print(f"👻 Spawned rendezvous ghost {name} at {point['name']}")
                    return  # only spawn one per update

# ----------------------
# GENERATE OR UPDATE ALL GHOSTS
# ----------------------
def generate_or_update_ghosts(real_lat, real_lon, sog, hdg, fleet):
    for ghost_id, state in list(GHOST_STATES.items()):
        fleet.setdefault(ghost_id, [])
        new_lat, new_lon, ghost_speed, ghost_hdg = move_ghost(real_lat, real_lon, sog, hdg, ghost_id)
        # ensure friendly name output
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

