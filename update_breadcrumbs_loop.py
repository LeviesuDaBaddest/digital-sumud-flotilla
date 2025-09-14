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
UPDATE_INTERVAL = 60  # seconds

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
    """Move ghost realistically near the real ship, arcs, bursts, pauses, human-like"""

    if ghost_id not in GHOST_STATES:
        GHOST_STATES[ghost_id] = {
            "angle_offset": random.uniform(-math.pi, math.pi),
            "speed_multiplier": random.uniform(0.85, 1.15),
            "arc_ticks": random.randint(15, 40),
            "burst_wait": random.randint(5, 15),
            "burst_active": False,
            "pause_ticks": 0,
            "drift_lat": 0,
            "drift_lon": 0,
            "course_correction": 0
        }

    state = GHOST_STATES[ghost_id]

    # -----------------
    # Pause & small drift
    # -----------------
    if state["pause_ticks"] > 0:
        state["pause_ticks"] -= 1
        return last_lat + state["drift_lat"], last_lon + state["drift_lon"]

    if random.random() < 0.02 and state["pause_ticks"] == 0:
        state["pause_ticks"] = random.randint(2, 5)
        state["drift_lat"] = random.uniform(-0.00001, 0.00001)
        state["drift_lon"] = random.uniform(-0.00001, 0.00001)

    # -----------------
    # Distance to real ship
    # -----------------
    delta_lat_real = real_lat - last_lat
    delta_lon_real = real_lon - last_lon
    distance_to_real = math.hypot(delta_lat_real, delta_lon_real)

    # -----------------
    # Burst if slightly behind
    # -----------------
    MIN_DISTANCE = 0.00003
    MAX_DISTANCE = 0.00012
    if not state["burst_active"] and state["burst_wait"] <= 0 and MIN_DISTANCE < distance_to_real < MAX_DISTANCE and random.random() < 0.35:
        state["burst_active"] = True
        state["burst_ticks"] = random.randint(3, 7)
        state["speed_multiplier"] *= random.uniform(1.2, 1.35)
        state["burst_wait"] = random.randint(15, 25)
    else:
        state["burst_wait"] -= 1

    # -----------------
    # Arc movement close to ship
    # -----------------
    if state["arc_ticks"] > 0:
        radius = 0.00008 + random.uniform(0, 0.00004)
        state["angle_offset"] += random.uniform(-0.05, 0.05)
        state["course_correction"] = random.uniform(-0.00001, 0.00001)
        target_lat = real_lat + radius * math.sin(state["angle_offset"]) + state["drift_lat"] + state["course_correction"]
        target_lon = real_lon + radius * math.cos(state["angle_offset"]) + state["drift_lon"] + state["course_correction"]
        state["arc_ticks"] -= 1
    else:
        target_lat = real_lat + random.uniform(-0.000015, 0.000015) + state["drift_lat"]
        target_lon = real_lon + random.uniform(-0.000015, 0.000015) + state["drift_lon"]
        state["arc_ticks"] = random.randint(15, 40)

    # -----------------
    # Move vector
    # -----------------
    delta_lat = target_lat - last_lat
    delta_lon = target_lon - last_lon
    distance = math.sqrt(delta_lat**2 + delta_lon**2)
    if distance == 0:
        distance = 1e-6

    speed = (BASE_SPEED + random.uniform(0, SPEED_VARIATION)) * state["speed_multiplier"]

    if state.get("burst_active", False):
        state["burst_ticks"] -= 1
        if state["burst_ticks"] <= 0:
            state["burst_active"] = False
            state["speed_multiplier"] = random.uniform(0.85, 1.15)

    move_lat = (delta_lat / distance) * speed
    move_lon = (delta_lon / distance) * speed

    new_lat = last_lat + move_lat
    new_lon = last_lon + move_lon

    return new_lat, new_lon

def generate_or_update_ghosts(real_lat, real_lon, fleet):
    for i in range(1, NUM_GHOSTS + 1):
        ghost_id = f"ghost_{i}"
        if ghost_id not in fleet or len(fleet[ghost_id]) == 0:
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

        # Keep all breadcrumbs, no limit

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



