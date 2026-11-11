"""Rebuild and run the curated Roosevelt–Camacho roundabout in SUMO."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from export_web import SCENARIO_DIR, fcd_frames, locate_sumo, write_replay


PILOT_DIR = SCENARIO_DIR / "pilot"
SCENARIO = "roosevelt-camacho"
OUTPUT = SCENARIO_DIR.parent / "urbanflow-web" / "pilot.js"
INCOMING = {
    "181384674": "roosevelt-noroeste",
    "553842606": "roosevelt-sureste",
    "-178119926": "camacho-sur",
    "121506103": "camacho-sur",
}
APPROACHES = {
    "roosevelt-noroeste": "Roosevelt NO",
    "roosevelt-sureste": "Roosevelt SE",
    "camacho-sur": "Camacho Sur",
}


def shape(value):
    return [tuple(map(float, point.split(","))) for point in value.split()]


def pilot_metadata():
    network = ET.parse(PILOT_DIR / f"{SCENARIO}.net.xml")
    roundabout = network.find("roundabout")
    ring_nodes = [network.find(f"junction[@id='{node}']") for node in roundabout.get("nodes").split()]
    center = [sum(float(node.get(axis)) for node in ring_nodes) / len(ring_nodes) for axis in ("x", "y")]
    min_x, min_y, max_x, max_y = map(float, network.find("location").get("convBoundary").split(","))
    lanes = [
        [float(lane.get("width", 3.2)), shape(lane.get("shape"))]
        for edge in network.findall("edge[@from]") for lane in edge.findall("lane")
    ]
    junctions = [
        shape(junction.get("shape")) for junction in network.findall("junction")
        if junction.get("type") not in {"dead_end", "internal"}
    ]
    labels = []
    for edge_id, index, name, dx, dy in [
        ("181384674", 2, "Av. Roosevelt", -12, 19),
        ("553842606", 2, "Av. Roosevelt", 15, -18),
        ("815625574", -1, "Av. Camacho", 12, 4),
        ("178119926", -1, "Av. Camacho", 12, -16),
    ]:
        lane = network.find(f"edge[@id='{edge_id}']/lane")
        x, y = shape(lane.get("shape"))[index]
        labels.append([name, round(x + dx, 2), round(y + dy, 2)])

    flows = ET.parse(PILOT_DIR / f"{SCENARIO}.rou.xml").findall("flow")
    return {
        "title": "Rotonda de Roosevelt y Camacho",
        "location": {"lat": -34.915903, "lng": -54.959541},
        "center": [round(value, 2) for value in center],
        "geometry": {"bounds": [min_x, min_y, max_x, max_y], "lanes": lanes, "junctions": junctions, "labels": labels},
        "approaches": APPROACHES,
        "demand": sum(float(flow.get("vehsPerHour")) for flow in flows),
        "source": "sumo",
    }


def main():
    sumo = locate_sumo()
    netconvert = locate_sumo("netconvert")
    if not sumo or not netconvert:
        raise SystemExit("Agregá sumo y netconvert al PATH o configurá SUMO_HOME.")
    subprocess.run([
        netconvert, "--osm-files", f"{SCENARIO}.osm.xml", "--geometry.remove", "true",
        "--no-turnarounds", "true", "--output.street-names", "true", "-o", f"{SCENARIO}.net.xml",
    ], cwd=PILOT_DIR, check=True)
    with TemporaryDirectory(prefix="urbanflow-pilot-") as temp_dir:
        output = Path(temp_dir) / "trajectories.xml"
        subprocess.run([
            sumo, "-c", f"{SCENARIO}.sumocfg", "--fcd-output", str(output), "--no-step-log", "true",
        ], cwd=PILOT_DIR, check=True)
        frames = fcd_frames(output, {"incoming": INCOMING})
    write_replay(OUTPUT, "urbanflowPilot", pilot_metadata(), frames, "sumo_scenario/export_pilot.py")


if __name__ == "__main__":
    main()
