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
            line = s.recv(1024).decode(errors="ignore")
            print("📡 Got NMEA line:", line.strip())
            if line.startswith("$GPRMC"):
                parts = line.strip().split(",")
                if parts[3] and parts[5]:
                    lat = float(parts[3][:2]) + float(parts[3][2:]) / 60.0
                    if parts[4] == "S":
                        lat = -lat
                    lon = float(parts[5][:3]) + float(parts[5][3:]) / 60.0
                    if parts[6] == "W":
                        lon = -lon
                    print(f"✅ Got position: {lat}, {lon}")
                    return lat, lon
    except Exception as e:
        print("❌ NMEA read error:", e)
        return None, None

def append_position(lat, lon):
    data = {
        "lat": lat,
        "lon": lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "heartbeat": str(time.time())  # 👈 Forces JSON to change every run
    }
    with open("position.json", "w") as f:
        json.dump(data, f, indent=2)
    print("📌 Wrote forced-update position:", data)

def push_to_git():
    subprocess.run(["git", "add", "-A"])
    subprocess.run(["git", "commit", "-m", "🛰️ Auto-update with heartbeat"], shell=True)
    subprocess.run(["git", "push"], shell=True)
    print("📤 Pushed to GitHub.")

if __name__ == "__main__":
    while True:
        lat, lon = read_position()
        if lat and lon:
            append_position(lat, lon)
            push_to_git()
        else:
            print("⚠️ No GPS fix. Will try again.")
        print("⏱️ Waiting 15 minutes before next update...")
        time.sleep(900)
