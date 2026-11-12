"""Run and export the marked crossing on Burnett next to Sarandí."""

import argparse
import json
from pathlib import Path
import shutil
from uuid import uuid4
from xml.etree import ElementTree as ET

from .export_web import fcd_frames
from .lane_geometry import replay_geometry
from .signal_replay import prepare_signal_recording, signal_replay
from .study import VEHICLE_LENGTHS, VEHICLE_TYPES, StudyError, map_network, run_tool, saved_catalog, sumo_tools, tags, write_json


PILOT = Path(__file__).resolve().parent / "pilot" / "burnett-crossing"
RESULTS = PILOT.parents[2] / "results"
BASE = RESULTS / "studies" / "1326984e1af04135a05c1d17adab271b"
OUTPUT = RESULTS / "pilot-burnett-pedestrians"
OSM_NODE = "1961589755"
CROSSING = f":{OSM_NODE}_c0"
ROAD = "184791610#2"
ROAD_AFTER = f"{ROAD}.peatonal"
REFERENCE_SHAPE = "904.02,1087.02 970.32,1092.03 999.36,1094.24 1005.95,1094.36"


def crossing_location(base):
    extract = ET.parse(base / "recorte.osm.xml")
    node = extract.find(f"node[@id='{OSM_NODE}']")
    if node is None or tags(node).get("crossing:markings") != "zebra":
        raise StudyError("El recorte de origen no contiene la cebra registrada de Burnett.")
    return [float(node.get("lon")), float(node.get("lat"))]


def split_vehicle_routes(source, destination):
    demand = ET.parse(source)
    for route in demand.iter("route"):
        edges = route.get("edges", "").split()
        if ROAD in edges:
            route.set("edges", " ".join(f"{edge} {ROAD_AFTER}" if edge == ROAD else edge for edge in edges))
    demand.write(destination, encoding="utf-8", xml_declaration=True)


def person_replay(path, location):
    people = {}
    frames = []
    root = None
    for event, node in ET.iterparse(path, events=("start", "end")):
        if root is None:
            root = node
        if event != "end" or node.tag != "timestep":
            continue
        samples = []
        for person in node.findall("person"):
            identifier = person.attrib["id"]
            people[identifier] = person.attrib["type"]
            x, y, angle, speed, position = (float(person.attrib[key]) for key in ("x", "y", "angle", "speed", "pos"))
            samples.append([identifier, x, y, angle, speed, person.attrib["edge"], position])
        frames.append([float(node.attrib["time"]), samples])
        root.remove(node)
    return {
        "source": "sumo", "geographic": True,
        "crossing": {"osmNode": OSM_NODE, "edge": CROSSING, "location": location, "priority": "pedestrian"},
        "personIndex": [{"id": identifier, "type": kind} for identifier, kind in people.items()],
        "sampleFields": ["id", "longitude", "latitude", "heading", "speed", "edge", "position"],
        "frames": frames,
    }


def publish_replay(base, output, network, pedestrians):
    metadata = json.loads((base / "metadata.json").read_text(encoding="utf-8"))
    catalog, _ = saved_catalog(base, metadata)
    approaches = {movement["entry"]: movement["from"] for movement in catalog}
    motion = replay_geometry(network, output / "map.nod.xml")
    if motion is None:
        raise StudyError("SUMO no produjo la proyección necesaria para abrir la corrida en el visor.")
    vehicles = []
    frames = fcd_frames(output / "trajectories.xml", {"incoming": {key: key for key in approaches}},
                        geographic=True, vehicle_lengths={**VEHICLE_LENGTHS, "auto-ensayo": VEHICLE_LENGTHS["car"]},
                        vehicle_index=vehicles)
    if [t for t, _ in frames] != [t for t, _ in pedestrians["frames"]]:
        raise StudyError("Las muestras de peatones y vehículos tienen relojes distintos.")
    signals = signal_replay(output, network)
    if not signals or not signals["states"]:
        raise StudyError("SUMO no registró las fases de esta corrida.")
    used = {edge for filename in ("routes.rou.xml", "probe.rou.xml")
            for route in ET.parse(output / filename).iter("route") for edge in route.attrib["edges"].split()}
    summary = ET.parse(output / "summary.xml").getroot()[-1]
    replay = {
        "title": "Cebra de Burnett y Sarandí", "junctionId": f"n{OSM_NODE}",
        "location": pedestrians["crossing"]["location"], "sceneOrigin": metadata["location"],
        "bounds": metadata["bounds"], "accesses": ["Enrique G. Burnett", "Sarandí"],
        "source": "sumo", "geographic": True, "seed": metadata["seed"], "seconds": 300,
        "trips": int(summary.attrib["loaded"]), "inserted": int(summary.attrib["inserted"]),
        "arrived": int(summary.attrib["arrived"]),
        "assumptions": ["Anchos estimados. La espera del peatón 04 es una pausa de muestra en la vereda."],
        "traffic": {"source": "sample", "durationMinutes": metadata["traffic"]["durationMinutes"], "movements": []},
        "network": map_network(output, used), "approaches": approaches, "frames": frames, "laneMotion": motion,
        "vehicleTypes": {**VEHICLE_TYPES, "auto-ensayo": VEHICLE_TYPES["car"]}, "vehicleIndex": vehicles,
        "pedestrianReplay": pedestrians, "signalReplay": signals,
    }
    shutil.copyfile(base / "recorte.osm.xml", output / "recorte.osm.xml")
    write_json(output / "status.json", {"stage": "ready", "message": "Corrida peatonal lista."})
    write_json(output / "replay.json", replay)


