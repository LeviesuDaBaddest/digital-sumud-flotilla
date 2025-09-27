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
NUM_GHOSTS = 4  # 3 boats total including the real ship
UPDATE_INTERVAL = 300  # seconds
SPEED_VARIATION = 0.08  # ±8% variation
POSITIONS_FILE = "fleet_positions.json"
REAL_SHIP_ID = "al_awda"

# ----------------------
# CUSTOM GHOST NAMES
# ----------------------
GHOST_NAMES = [
    "Ma’an", "Navaren", "Al Quds", "Ramallah"  
]

# ----------------------
# GLOBAL STATE
# ----------------------
GHOST_STATES = {}

# ----------------------
# HELPER FUNCTIONS
# ----------------------
def read_position():
    """Read real ship position from Sailaway NMEA and return lat, lon, SOG, HDG."""
    try:
        print("🔌 Connecting to Sailaway NMEA on localhost:10111...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", 10111))
        s.settimeout(10)
        print("✅ Connected! Listening for NMEA...")

        true_heading = None
        while True:
            raw = s.recv(1024).decode(errors="ignore")
            for line in raw.splitlines():
                print("NMEA:", line)  # 👀 debug every sentence

                # --- True heading from HDT (preferred) ---
                if line.startswith("$HDT"):
                    try:
                        parts = line.split(",")
                        if len(parts) > 1 and parts[1]:
                            true_heading = float(parts[1])
                            print(f"🧭 True Heading (HDT): {true_heading}")
                    except:
                        pass

                # --- Magnetic/true heading from HDG (fallback) ---
                elif line.startswith("$HDG"):
                    try:
                        parts = line.split(",")
                        if len(parts) > 1 and parts[1]:
                            true_heading = float(parts[1])
                            print(f"🧭 Heading (HDG): {true_heading}")
                    except:
                        pass

                # --- Position, speed, and COG from GPRMC ---
                elif line.startswith("$GPRMC"):
                    parts = line.split(",")
                    if len(parts) < 9:
                        continue
                    lat_raw, lat_dir = parts[3], parts[4]
                    lon_raw, lon_dir = parts[5], parts[6]
                    if not lat_raw or not lon_raw:
                        continue

                    # Parse lat/lon
                    lat = float(lat_raw[:2]) + float(lat_raw[2:]) / 60.0
                    lon = float(lon_raw[:3]) + float(lon_raw[3:]) / 60.0
                    if lat_dir.upper() == "S": lat = -lat
                    if lon_dir.upper() == "W": lon = -lon

                    # Speed and course over ground
                    sog = float(parts[7]) if parts[7] else 0.0
                    cog = float(parts[8]) if parts[8] else 0.0

                    # Pick heading: prefer HDT/HDG, else use COG
                    hdg = true_heading if true_heading is not None else cog
                    print(f"📍 Position: {lat:.6f}, {lon:.6f} | SOG={sog:.2f} kn | HDG={hdg:.1f}")

                    return lat, lon, sog, hdg

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

def compute_heading(lat1, lon1, lat2, lon2):
    """Compute compass heading from point1 to point2 in degrees."""
    dLon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dLon) * math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dLon)
    heading = math.degrees(math.atan2(x, y))
    return (heading + 360) % 360

