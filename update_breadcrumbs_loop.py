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
NUM_GHOSTS = 9
UPDATE_INTERVAL = 60  # seconds
SPEED_VARIATION = 0.08  # ±8% variation
POSITIONS_FILE = "fleet_positions.json"
REAL_SHIP_ID = "al_awda"

# ----------------------
# CUSTOM GHOST NAMES
# ----------------------
GHOST_NAMES = [
    "Ma’an", 
    "Al Quds", 
    "Voyage2Gaza", 
    "Resistance", 
    "Humanity", 
    "Olive Branch", 
    "Gamers4Justice", 
    "Hebron", 
    "Khan Younis"
]

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
                    if len(parts) < 8:
                        continue
                    try:
                        lat_raw = parts[3]
                        lat_dir = parts[4]
                        lon_raw = parts[5]
                        lon_dir = parts[6]
                        sog_knots = float(parts[7]) if parts[7] else 0.0
                        cog_deg = float(parts[8]) if parts[8] else 0.0
                        if not lat_raw or not lon_raw:
                            continue
                        lat = float(lat_raw[:2]) + float(lat_raw[2:]) / 60.0
                        if lat_dir == "S":
                            lat = -lat
                        lon = float(lon_raw[:3]) + float(lon_raw[3:]) / 60.0
                        if lon_dir == "W":
                            lon = -lon
                        print(f"✅ Got position: {lat}, {lon} at {sog_knots}kn {cog_deg}°")
                        return lat, lon, sog_knots, cog_deg
                    except Exception as e:
                        print("❌ Error parsing GPRMC:", e)
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

# ----------------------
# GHOST MOVEMENT
# ----------------------
def move_ghost(real_lat, real_lon, sog_knots, cog_deg, ghost_id):
    if ghost_id not in GHOST_STATES:
        GHOST_STATES[ghost_id] = {
            "offset_lat": random.uniform(-0.02, 0.02),
            "offset_lon": random.uniform(-0.02, 0.02),
            "burst_ticks": 0,
            "pause_ticks": 0,
            "swerve_phase": random.uniform(0, math.pi*2),
            "swerve_amp": random.uniform(0.00005, 0.00012),
            "swerve_speed": random.uniform(0.05, 0.15),
            "crossing": False,
            "cross_ticks": 0,
            "group_id": random.randint(1, 3)
        }

    state = GHOST_STATES[ghost_id]

    # Pauses
    if state["pause_ticks"] > 0:
        state["pause_ticks"] -= 1
        return real_lat + state["offset_lat"], real_lon + state["offset_lon"], sog_knots

    if random.random() < 0.02:
        state["pause_ticks"] = random.randint(2, 5)

    # Base speed
    speed_mult = 1.0 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION)
    ghost_speed = sog_knots * speed_mult

    dist_nm = ghost_speed * (UPDATE_INTERVAL / 3600.0)
    dist_deg = dist_nm / 60.0

    # Drift
    drift_lat = random.uniform(-0.00015, 0.00015)
    drift_lon = random.uniform(-0.00015, 0.00015)

    # Bursts
    if state["burst_ticks"] > 0:
        burst_mult = 1.3
        state["burst_ticks"] -= 1
    elif random.random() < 0.05:
        state["burst_ticks"] = random.randint(2, 5)
        burst_mult = 1.3
    else:
        burst_mult = 1.0

    # Swerving
    state["swerve_phase"] += state["swerve_speed"]
    swerve_lat = math.sin(state["swerve_phase"]) * state["swerve_amp"]
    swerve_lon = math.cos(state["swerve_phase"]) * state["swerve_amp"]

    # Move along course
    rad = math.radians(cog_deg)
    delta_lat = dist_deg * math.cos(rad) * burst_mult
    delta_lon = dist_deg * math.sin(rad) * burst_mult / max(0.1, math.cos(math.radians(real_lat)))

    new_lat = real_lat + state["offset_lat"] + delta_lat + drift_lat + swerve_lat
    new_lon = real_lon + state["offset_lon"] + delta_lon + drift_lon + swerve_lon

    return new_lat, new_lon, ghost_speed

def generate_or_update_ghosts(real_lat, real_lon, sog_knots, cog_deg, fleet):
    for i in range(1, NUM_GHOSTS + 1):
        ghost_id = f"ghost_{i}"
        ghost_name = GHOST_NAMES[(i-1) % len(GHOST_NAMES)]

        if ghost_id not in fleet:
            fleet[ghost_id] = []

        new_lat, new_lon, ghost_speed = move_ghost(real_lat, real_lon, sog_knots, cog_deg, ghost_id)

        fleet[ghost_id].append({
            "lat": new_lat,
            "lon": new_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True,
            "name": ghost_name,
            "speed": round(ghost_speed, 2),
            "heading": round(cog_deg, 1)
        })

    return fleet

# ----------------------
# APPEND POSITIONS
# ----------------------
def append_positions(real_lat, real_lon, sog_knots, cog_deg):
    fleet = load_positions()

    # Real ship
    real_point = {
        "lat": real_lat,
        "lon": real_lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ghost": False,
        "name": "Al Awda",
        "speed": round(sog_knots, 2),
        "heading": round(cog_deg, 1)
    }
    if REAL_SHIP_ID not in fleet:
        fleet[REAL_SHIP_ID] = []
    fleet[REAL_SHIP_ID].append(real_point)

    # Ghost ships
    fleet = generate_or_update_ghosts(real_lat, real_lon, sog_knots, cog_deg, fleet)

    save_positions(fleet)
    print(f"📌 Appended real ship + {NUM_GHOSTS} ghost ships to {POSITIONS_FILE}")

# ----------------------
# GIT PUSH
# ----------------------
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
        lat, lon, sog, cog = read_position()
        if lat and lon:
            append_positions(lat, lon, sog, cog)
            push_to_git()
        else:
            print("⚠️ No valid position this cycle.")
        print(f"⏲️ Sleeping {UPDATE_INTERVAL} seconds...")
        time.sleep(UPDATE_INTERVAL)

