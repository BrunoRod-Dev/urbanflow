"""Export this intersection to the local UrbanFlow web replay."""

import argparse
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET


SCENARIO_DIR = Path(__file__).resolve().parent
OUTPUT = SCENARIO_DIR.parent / "urbanflow-web" / "scenario.js"
APPROACHES = {"N": "Norte", "E": "Este", "S": "Sur", "W": "Oeste"}


def read_scenario():
    network = ET.parse(SCENARIO_DIR / "intersection.net.xml")
    demand = ET.parse(SCENARIO_DIR / "intersection.rou.xml")
    signal = network.find("tlLogic[@id='C']")
    junction = network.find("junction[@id='C']")
    center = float(junction.get("x")), float(junction.get("y"))
    links = {
        (link.get("from"), link.get("to")): int(link.get("linkIndex"))
        for link in network.findall("connection[@tl='C']")
    }
    lanes = {}
    for edge in network.findall("edge[@from]"):
        lane = edge.find("lane")
        lanes[edge.get("id")] = [
            tuple(map(float, point.split(","))) for point in lane.get("shape").split()
        ]

    route_edges = {route.get("id"): route.get("edges").split() for route in demand.findall("route")}
    flows = []
    for flow in demand.findall("flow"):
        incoming, outgoing = route_edges[flow.get("route")]
        flows.append({
            "in": incoming,
            "out": outgoing,
            "approach": incoming[0],
            "rate": float(flow.get("vehsPerHour")),
            "begin": float(flow.get("begin")),
            "end": float(flow.get("end")),
            "link": links[incoming, outgoing],
        })

    phases = [
        {"duration": float(phase.get("duration")), "signals": {
            flow["approach"]: phase.get("state")[flow["link"]].lower() for flow in flows
        }}
        for phase in signal.findall("phase")
    ]
    return {
        "center": center,
        "lanes": lanes,
        "approaches": APPROACHES,
        "incoming": {flow["in"]: flow["approach"] for flow in flows},
        "phases": phases,
        "offset": float(signal.get("offset", 0)),
        "demand": sum(flow["rate"] for flow in flows),
    }, flows


def signals_at(scenario, time):
    phases = scenario["phases"]
    cycle = sum(phase["duration"] for phase in phases)
    remaining = (time + scenario["offset"]) % cycle
    for phase in phases:
        if remaining < phase["duration"]:
            return phase["signals"]
        remaining -= phase["duration"]


def sample_frames(scenario, flows, duration):
    """Create a labeled preview when SUMO is unavailable. Supports the demo's straight routes."""
    cars = [[] for _ in flows]
    next_arrivals = [flow["begin"] for flow in flows]
    route_geometry = []
    for flow in flows:
        start = scenario["lanes"][flow["in"]][0]
        stop = scenario["lanes"][flow["in"]][-1]
        end = scenario["lanes"][flow["out"]][-1]
        length = math.dist(start, end)
        dx, dy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
        angle = round(math.degrees(math.atan2(dx, dy)) % 360)
        route_geometry.append((start, math.dist(start, stop), length, dx, dy, angle))

    frames = []
    next_id = 0
    for step in range(duration * 4 + 1):
        time = step / 4
        signals = signals_at(scenario, time)
        visible = []
        for index, flow in enumerate(flows):
            start, stop, length, dx, dy, angle = route_geometry[index]
            lane_cars = cars[index]
            if (flow["rate"] > 0 and next_arrivals[index] <= time < flow["end"]
                    and (not lane_cars or lane_cars[-1][1] >= 10)):
                lane_cars.append([next_id, 0.0, 9.0 + (next_id % 4) * 0.6])
                next_arrivals[index] += 3600 / flow["rate"]
                next_id += 1

            leader_position = math.inf
            for car in lane_cars:
                car_id, position, speed = car
                limit = leader_position - 8.0
                if position <= stop and signals[flow["approach"]] != "g":
                    limit = min(limit, stop)
                free_distance = max(0, limit - position)
                target_speed = min(12.8, math.sqrt(2 * 2.6 * free_distance))
                speed = min(speed + 1.5 / 4, target_speed)
                distance = min(speed / 4, free_distance)
                position += distance
                car[1:] = position, distance * 4
                leader_position = position
                if step % 4 == 0 and position < length:
                    visible.append([
                        car_id, round(start[0] + position * dx, 2), round(start[1] + position * dy, 2),
                        angle, round(distance * 4, 2), flow["approach"] if position <= stop else "",
                    ])
            cars[index] = [car for car in lane_cars if car[1] < length]
        if step % 4 == 0:
            frames.append([int(time), visible])
    return frames


