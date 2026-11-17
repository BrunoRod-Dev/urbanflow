"""Build the south window from an archived OSM map response."""

import hashlib
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import build_sector01_williman_geography as pilot


BOUNDS = (pilot.BOUNDS[0], -34.95540, pilot.BOUNDS[2], pilot.BOUNDS[1])
URL = "https://api.openstreetmap.org/api/0.6/map?bbox=-54.94225,-34.95540,-54.93815,-34.95255"


def build(source, retrieved):
    previous = json.loads(pilot.ASSET.read_bytes())
    root = ET.parse(source)
    nodes = {n.get("id"): (float(n.get("lon")), float(n.get("lat"))) for n in root.findall("node")}
    ways = {w.get("id"): w for w in root.findall("way")}
    beach = root.find("relation[@id='2503824']")
    if beach is None or pilot.tags_of(beach).get("natural") != "beach":
        raise ValueError("Falta Playa Mansa en el extracto.")
    members = {m.get("ref") for m in beach.findall("member") if m.get("type") == "way"}
    if not {"184791636", "186169893"} <= members or pilot.tags_of(ways["184791636"]).get("natural") != "coastline":
        raise ValueError("No se identificaron los bordes de Playa Mansa.")

    def points(way):
        return [nodes[n.get("ref")] for n in way.findall("nd")]

    coast, = pilot.clip_line(points(ways["184791636"]), BOUNDS)
    inland, = pilot.clip_line(points(ways["186169893"]), BOUNDS)
    seam, south = BOUNDS[3], BOUNDS[1]
    for line in (coast, inland):
        if abs(line[0][1] - south) < 1e-8:
            line.reverse()
        if abs(line[0][1] - seam) > 1e-8 or abs(line[-1][1] - south) > 1e-8:
            raise ValueError("Un borde no atraviesa toda la nueva ventana.")
    existing = {f["properties"]["class"]: f for f in previous["features"]
                if f["properties"]["class"] in {"sand", "coastline"}}
    old_coast, = {(x, y) for x, y in existing["coastline"]["geometry"]["coordinates"] if y == seam}
    old_inland, = {(x, y) for x, y in existing["sand"]["geometry"]["coordinates"][0]
                   if y == seam and (x, y) != old_coast}
    for line, anchor in ((coast, old_coast), (inland, old_inland)):
        if abs(line[0][0] - anchor[0]) > 0.0000001:
            raise ValueError("Los extractos discrepan en la unión.")
        line[0] = anchor
    sand = coast + inland[::-1]
    if not pilot.inside((-54.94106, -34.95315), sand):
        raise ValueError("No se pudo comprobar el interior de la franja de arena.")
    west = BOUNDS[0]
    features = [
        pilot.feature("water", "184791636", pilot.polygon_geometry(coast + [(west, south), (west, seam)]),
                      {"derived": True, "source": "natural=coastline"}),
        pilot.feature("sand", "2503824", pilot.polygon_geometry(sand),
                      {"derived": True, "sourceWays": ["184791636", "186169893"]}),
        pilot.feature("coastline", "184791636", pilot.line_geometry(coast), {"natural": "coastline"}),
    ]
    for way in ways.values():
        tags = pilot.tags_of(way)
        kind = ("building" if "building" in tags else "grass" if tags.get("landuse") == "grass"
                else "scrub" if tags.get("natural") == "scrub" else None)
        if kind is None:
            continue
        ring = points(way)
        if len(ring) < 4 or ring[0] != ring[-1]:
            continue
        clipped = pilot.clip_ring(ring[:-1], BOUNDS)
        if len(clipped) < 3 or pilot.area_m2(clipped) < 12:
            continue
        props = {}
        if kind == "building":
            levels = tags.get("building:levels", "")
            height = tags.get("height", "")
            props = {"name": tags.get("name"), "building": tags["building"],
                     "levels": int(levels) if levels.isdigit() else None,
                     "height": float(height) if height.replace(".", "", 1).isdigit() else None,
                     "footprint": "complete"}
        features.append(pilot.feature(kind, way.get("id"),
                                      pilot.polygon_geometry(ring[:-1] if kind == "building" else clipped), props))
    return {"type": "FeatureCollection", "meta": {
        "name": "Rambla Williman, extensión sur", "bounds": BOUNDS,
        "retrievedAt": retrieved, "source": URL, "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "license": previous["meta"]["license"], "licenseName": previous["meta"]["licenseName"],
        "attribution": previous["meta"]["attribution"], "heightRule": previous["meta"]["heightRule"],
        "vegetationRule": previous["meta"]["vegetationRule"],
    }, "features": features}


if __name__ == "__main__":
    source, retrieved, output = sys.argv[1:]
    data = build(Path(source), retrieved)
    with Path(output).open("x", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
