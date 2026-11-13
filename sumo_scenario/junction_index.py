"""Find study locations in the same regional extract used to build the SUMO network."""

from functools import lru_cache
import re
import unicodedata

from .regional_map import coverage, regional_network
from .study import StudyError, junction_candidates, nearby_junctions


SEARCH_LIMIT = 12
IGNORED = {'av', 'avenida', 'calle', 'de', 'del', 'el', 'esq', 'esquina', 'la', 'las', 'los', 'y'}


def words(text):
    normalized = ''.join(char for char in unicodedata.normalize('NFKD', text.casefold())
                         if not unicodedata.combining(char))
    return set(re.findall(r'[a-z0-9]+', normalized)) - IGNORED


@lru_cache(maxsize=1)
def regional_junctions():
    region = coverage()
    if not region['available']:
        raise StudyError('Falta la base vial regional de Maldonado. Revisá los archivos de UrbanFlow.')
    attributes, _, points, ways, _ = regional_network()
    west, south, east, north = region['bounds']
    targets = junction_candidates(points, (way for way, _ in ways.values()))
    index = {target['junctionId']: {**target, 'snapshot': attributes.get('snapshot')} for target in targets
             if west <= target['location'][0] <= east and south <= target['location'][1] <= north}
    terms = {key: words(' '.join(target['accesses'])) for key, target in index.items()}
    return region['bounds'], points, index, terms


def search_junctions(query):
    tokens = words(query)
    if not tokens:
        return {'candidates': [], 'more': False}
    _, _, index, terms = regional_junctions()
    matches = []
    for key, names in terms.items():
        missing = tokens - names
        if any(token.isdecimal() or len(token) < 3 or not any(name.startswith(token) for name in names)
               for token in missing):
            continue
        target = index[key]
        matches.append((len(missing), target['title'].casefold(), key))
    matches.sort()
    return {'candidates': [index[key] for _, _, key in matches[:SEARCH_LIMIT]], 'more': len(matches) > SEARCH_LIMIT}


def resolve_junctions(lon, lat):
    bounds, points, index, _ = regional_junctions()
    west, south, east, north = bounds
    if not west <= lon <= east or not south <= lat <= north:
        raise StudyError('Ese punto queda fuera de la cobertura regional. Usá Ver región y elegí otro lugar.')
    return {'candidates': nearby_junctions(index.values(), points, (lon, lat)), 'more': False}


def confirmed_junction(junction_id):
    _, _, index, _ = regional_junctions()
    if junction_id not in index:
        raise StudyError('Ese cruce ya no está disponible en la base regional. Buscalo de nuevo.')
    return index[junction_id]
