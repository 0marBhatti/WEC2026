import socket
import json
import codecs

HOST = "localhost"
PORT = 8800
RECV_SIZE = 4096

SOLAR_CAP = 200
BATTERY_CAP = 100
GEN_COST = 1.00

PEAK_START = 9
PEAK_END = 17
PRE_PEAK_HOURS = 4
HOURS = 24
FINAL_HOUR = HOURS - 1

EMA_ALPHA = 0.3

PRICE_HIGH = 1.5
PRICE_VERY_HIGH = 2.0
PRICE_CHEAP = 0.5

PEAK_RESERVE = 5
PRE_PEAK_RESERVE = 20
PRE_PEAK_RESERVE_CLOUDY = 30
BASE_RESERVE = 15
BASE_RESERVE_CLOUDY = 25
RESERVE_DROP = 10
PEAK_DISCHARGE_PRICE = 0.8

SAFETY_LEVEL = 10
CLOUDY_TARGET = 80
TREND_TARGET = 70
EARLY_HOURS = 3
EARLY_TARGET = 20

battery = 0
avg_grid_price = None
hour = 0


def solve(data):
    global battery, hour, avg_grid_price

    event = data.get("random_event", "none")
    forecast = data.get("forecast", "not cloudy")
    loads = data["loads"]
    grid_price = data["grid_price"]
    if avg_grid_price is None:
        avg_grid_price = grid_price
    else:
        avg_grid_price = EMA_ALPHA * grid_price + (1 - EMA_ALPHA) * avg_grid_price

    has_solar = (event != "cloudy_weather")
    has_grid = (event != "grid_failure")
    has_bat = (event != "battery_failure")
    has_gen = (event != "generator_failure")

    final_hour = hour == FINAL_HOUR
    peak = PEAK_START <= hour < PEAK_END
    pre_peak = PEAK_START - PRE_PEAK_HOURS <= hour < PEAK_START
    cloudy = (forecast == "cloudy")

    if final_hour:
        reserve = 0
        threshold = 0
    else:
        threshold = PEAK_DISCHARGE_PRICE if peak else GEN_COST
        if peak:
            reserve = 0 if grid_price >= PRICE_HIGH else PEAK_RESERVE
        elif pre_peak:
            reserve = PRE_PEAK_RESERVE_CLOUDY if cloudy else PRE_PEAK_RESERVE
        else:
            base = BASE_RESERVE_CLOUDY if cloudy else BASE_RESERVE
            if grid_price >= PRICE_VERY_HIGH:
                reserve = 0
            elif grid_price >= PRICE_HIGH:
                reserve = base - RESERVE_DROP
            else:
                reserve = base

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
            "grid": remaining - b_use if has_grid else 0,
        })

    post_level = battery - discharged
    room = BATTERY_CAP - post_level
    gen = 0

    if has_gen and has_bat and not final_hour:
        if post_level < SAFETY_LEVEL:
            gen = min(SAFETY_LEVEL - post_level, room)

        if pre_peak:
            gen = room

        if not (peak and post_level >= SAFETY_LEVEL):
            if cloudy and post_level < CLOUDY_TARGET:
                gen = max(gen, min(CLOUDY_TARGET - post_level, room))

            if avg_grid_price > GEN_COST and post_level < TREND_TARGET:
                gen = max(gen, min(TREND_TARGET - post_level, room))

            if hour < EARLY_HOURS and post_level < EARLY_TARGET:
                gen = max(gen, min(EARLY_TARGET - post_level, room))

            if (grid_price < PRICE_CHEAP and not pre_peak and not cloudy
                    and post_level >= SAFETY_LEVEL):
                gen = 0

    battery = post_level + gen
    hour += 1
    return {"buildings": buildings, "generator": gen}


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
