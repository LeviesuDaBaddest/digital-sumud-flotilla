import socket
import json
import time
import subprocess
import os

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
                    print(f"🔍 Raw parts: {parts}")
                    if len(parts) < 7:
                        print("⚠️ Incomplete GPRMC line.")
                        continue
                    try:
                        lat_raw = parts[3]
                        lat_dir = parts[4]
                        lon_raw = parts[5]
                        lon_dir = parts[6]
                        if not lat_raw or not lon_raw:
                            print("⚠️ Missing lat/lon in GPRMC.")
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

def append_position(lat, lon):
    data = {
        "lat": lat,
        "lon": lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated": True
    }
    if os.path.exists("positions.json"):
        with open("positions.json", "r") as f:
            try:
                trail = json.load(f)
                for point in trail:
                    point["updated"] = False  # clear previous flags
            except:
                print("⚠️ Could not read positions.json — starting fresh.")
                trail = []
    else:
        trail = []
    trail.append(data)
    with open("positions.json", "w") as f:
        json.dump(trail, f, indent=2)
    print("📌 Appended new position:", data)

def push_to_git():
    subprocess.run(["git", "add", "-A"])
    result = subprocess.run(["git", "commit", "-m", "🛰️ Auto-update with heartbeat"], shell=True)
    if result.returncode != 0:
        print("⚠️ Nothing to commit (no change in file?)")
    subprocess.run(["git", "push"], shell=True)
    print("📤 Pushed to GitHub.")
