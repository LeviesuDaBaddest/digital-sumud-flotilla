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
GHOST_MAX_SPEED = 0.00005  # degrees per tick (adjust for realism)
POSITIONS_FILE = "positions.json"
REAL_SHIP_ID = "al_awda"

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

def move_ghost(last_lat, last_lon):
    """Apply a small movement vector to simulate sailing drift"""
    angle = random.uniform(0, 2*math.pi)  # random heading
    speed = random.uniform(0, GHOST_MAX_SPEED)
    new_lat = last_lat + math.cos(angle) * speed
    new_lon = last_lon + math.sin(angle) * speed
    return new_lat, new_lon

def generate_or_update_ghosts(real_lat, real_lon, fleet):
    """Generate new ghosts if missing, otherwise move them smoothly"""
    for i in range(1, NUM_GHOSTS + 1):
        ghost_id = f"ghost_{i}"
        if ghost_id not in fleet:
            # spawn near real ship initially
            offset_lat = (random.random() - 0.5) * 0.01
            offset_lon = (random.random() - 0.5) * 0.01
            last_lat, last_lon = real_lat + offset_lat, real_lon + offset_lon
            fleet[ghost_id] = []
        else:
            last_point = fleet[ghost_id][-1]
            last_lat, last_lon = last_point["lat"], last_point["lon"]

        new_lat, new_lon = move_ghost(last_lat, last_lon)
        fleet[ghost_id].append({
            "lat": new_lat,
            "lon": new_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True,
            "dot": True
        })
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

    # Ghost ships
    fleet = generate_or_update_ghosts(real_lat, real_lon, fleet)

    save_positions(fleet)
    print(f"📌 Appended real ship + {NUM_GHOSTS} ghost ships to positions.json")

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
        print("⏲️ Sleeping 15 minutes...")
        time.sleep(900)