def fcd_frames(path, scenario, *, geographic=False, vehicle_lengths=None, vehicle_index=None):
    ids = {}
    frames = []
    root = None
    for event, element in ET.iterparse(path, events=("start", "end")):
        if root is None:
            root = element
        if event != "end" or element.tag != "timestep":
            continue
        cars = []
        for car in element.findall("vehicle"):
            sumo_id = car.get("id")
            kind = car.get("type")
            identifier = ids.setdefault(sumo_id, len(ids))
            if vehicle_index is not None and identifier == len(vehicle_index):
                vehicle_index.append({"sumoId": sumo_id, "type": kind})
            angle = float(car.get("angle"))
            radians = math.radians(angle)
            x, y = float(car.get("x")), float(car.get("y"))
            precision = 7 if geographic else 2
            if not geographic:
                # Cartesian schematic uses the center of the 5 m car.
                x -= 2.5 * math.sin(radians)
                y -= 2.5 * math.cos(radians)
            edge = car.get("lane", "").rsplit("_", 1)[0]
            sample = [
                identifier, round(x, precision), round(y, precision), angle, float(car.get("speed")),
                scenario["incoming"].get(edge, ""),
            ]
            if vehicle_lengths is not None:
                sample.extend((car.get("lane"), float(car.get("pos")), vehicle_lengths[kind]))
            cars.append(sample)
        frames.append([float(element.get("time")), cars])
        root.remove(element)
    if len(frames) < 2:
        raise ValueError("La salida FCD necesita al menos dos instantes de simulación.")
    return frames


def locate_sumo(name="sumo"):
    executable = shutil.which(name)
    if executable:
        return executable
    sumo_home = os.getenv("SUMO_HOME")
    if sumo_home:
        candidate = Path(sumo_home) / "bin" / (f"{name}.exe" if os.name == "nt" else name)
        if candidate.is_file():
            return str(candidate)
    return None


def write_replay(destination, variable, metadata, frames, script):
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))
    with destination.open("w", encoding="utf-8", newline="\n") as file:
        file.write(f'// Generated by {script}.\nwindow.{variable} = {encoder.encode(metadata)[:-1]},"frames":[\n')
        file.write(",\n".join(map(encoder.encode, frames)))
        file.write("\n]};\n")
    print(f"{len(frames)} instantes exportados a {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Generar tráfico ilustrativo sin ejecutar SUMO.")
    mode.add_argument("--fcd", type=Path, help="Importar un FCD XML de este mismo escenario.")
    parser.add_argument("--seconds", type=int, default=360, help="Duración para una corrida nueva.")
    args = parser.parse_args()
    if args.seconds < 2:
        parser.error("--seconds debe ser mayor o igual a 2")
    scenario, flows = read_scenario()
    if args.demo:
        frames = sample_frames(scenario, flows, args.seconds)
    elif args.fcd:
        frames = fcd_frames(args.fcd, scenario)
    else:
        executable = locate_sumo()
        if not executable:
            parser.error("SUMO no está disponible. Agregá sumo al PATH o configurá SUMO_HOME.")
        with TemporaryDirectory(prefix="urbanflow-") as temp_dir:
            output = Path(temp_dir) / "trajectory.xml"
            subprocess.run([
                executable, "-c", str(SCENARIO_DIR / "intersection.sumocfg"),
                "--end", str(args.seconds), "--fcd-output", str(output), "--no-step-log", "true",
            ], check=True, cwd=SCENARIO_DIR)
            frames = fcd_frames(output, scenario)
    metadata = {key: value for key, value in scenario.items() if key not in {"lanes", "incoming"}}
    metadata["source"] = "demo" if args.demo else "sumo"
    write_replay(OUTPUT, "urbanflowScenario", metadata, frames, "sumo_scenario/export_web.py")


if __name__ == "__main__":
    main()
