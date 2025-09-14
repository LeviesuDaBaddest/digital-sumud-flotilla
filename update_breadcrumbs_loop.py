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
BASE_SPEED = 0.0004       # base movement per tick
SPEED_VARIATION = 0.00015
POSITIONS_FILE = "fleet_positions.json"
REAL_SHIP_ID = "al_awda"
UPDATE_INTERVAL = 180  # seconds

# ----------------------
# GLOBAL STATE
# ----------------------
GHOST_STATES = {}

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
    Move ghost in a wide, human-like arc around the real ship, slowly converging back.
    """
    # Initialize ghost state
    if ghost_id not in GHOST_STATES:
        GHOST_STATES[ghost_id] = {
            "angle_offset": random.uniform(-math.pi, math.pi),
            "speed_multiplier": random.uniform(0.85, 1.15),
            "arc_ticks": random.randint(20, 60)
        }

    state = GHOST_STATES[ghost_id]

    # Wide arc movement
    if state["arc_ticks"] > 0:
        # rotate around real ship
        radius = 0.0004 + random.uniform(0, 0.0003)
        state["angle_offset"] += random.uniform(-0.1, 0.1)  # subtle turn
        target_lat = real_lat + radius * math.sin(state["angle_offset"])
        target_lon = real_lon + radius * math.cos(state["angle_offset"])
        state["arc_ticks"] -= 1
    else:
        # converge slowly back to real ship
        target_lat = real_lat + random.uniform(-0.00005, 0.00005)
        target_lon = real_lon + random.uniform(-0.00005, 0.00005)
        # reset arc for next fan-out
        state["arc_ticks"] = random.randint(20, 60)

    # Vector to target
    delta_lat = target_lat - last_lat
    delta_lon = target_lon - last_lon
    distance = math.sqrt(delta_lat**2 + delta_lon**2)
    if distance == 0:
        distance = 1e-6

    speed = (BASE_SPEED + random.uniform(0, SPEED_VARIATION)) * state["speed_multiplier"]
    move_lat = (delta_lat / distance) * speed
    move_lon = (delta_lon / distance) * speed

    new_lat = last_lat + move_lat
    new_lon = last_lon + move_lon

    return new_lat, new_lon

def generate_or_update_ghosts(real_lat, real_lon, fleet):
    for i in range(1, NUM_GHOSTS + 1):
        ghost_id = f"ghost_{i}"
        if ghost_id not in fleet or len(fleet[ghost_id]) == 0:
            # spawn close to real ship
            offset_lat = (random.random() - 0.5) * 0.005
            offset_lon = (random.random() - 0.5) * 0.005
            last_lat, last_lon = real_lat + offset_lat, real_lon + offset_lon
            fleet[ghost_id] = []
        else:
            last_point = fleet[ghost_id][-1]
            last_lat, last_lon = last_point["lat"], last_point["lon"]

        new_lat, new_lon = move_ghost(last_lat, last_lon, real_lat, real_lon, ghost_id, i-1)

        fleet[ghost_id].append({
            "lat": new_lat,
            "lon": new_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True,
            "dot": True
        })

        # Limit breadcrumbs
        MAX_BREADCRUMBS = 50
        if len(fleet[ghost_id]) > MAX_BREADCRUMBS:
            fleet[ghost_id].pop(0)

    return fleet

def append_positions(real_lat, real_lon):
    fleet = load_positions()

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

    MAX_REAL_HISTORY = 50
    if len(fleet[REAL_SHIP_ID]) > MAX_REAL_HISTORY:
        fleet[REAL_SHIP_ID].pop(0)

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



