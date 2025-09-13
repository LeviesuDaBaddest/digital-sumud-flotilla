import socket
import json
import time
import subprocess
import os
import random

# ----------------------
# CONFIG
# ----------------------
GHOST_FLEET_SIZE = 15
GHOST_SPREAD = 0.02  # max offset in degrees for ghosts

# ----------------------
# Functions
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

def append_positions(lat, lon):
    """Append real position + ghost fleet"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    # Load existing trail
    if os.path.exists("positions.json"):
        with open("positions.json", "r") as f:
            try:
                trail = json.load(f)
                for point in trail:
                    point["updated"] = False
            except:
                trail = []
    else:
        trail = []

    # Real ship
    trail.append({
        "lat": lat,
        "lon": lon,
        "timestamp": timestamp,
        "updated": True,
        "type": "real"
    })

    # Ghost ships
    for i in range(GHOST_FLEET_SIZE):
        offset_lat = (random.random() - 0.5) * GHOST_SPREAD
        offset_lon = (random.random() - 0.5) * GHOST_SPREAD
        trail.append({
            "lat": lat + offset_lat,
            "lon": lon + offset_lon,
            "timestamp": timestamp,
            "updated": True,
            "type": f"ghost{i+1}"
        })

    with open("positions.json", "w") as f:
        json.dump(trail, f, indent=2)

    print(f"📌 Appended real + {GHOST_FLEET_SIZE} ghost positions at {timestamp}")

def push_to_git():
    subprocess.run(["git", "add", "-A"])
    result = subprocess.run(["git", "commit", "-m", "🛰️ Auto-update with heartbeat"])
    if result.returncode != 0:
        print("⚠️ Nothing to commit")
    subprocess.run(["git", "push"])
    print("📤 Pushed to GitHub.")

# ----------------------
# Main loop
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