# ----------------------
# GHOST MOVEMENT FOLLOWING REAL SHIP (more natural)
# ----------------------
def move_ghost(real_lat, real_lon, sog, hdg, ghost_id, fleet):
    if ghost_id not in GHOST_STATES:
        # assign each ghost a stable formation bearing & distance (in nm)
        rel_bearing = random.uniform(0, 360)   # degrees relative to ship
        rel_distance = random.uniform(0.2, 0.8)  # between 0.2–0.8 nm
        speed_bias = 1 + random.uniform(-SPEED_VARIATION, SPEED_VARIATION)
        GHOST_STATES[ghost_id] = {
            "rel_bearing": rel_bearing,
            "rel_distance": rel_distance,
            "speed_bias": speed_bias,
            "heading_jitter": random.uniform(-5, 5)  # +/-5° wander
        }

    state = GHOST_STATES[ghost_id]

    # gradually drift speed bias (small random walk)
    state["speed_bias"] += random.uniform(-0.01, 0.01)
    state["speed_bias"] = max(0.9, min(1.1, state["speed_bias"]))  # clamp 90–110%

    # gradually drift heading jitter
    state["heading_jitter"] += random.uniform(-0.5, 0.5)
    state["heading_jitter"] = max(-15, min(15, state["heading_jitter"]))  # clamp

    # ghost speed
    ghost_speed = sog * state["speed_bias"]

    # distance moved in this interval (nm → degrees lat/lon)
    dist_deg = ghost_speed * (UPDATE_INTERVAL / 3600) / 60  

    # base movement direction = real ship heading + ghost’s jitter
    move_heading = hdg + state["heading_jitter"]
    rad = math.radians(move_heading)

    delta_lat = dist_deg * math.cos(rad)
    delta_lon = dist_deg * math.sin(rad) / max(0.1, math.cos(math.radians(real_lat)))

    # base ghost position relative to real ship
    rel_rad = math.radians(hdg + state["rel_bearing"])
    rel_lat = state["rel_distance"] * math.cos(rel_rad) / 60.0  # nm→deg
    rel_lon = state["rel_distance"] * math.sin(rel_rad) / (60.0 * math.cos(math.radians(real_lat)))

    new_lat = real_lat + rel_lat + delta_lat
    new_lon = real_lon + rel_lon + delta_lon

    ghost_hdg = (hdg + state["heading_jitter"]) % 360

    return new_lat, new_lon, ghost_speed, ghost_hdg

# ----------------------
# GENERATE / UPDATE GHOSTS
# ----------------------
def generate_or_update_ghosts(real_lat, real_lon, sog, hdg, fleet):
    for i in range(1, NUM_GHOSTS+1):
        ghost_id = f"ghost_{i}"
        ghost_name = GHOST_NAMES[(i-1) % len(GHOST_NAMES)]
        if ghost_id not in fleet: fleet[ghost_id] = []

        new_lat, new_lon, ghost_speed, ghost_hdg = move_ghost(real_lat, real_lon, sog, hdg, ghost_id, fleet)
        fleet[ghost_id].append({
            "lat": new_lat,
            "lon": new_lon,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ghost": True,
            "name": ghost_name,
            "speed": round(ghost_speed,2),
            "heading": round(ghost_hdg,1)
        })
    return fleet

# ----------------------
# APPEND POSITIONS
# ----------------------
def append_positions(real_lat, real_lon, sog, hdg):
    fleet = load_positions()

    fleet.setdefault(REAL_SHIP_ID, []).append({
        "lat": real_lat,
        "lon": real_lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ghost": False,
        "name": "Al Awda",
        "speed": round(sog,2),
        "heading": round(hdg,1)
    })

    fleet = generate_or_update_ghosts(real_lat, real_lon, sog, hdg, fleet)
    save_positions(fleet)
    print(f"📌 Appended real ship + {NUM_GHOSTS} ghost ships.")

# ----------------------
# GIT PUSH
# ----------------------
def push_to_git():
    subprocess.run(["git","add","-A"])
    result = subprocess.run(["git","commit","-m","🛰️ Auto-update with heartbeat"])
    if result.returncode != 0: print("⚠️ Nothing to commit")
    subprocess.run(["git","push"])
    print("📤 Pushed to GitHub.")

# ----------------------
# MAIN LOOP
# ----------------------
if __name__ == "__main__":
    print("🚀 Starting Digital Sumud Flotilla Tracker...")
    while True:
        lat, lon, sog, hdg = read_position()
        if lat and lon:
            append_positions(lat, lon, sog, hdg)
            push_to_git()
        print(f"⏲️ Sleeping {UPDATE_INTERVAL} seconds...")
        time.sleep(UPDATE_INTERVAL)



