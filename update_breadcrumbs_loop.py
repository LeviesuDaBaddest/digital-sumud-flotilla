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
    """Ghosts sail in loose formation with swerves, groups, arcs, bursts, and pauses"""
    if ghost_id not in GHOST_STATES:
        GHOST_STATES[ghost_id] = {
            "offset_lat": random.uniform(-0.02, 0.02),   # spawn ~1–2 km
            "offset_lon": random.uniform(-0.02, 0.02),
            "burst_ticks": 0,
            "pause_ticks": 0,
            "swerve_phase": random.uniform(0, math.pi*2),
            "swerve_amp": random.uniform(0.00005, 0.00012),
            "swerve_speed": random.uniform(0.05, 0.15),
            "crossing": False,
            "cross_ticks": 0,
            "group_id": random.randint(1, 3)  # small packs
        }

    state = GHOST_STATES[ghost_id]

    # Pauses
    if state["pause_ticks"] > 0:
        state["pause_ticks"] -= 1
        return real_lat + state["offset_lat"], real_lon + state["offset_lon"]

    if random.random() < 0.02:  # 2% chance to pause
        state["pause_ticks"] = random.randint(2, 5)

    # Base speed = your speed ± variation
    speed_mult = 1.0 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION)
    ghost_speed = sog_knots * speed_mult

    # Distance travelled this tick (nm → degrees)
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

    # Crossings
    if not state["crossing"] and random.random() < 0.01:
        state["crossing"] = True
        state["cross_ticks"] = random.randint(4, 10)
        state["cross_angle"] = random.choice([math.pi/2, -math.pi/2])

    if state["crossing"]:
        overshoot = 0.0002
        swerve_lat += overshoot * math.sin(state["cross_angle"])
        swerve_lon += overshoot * math.cos(state["cross_angle"])
        state["cross_ticks"] -= 1
        if state["cross_ticks"] <= 0:
            state["crossing"] = False

    # Grouping: ghosts in same group share slight attraction
    group_pull_lat = 0
    group_pull_lon = 0
    for other_id, other in GHOST_STATES.items():
        if other_id == ghost_id:
            continue
        if other["group_id"] == state["group_id"]:
            group_pull_lat += (other["offset_lat"] - state["offset_lat"]) * 0.01
            group_pull_lon += (other["offset_lon"] - state["offset_lon"]) * 0.01
    state["offset_lat"] += group_pull_lat
    state["offset_lon"] += group_pull_lon

    # Move forward along course
    rad = math.radians(cog_deg)
    delta_lat = dist_deg * math.cos(rad) * burst_mult
    delta_lon = dist_deg * math.sin(rad) * burst_mult / max(0.1, math.cos(math.radians(real_lat)))

    new_lat = real_lat + state["offset_lat"] + delta_lat + drift_lat + swerve_lat
    new_lon = real_lon + state["offset_lon"] + delta_lon + drift_lon + swerve_lon

    return new_lat, new_lon

def generate_or_update_ghosts(real_lat, real_lon, sog_knots, cog_deg, fleet):
    for i in range(1, NUM_GHOSTS + 1):
        ghost_id = f"ghost_{i}"
        if ghost_id not in fleet:
            fleet[ghost_id] = []

        new_lat, new_lon = move_ghost(real_lat, real_lon, sog_knots, cog_deg, ghost_id)

        fleet[ghost_id].append({
            "lat": new_lat,
            "lon": new_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True,
            "dot": True
        })

    return fleet

def append_positions(real_lat, real_lon, sog_knots, cog_deg):
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

    fleet = generate_or_update_ghosts(real_lat, real_lon, sog_knots, cog_deg, fleet)
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
        lat, lon, sog, cog = read_position()
        if lat and lon:
            append_positions(lat, lon, sog, cog)
            push_to_git()
        else:
            print("⚠️ No valid position this cycle.")
        print(f"⏲️ Sleeping {UPDATE_INTERVAL} seconds...")
        time.sleep(UPDATE_INTERVAL)