def run_pilot(base, output, *, web=False):
    if output.exists():
        raise StudyError(f"Ya existe {output}. Usá --output para guardar otra corrida en una carpeta nueva.")
    network = ET.parse(base / "network.net.xml")
    road = network.find(f"edge[@id='{ROAD}']")
    if road is None or road.get("shape") != REFERENCE_SHAPE or len(road.findall("lane")) != 1:
        raise StudyError("La geometría guardada de Burnett difiere de la usada para ubicar la cebra.")
    location = crossing_location(base)
    sumo, netconvert, env = sumo_tools()
    output.mkdir(parents=True)
    for name in ("burnett.sumocfg", "gui.settings.xml", "probe.rou.xml", "pedestrians.rou.xml"):
        shutil.copyfile(PILOT / name, output / name)
    split_vehicle_routes(base / "routes.rou.xml", output / "routes.rou.xml")
    run_tool([
        netconvert, "--sumo-net-file", str(base / "network.net.xml"),
        "--node-files", str(PILOT / "crossing.nod.xml"), "--edge-files", str(PILOT / "crossing.edg.xml"),
        "--connection-files", str(PILOT / "crossing.con.xml"), "--offset.disable-normalization", "true",
        "--no-turnarounds", "true", "--output-file", "network.net.xml", "--plain-output-prefix", "map",
        "--proj.plain-geo", "true", "--plain-output.lanes", "true", "--output.street-names", "true",
        "--precision.geo", "7",
    ], output, env, "La preparación de la cebra")
    network = ET.parse(output / "network.net.xml")
    if network.find(f"edge[@id='{CROSSING}'][@function='crossing']") is None:
        raise StudyError("SUMO no pudo conectar las veredas con la cebra de Burnett. Revisá sumo.log.")
    signal_args = []
    if web:
        people_path = output / "pedestrians.rou.xml"
        people = ET.parse(people_path)
        people.getroot().extend(ET.parse(PILOT / "waiting.rou.xml").findall("person"))
        people.write(people_path, encoding="utf-8", xml_declaration=True)
        waiting = "waiting.add.xml"
        shutil.copyfile(PILOT / waiting, output / waiting)
        config_path = output / "burnett.sumocfg"
        config = ET.parse(config_path)
        ET.SubElement(config.find("input"), "additional-files", value=waiting)
        config.write(config_path, encoding="utf-8", xml_declaration=True)
        signal_args = prepare_signal_recording(network, output)
        signal_args = ["--additional-files", ",".join([waiting, *signal_args[1:]])]
    run_tool([
        sumo, "-c", "burnett.sumocfg", "--no-step-log", "true", "--fcd-output", "trajectories.xml",
        "--person-fcd-output", "pedestrians.fcd.xml", "--fcd-output.geo", "true", "--precision.geo", "7",
        "--tripinfo-output", "trips.xml", "--summary-output", "summary.xml", *signal_args,
    ], output, env, "La corrida peatonal")
    replay = person_replay(output / "pedestrians.fcd.xml", location)
    expected = {person.attrib["id"] for person in ET.parse(output / "pedestrians.rou.xml").findall("person")}
    crossed = {sample[0] for _, frame in replay["frames"] for sample in frame if sample[5] == CROSSING}
    if crossed != expected:
        raise StudyError("Faltan trayectorias de peatones sobre la cebra. Revisá sumo.log.")
    write_json(output / "pedestrian-replay.json", replay)
    if web:
        publish_replay(base, output, network, replay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE, help="Carpeta de la corrida de origen de Roosevelt–Camacho")
    parser.add_argument("--output", type=Path, help="Carpeta nueva para la corrida y su exportación")
    parser.add_argument("--web", action="store_true", help="Guardar una corrida para el visor con una espera de muestra")
    args = parser.parse_args()
    default_output = RESULTS / "studies" / uuid4().hex if args.web else OUTPUT
    output = (args.output or default_output).resolve()
    try:
        run_pilot(args.base.resolve(), output, web=args.web)
    except (StudyError, OSError, ET.ParseError) as error:
        parser.exit(1, f"{error}\n")
    print(f"Escenario SUMO: {output / 'burnett.sumocfg'}")
    print(f"Trayectorias peatonales: {output / 'pedestrian-replay.json'}")
    if args.web:
        print(f"Corrida web: http://127.0.0.1:8000/#estudio/{output.name}")


if __name__ == "__main__":
    main()
