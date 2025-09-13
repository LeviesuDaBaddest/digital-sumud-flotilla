import socket
import json
import time
import subprocess
import os
import random

# ----------------------
# CONFIG
# ----------------------
NUM_GHOSTS = 15
GHOST_OFFSET_MAX = 0.02  # Max lat/lon offset from real ship
POSITIONS_FILE = "positions.json"

# ----------------------
# Helper functions
# ----------------------
def read_position():
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
                print("📡 Got NMEA line:", line)
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
            return []
    return []

def save_positions(trail):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(trail, f, indent=2)

def generate_ghosts(real_lat, real_lon):
    ghosts = []
    for i in range(NUM_GHOSTS):
        offset_lat = (random.random() - 0.5) * GHOST_OFFSET_MAX
        offset_lon = (random.random() - 0.5) * GHOST_OFFSET_MAX
        ghost = {
            "lat": real_lat + offset_lat,
            "lon": real_lon + offset_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated": True,
            "ghost": True
        }
        ghosts.append(ghost)
    return ghosts

def append_positions(real_lat, real_lon):
    trail = load_positions()
    # Mark previous points as not updated
    for point in trail:
        point["updated"] = False

    # Add real ship
    real_ship = {
        "lat": real_lat,
        "lon": real_lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated": True,
        "ghost": False
    }
    trail.append(real_ship)

    # Add ghosts
    ghosts = generate_ghosts(real_lat, real_lon)
    trail.extend(ghosts)

    save_positions(trail)
    print(f"📌 Appended real ship + {len(ghosts)} ghost ships to positions.json")

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

