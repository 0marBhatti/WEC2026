import socket
import json

HOST = "localhost"
PORT = 8800
RECV_SIZE = 4096 # socket read size in bytes

SOLAR_CAP = 200 # max solar units per hour
BATTERY_CAP = 100 # max battery charge
GEN_COST = 1.00 # generator cost per unit
FINAL_HOUR = 24 # last hour: use all battery, no charging

battery = 0
hour = 0


def solve(data):
    global battery, hour

    event = data.get("random_event", "none")
    loads = data["loads"]
    grid_price = data["grid_price"]

    has_solar = (event != "cloudy_weather")
    has_grid = (event != "grid_failure")
    has_bat = (event != "battery_failure")
    has_gen = (event != "generator_failure")

    final_hour = hour >= FINAL_HOUR

    if final_hour:
        threshold = 0
        reserve = 0
    else:
        threshold = GEN_COST
        reserve = 0 if has_gen else BATTERY_CAP

    solar_left = SOLAR_CAP if has_solar else 0
    discharged = 0
    buildings = []

    for entry in loads:
        load = entry["load"]

        solar = 0
        if entry["type"] != "lecture_hall":
            solar = min(load, solar_left)
            solar_left -= solar

        remaining = load - solar
        available = (battery - discharged) if has_bat else 0

        if not has_grid:
            b_use = min(remaining, available)
        elif grid_price > threshold:
            b_use = min(remaining, max(0, available - reserve))
        else:
            b_use = 0

        discharged += b_use
        buildings.append({
            "solar": solar,
            "battery": b_use,
            "grid": remaining - b_use,
        })

    post_level = battery - discharged
    gen = 0
    if has_gen and has_bat and not final_hour:
        gen = BATTERY_CAP - post_level

    battery = post_level + gen
    hour += 1
    return {"buildings": buildings, "generator": gen}


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    while True:
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(RECV_SIZE)
            if not chunk:
                break
            buf += chunk
        if not buf:
            break

        data = json.loads(buf.split(b"\n")[0])
        response = solve(data)
        sock.sendall((json.dumps(response) + "\n").encode())

    sock.close()


if __name__ == "__main__":
    main()
