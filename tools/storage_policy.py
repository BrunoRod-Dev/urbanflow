"""Reglas de almacenamiento para las etapas de UrbanFlow.

La limpieza automática solo borra `results/_tmp`. Las corridas certificadas,
los históricos y el SUMO portátil quedan fuera de ese directorio.
"""

from hashlib import sha256
import json
from pathlib import Path


class StorageError(ValueError):
    """La operación pedida mezclaría temporales con material conservado."""


PROTECTED = (
    "results/studies/39f2fd082e4941339942760498206531",
    "results/studies/f2cac09376554d76991d90888016e4de",
    "results/studies/32f97a5d36954c94a02793eea5892e9c",
    "results/studies/7aa8eace2961434d9446b0eb77fe3d0a",
    "results/baseline-v001-tools/portable",
    "results/baseline-v001-cert-10114794",
    "results/camacho-0c-d0025f9d",
    "results/camacho-0b-bde651b1",
    "results/etapa1a-6efcccfe",
    "results/etapa1a-cierre-b4ac0b57",
    "results/etapa1b-v001",
    "results/etapa1b-v002",
    "results/etapa1b-v002-consolidado",
    "results/etapa1c-sector01-validacion",
    "results/etapa1c-sector01-20261113",
    "results/etapa1c3-sector01",
    "results/etapa1c3b-sector01",
    "results/etapa1c4-sector01-3d",
    "results/etapa1c5-sector01",
    "results/etapa1d1-piloto",
    "results/etapa1d2-piloto",
    "sumo_scenario/regional/maldonado.osm.gz",
)

SUMO_PORTABLE = "results/baseline-v001-tools/portable/sumo-1.26.0"
SUMO_ZIP_URL = "https://sumo.dlr.de/releases/1.26.0/sumo-win64-1.26.0.zip"
SUMO_ZIP_SHA256 = "17709c062ba420b3ce6a9e8e2fa1925a8f3a6f9ce87b49dd232a21898c660d71"
SUMO_EXE_SHA256 = "dcdbf4fe1f8268816cda2d0631d407fd8e63b0cad5f3e57fe9cf235d9dece926"
NETCONVERT_SHA256 = "4174c17db813d413c85cdf7ad99a5f59b537ddf80f8caac9e1dfe87a35cb6b51"
SNAPSHOT = "sumo_scenario/regional/maldonado.osm.gz"


def directory_bytes(path):
    """Suma el tamaño de los archivos bajo path."""
    total = 0
    for file in Path(path).rglob("*"):
        if file.is_file():
            total += file.stat().st_size
    return total


def stage_growth(before, after):
    """Informa cuánto almacenamiento nuevo produjo una etapa."""
    return {"before": before, "after": after, "added": after - before}


def file_sha256(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root, path):
    resolved_root = Path(root).resolve()
    resolved = Path(path).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise StorageError("La ruta queda fuera del proyecto.")
    return resolved.relative_to(resolved_root)


def is_protected(relative):
    text = Path(relative).as_posix()
    return any(text == item or text.startswith(item + "/") for item in PROTECTED)


def temporary_directory(root, stage):
    """Crea results/_tmp/<etapa>, separado de las corridas certificadas."""
    if not stage or any(character in stage for character in "\\/.:") or stage in {".", ".."}:
        raise StorageError("El nombre de la etapa temporal no es válido.")
    path = Path(root) / "results" / "_tmp" / stage
    path.mkdir(parents=True, exist_ok=True)
    return path


def assert_disposable(root, path):
    relative = _relative(root, path)
    text = relative.as_posix()
    if text != "results/_tmp" and not text.startswith("results/_tmp/"):
        raise StorageError("La limpieza automática solo alcanza results/_tmp.")
    if is_protected(relative):
        raise StorageError("La ruta está protegida.")


def cleanup_temporary(root, stage=None):
    """Borra solo temporales. Devuelve los bytes retirados."""
    if stage is None:
        target = Path(root) / "results" / "_tmp"
    else:
        if not stage or any(character in stage for character in "\\/.:") or stage in {".", ".."}:
            raise StorageError("El nombre de la etapa temporal no es válido.")
        target = Path(root) / "results" / "_tmp" / stage
    if not target.exists():
        return 0
    assert_disposable(root, target)
    removed = 0
    files = [file for file in target.rglob("*") if file.is_file()]
    for file in files:
        assert_disposable(root, file)
        removed += file.stat().st_size
        file.unlink()
    directories = [item for item in target.rglob("*") if item.is_dir()]
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        directory.rmdir()
    if stage is not None:
        target.rmdir()
    return removed


def write_hash_reference(directory, source, name):
    """Anota hash, tamaño y ruta en lugar de copiar un XML, GeoJSON, captura o ZIP idéntico."""
    source = Path(source)
    destination = Path(directory) / name
    if destination.exists():
        raise StorageError("La referencia ya existe.")
    payload = {
        "source": source.as_posix(),
        "sha256": file_sha256(source),
        "bytes": source.stat().st_size,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination
