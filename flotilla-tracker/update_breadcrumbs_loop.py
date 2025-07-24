import socket
import json
import time
import subprocess
import os

def read_position():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", 10111))
        s.settimeout(10)
        while True:
            line = s.recv(1024).decode(errors="ignore")
            print("📡 Got NMEA line:", line.strip())  # DEBUG LINE 👈
            if line.startswith("$GPRMC"):
                parts = line.strip().split(",")
                if parts[3] and parts[5]:
                    lat = float(parts[3][:2]) + float(parts[3][2:]) / 60.0
                    if parts[4] == "S":
                        lat = -lat
                    lon = float(parts[5][:3]) + float(parts[5][3:]) / 60.0
                    if parts[6] == "W":
                        lon = -lon
                    return lat, lon
    except Exception as e:
        print("❌ NMEA read error:", e)
        return None, None

def append_position(lat, lon):
    data = {"lat": lat, "lon": lon, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    if os.path.exists("positions.json"):
        with open("positions.json", "r") as f:
            trail = json.load(f)
    else:
        trail = []
    trail.append(data)
    with open("positions.json", "w") as f:
        json.dump(trail, f, indent=2)
    print("📌 Appended:", data)

def push_to_git():
    subprocess.run(["git", "add", "positions.json"])
    subprocess.run(["git", "commit", "-m", "trail update"], shell=True)
    subprocess.run(["git", "push"], shell=True)

if __name__ == "__main__":
    while True:
        print("⏳ Waiting for NMEA data from Sailaway...")
        lat, lon = read_position()
        if lat and lon:
            print(f"✅ Got position: {lat}, {lon}")
            append_position(lat, lon)
            push_to_git()
            print("📤 Pushed to GitHub. Waiting 15 minutes...")
        else:
            print("⚠️ No GPS fix. Retrying in 15 minutes...")
        time.sleep(900)

