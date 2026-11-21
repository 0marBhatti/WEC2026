import socket
import json
import codecs

HOST = "localhost"
PORT = 8800
RECV_SIZE = 4096

SOLAR_CAP = 200
BATTERY_CAP = 100
GEN_COST = 1.00
HOURS = 24
FINAL_HOUR = HOURS - 1

battery = 0
hour = 0


def to_number(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def read_events(data):
    raw = data.get("random_event") or "none"
    if isinstance(raw, str):
        raw = [raw]
    return {str(e).strip().lower() for e in raw}


def is_lecture_hall(entry):
    name = str(entry.get("type", "")).strip().lower()
    return name.replace(" ", "_").replace("-", "_") == "lecture_hall"


def build_response(buildings, gen):
    return {
        "buildings": buildings,
        "solar": sum(b["solar"] for b in buildings),
        "battery": sum(b["battery"] for b in buildings),
        "generator": gen,
    }


def can_discharge(price, has_bat, has_grid, has_gen):
    if not has_bat:
        return False
    if not has_grid:
        return True
    if hour == FINAL_HOUR:
        return True
    if not has_gen:
        return False
    return price > GEN_COST


def solve(data):
    global battery, hour

    events = read_events(data)
    loads = data["loads"]
    price = float(data.get("grid_price", 0))

    has_solar = "cloudy_weather" not in events
    has_grid = "grid_failure" not in events
    has_bat = "battery_failure" not in events
    has_gen = "generator_failure" not in events

    solar_left = SOLAR_CAP if has_solar else 0
    bat_left = battery if can_discharge(price, has_bat, has_grid, has_gen) else 0
    discharged = 0
    buildings = []

    for entry in loads:
        load = to_number(entry.get("load", 0))

        solar = 0
        if not is_lecture_hall(entry):
            solar = min(load, solar_left)
            solar_left -= solar

        remaining = load - solar
        bat = min(remaining, bat_left)
        bat_left -= bat
        discharged += bat

        grid = remaining - bat if has_grid else 0

        buildings.append({"solar": solar, "battery": bat, "grid": grid})

    battery -= discharged

    gen = 0
    if has_gen and has_bat and hour < FINAL_HOUR:
        gen = BATTERY_CAP - battery
    battery += gen

    hour += 1
    return build_response(buildings, gen)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    decoder = json.JSONDecoder()
    utf8 = codecs.getincrementaldecoder("utf-8")()
    buf = ""
    try:
        while True:
            chunk = sock.recv(RECV_SIZE)
            if not chunk:
                return
            buf += utf8.decode(chunk)

            while True:
                buf = buf.lstrip()
                if not buf:
                    break
                try:
                    data, end = decoder.raw_decode(buf)
                except json.JSONDecodeError:
                    break
                buf = buf[end:]

                if isinstance(data, dict) and "loads" in data:
                    response = solve(data)
                    sock.sendall((json.dumps(response) + "\n").encode())
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()