import socket
import json

HOST = "localhost"
PORT = 8800
RECV_SIZE = 4096

SOLAR_CAP = 200
BATTERY_CAP = 100
GEN_COST = 1.00
FINAL_HOUR = 23  # sim runs hours 0..23

# server never reports the battery level so we have to track it ourselves
battery = 0
hour = 0


def can_discharge(price, has_bat, has_grid, has_gen):
    if not has_bat:
        return False
    if not has_grid:
        return True  # grid is down, battery is all we've got
    if hour == FINAL_HOUR:
        return True  # nothing after this hour, leftover charge is wasted
    if not has_gen:
        return False  # can't refill this hour, so keep the full 100 for next hour
    # anything we use gets refilled at $1/unit, only worth it if grid costs more
    return price > GEN_COST


def solve(data):
    global battery, hour

    event = data.get("random_event", "none")
    loads = data["loads"]
    price = data["grid_price"]

    has_solar = event != "cloudy_weather"
    has_grid = event != "grid_failure"
    has_bat = event != "battery_failure"
    has_gen = event != "generator_failure"

    solar_left = SOLAR_CAP if has_solar else 0
    bat_left = battery if can_discharge(price, has_bat, has_grid, has_gen) else 0
    discharged = 0
    buildings = []

    for entry in loads:
        load = entry["load"]

        # solar first since it's free. lecture hall has no panels
        solar = 0
        if entry["type"] != "lecture_hall":
            solar = min(load, solar_left)
            solar_left -= solar

        remaining = load - solar
        bat = min(remaining, bat_left)
        bat_left -= bat
        discharged += bat

        # on grid_failure a full battery should cover this, so grid stays 0
        grid = remaining - bat if has_grid else 0

        buildings.append({"solar": solar, "battery": bat, "grid": grid})

    battery -= discharged

    # always top back up to 100 so a grid failure next hour can't hurt us.
    # skip on the last hour, there's no next hour to use it in
    gen = 0
    if has_gen and has_bat and hour < FINAL_HOUR:
        gen = BATTERY_CAP - battery
    battery += gen

    hour += 1
    return {"buildings": buildings, "generator": gen}


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    # keep leftover bytes between reads in case two messages come in one chunk
    buf = b""
    try:
        while True:
            while b"\n" not in buf:
                chunk = sock.recv(RECV_SIZE)
                if not chunk:
                    return  # server closed, sim is over
                buf += chunk

            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue

            data = json.loads(line)
            if "loads" not in data:
                continue  # not an hourly message (e.g. a final summary), nothing to answer

            response = solve(data)
            sock.sendall((json.dumps(response) + "\n").encode())
    except (ConnectionResetError, BrokenPipeError):
        pass  # server hung up on us after the last hour
    finally:
        sock.close()


if __name__ == "__main__":
    main()