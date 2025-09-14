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
REAL_SHIP_ID = "al_awda"

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
            return {}
    return {}

def save_positions(fleet):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(fleet, f, indent=2)

def generate_ghosts(real_lat, real_lon, existing_fleet):
    ghosts = {}
    for i in range(1, NUM_GHOSTS + 1):
        ghost_id = f"ghost_{i}"
        offset_lat = (random.random() - 0.5) * GHOST_OFFSET_MAX
        offset_lon = (random.random() - 0.5) * GHOST_OFFSET_MAX
        ghost_point = {
            "lat": real_lat + offset_lat,
            "lon": real_lon + offset_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True
        }
        if ghost_id not in existing_fleet:
            existing_fleet[ghost_id] = []
        existing_fleet[ghost_id].append(ghost_point)
    return existing_fleet

def append_positions(real_lat, real_lon):
    fleet = load_positions()

    # Add real ship
    real_point = {
        "lat": real_lat,
        "lon": real_lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ghost": False
    }
    if REAL_SHIP_ID not in fleet:
        fleet[REAL_SHIP_ID] = []
    fleet[REAL_SHIP_ID].append(real_point)

    # Add ghosts
    fleet = generate_ghosts(real_lat, real_lon, fleet)

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

