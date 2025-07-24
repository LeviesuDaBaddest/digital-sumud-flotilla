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
                print("🔍 GPRMC Parts:", parts)  # <--- NEW
                try:
                    if len(parts) > 6 and parts[3] and parts[5]:
                        lat = float(parts[3][:2]) + float(parts[3][2:]) / 60.0
                        if parts[4] == "S":
                            lat = -lat
                        lon = float(parts[5][:3]) + float(parts[5][3:]) / 60.0
                        if parts[6] == "W":
                            lon = -lon
                        print(f"✅ Got position: {lat}, {lon}")
                        return lat, lon
                    else:
                        print("⚠️ Missing lat/lon in GPRMC")
                except Exception as parse_error:
                    print("❌ Error parsing GPRMC:", parse_error)
    except Exception as e:
        print("❌ NMEA read error:", e)
        return None, None
