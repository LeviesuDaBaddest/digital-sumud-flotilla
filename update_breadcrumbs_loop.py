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
NUM_GHOSTS = 15
BASE_SPEED = 0.00045       # base movement per tick
SPEED_VARIATION = 0.0001   # max additional speed variation
POSITIONS_FILE = "fleet_positions.json"
REAL_SHIP_ID = "al_awda"
UPDATE_INTERVAL = 15  # seconds for testing

# ----------------------
# GLOBAL STATE
# ----------------------
GHOST_STATES = {}  # track per-ghost drift and drift ticks

# ----------------------
# HELPER FUNCTIONS
# ----------------------
def read_position():
    """Read real ship position from Sailaway NMEA"""
    print("⏳ Waiting for NMEA data from Sailaway...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", 10111))
        s.settimeout(10)
        while True:
            raw = s.recv(1024).decode(errors="ignore")
            lines = raw.splitlines()
            for line in lines:
                line = line.strip()
                if line.startswith("$GPRMC"):
                    parts = line.split(",")
                    if len(parts) < 7:
                        continue
                    try:
                        lat_raw = parts[3]
                        lat_dir = parts[4]
                        lon_raw = parts[5]
                        lon_dir = parts[6]
                        if not lat_raw or not lon_raw:
                            continue
                        lat = float(lat_raw[:2]) + float(lat_raw[2:]) / 60.0
                        if lat_dir == "S":
                            lat = -lat
                        lon = float(lon_raw[:3]) + float(lon_raw[3:]) / 60.0
                        if lon_dir == "W":
                            lon = -lon
                        print(f"✅ Got position: {lat}, {lon}")
                        return lat, lon
                    except Exception as e:
                        print("❌ Error parsing GPRMC:", e)
    except Exception as e:
        print("❌ NMEA read error:", e)
    return None, None

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

def move_ghost(last_lat, last_lon, real_lat, real_lon, ghost_id, ghost_index):
    """
    Move ghost toward real ship formation, with fan-out and variable speed.
    """
    # Initialize ghost state if missing
    if ghost_id not in GHOST_STATES:
        GHOST_STATES[ghost_id] = {
            "drift_lat": 0,
            "drift_lon": 0,
            "drift_ticks": 0,
            "speed_multiplier": random.uniform(0.85, 1.15)  # subtle speed variation
        }

    state = GHOST_STATES[ghost_id]

    # Occasionally start a new drift
    if state["drift_ticks"] == 0 and random.random() < 0.05:
        # Wider fan-out offsets
        state["drift_lat"] = random.uniform(-0.00025, 0.00025)
        state["drift_lon"] = random.uniform(-0.00025, 0.00025)
        state["drift_ticks"] = random.randint(10, 35)

    # Formation offsets
    formation_offsets = [
        (0.0001, 0), (-0.0001, 0), (0, 0.0001), (0, -0.0001),
        (0.00007, 0.00007), (-0.00007, -0.00007), (0.00005, -0.00005),
        (-0.00005, 0.00005)
    ]
    offset_lat, offset_lon = formation_offsets[ghost_index % len(formation_offsets)]

    # Target = real ship + formation offset + drift
    target_lat = real_lat + offset_lat + state["drift_lat"]
    target_lon = real_lon + offset_lon + state["drift_lon"]

    # Vector to target
    delta_lat = target_lat - last_lat
    delta_lon = target_lon - last_lon
    distance = math.sqrt(delta_lat**2 + delta_lon**2)
    if distance == 0:
        distance = 1e-6

    # Move toward target with speed variation
    speed = (BASE_SPEED + random.uniform(0, SPEED_VARIATION)) * state["speed_multiplier"]
    move_lat = (delta_lat / distance) * speed
    move_lon = (delta_lon / distance) * speed

    new_lat = last_lat + move_lat
    new_lon = last_lon + move_lon

    # Decrease drift ticks or reset
    if state["drift_ticks"] > 0:
        state["drift_ticks"] -= 1
    else:
        state["drift_lat"] = 0
        state["drift_lon"] = 0

    return new_lat, new_lon

def generate_or_update_ghosts(real_lat, real_lon, fleet):
    """Generate or move ghosts toward real ship formation"""
    for i in range(1, NUM_GHOSTS + 1):
        ghost_id = f"ghost_{i}"
        if ghost_id not in fleet or len(fleet[ghost_id]) == 0:
            offset_lat = (random.random() - 0.5) * 0.01
            offset_lon = (random.random() - 0.5) * 0.01
            last_lat, last_lon = real_lat + offset_lat, real_lon + offset_lon
            fleet[ghost_id] = []
        else:
            last_point = fleet[ghost_id][-1]
            last_lat, last_lon = last_point["lat"], last_point["lon"]

        # Move with fan-out, variable speed, and drift
        new_lat, new_lon = move_ghost(last_lat, last_lon, real_lat, real_lon, ghost_id, i-1)

        fleet[ghost_id].append({
            "lat": new_lat,
            "lon": new_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True,
            "dot": True
        })

        # Limit breadcrumb history
        MAX_BREADCRUMBS = 50
        if len(fleet[ghost_id]) > MAX_BREADCRUMBS:
            fleet[ghost_id].pop(0)

    return fleet

def append_positions(real_lat, real_lon):
    fleet = load_positions()

    # Real ship
    real_point = {
        "lat": real_lat,
        "lon": real_lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ghost": False,
        "dot": True
    }
    if REAL_SHIP_ID not in fleet:
        fleet[REAL_SHIP_ID] = []
    fleet[REAL_SHIP_ID].append(real_point)

    # Limit real ship history
    MAX_REAL_HISTORY = 50
    if len(fleet[REAL_SHIP_ID]) > MAX_REAL_HISTORY:
        fleet[REAL_SHIP_ID].pop(0)

    # Ghost ships
    fleet = generate_or_update_ghosts(real_lat, real_lon, fleet)

    save_positions(fleet)
    print(f"📌 Appended real ship + {NUM_GHOSTS} ghost ships to {POSITIONS_FILE}")

def push_to_git():
    subprocess.run(["git", "add", "-A"])
    result = subprocess.run(["git", "commit", "-m", "🛰️ Auto-update with heartbeat"])
    if result.returncode != 0:
        print("⚠️ Nothing to commit")
    subprocess.run(["git", "push"])
    print("📤 Pushed to GitHub.")

# ----------------------
# MAIN LOOP
# ----------------------
if __name__ == "__main__":
    while True:
        lat, lon = read_position()
        if lat and lon:
            append_positions(lat, lon)
            push_to_git()
        else:
            print("⚠️ No valid position this cycle.")
        print(f"⏲️ Sleeping {UPDATE_INTERVAL} seconds...")
        time.sleep(UPDATE_INTERVAL)


