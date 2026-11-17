"""Convert between geographic coordinates and the Cartesian frame stored by SUMO.

The replay records one projection. An existing affine fit stays as it was saved.
A new study stores the UTM projection declared by the network, including the
false northing that makes netOffset land on convBoundary.
"""

from math import cos, degrees, radians, sin, sqrt, tan
from xml.etree import ElementTree as ET


class ProjectionError(ValueError):
    """The network projection cannot be used for the 3D view."""


A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)
EP2 = E2 / (1 - E2)
K0 = 0.9996
FALSE_EASTING = 500_000.0
SOUTHERN_FALSE_NORTHING = 10_000_000.0
_ACCEPTED_ELLIPSOIDS = {None, 'WGS84', 'GRS80'}


def _tokens(proj):
    fields = {}
    for token in str(proj).split():
        if not token.startswith('+'):
            continue
        body = token[1:]
        if '=' in body:
            key, value = body.split('=', 1)
            fields[key] = value
        else:
            fields[body] = True
    return fields


def parse_utm(proj):
    """Return the UTM zone and whether the PROJ string forces the southern false northing."""
    if not isinstance(proj, str) or not proj.strip():
        raise ProjectionError('La red no declara projParameter. La vista 3D no puede construirse.')
    fields = _tokens(proj)
    if fields.get('proj') != 'utm':
        raise ProjectionError(
            f'La proyección «{proj}» no está soportada. La vista 3D acepta UTM (+proj=utm +zone=N).')
    try:
        zone = int(fields['zone'])
    except (KeyError, TypeError, ValueError):
        raise ProjectionError('La proyección UTM no declara una zona entre 1 y 60.') from None
    if not 1 <= zone <= 60:
        raise ProjectionError('La proyección UTM no declara una zona entre 1 y 60.')
    ellipsoid = fields.get('ellps')
    datum = fields.get('datum')
    if ellipsoid not in _ACCEPTED_ELLIPSOIDS or datum not in {None, 'WGS84'}:
        name = ellipsoid or datum or 'desconocido'
        raise ProjectionError(f'El elipsoide «{name}» no está soportado. La vista 3D acepta WGS84.')
    units = fields.get('units')
    if units not in {None, 'm'}:
        raise ProjectionError(f'La proyección declara unidades «{units}». La vista 3D acepta metros.')
    return zone, fields.get('south') is True


def _meridional(lat):
    return A * (
        (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256) * lat
        - (3 * E2 / 8 + 3 * E2 ** 2 / 32 + 45 * E2 ** 3 / 1024) * sin(2 * lat)
        + (15 * E2 ** 2 / 256 + 45 * E2 ** 3 / 1024) * sin(4 * lat)
        - (35 * E2 ** 3 / 3072) * sin(6 * lat)
    )


def _forward_equator(lon_deg, lat_deg, zone):
    """Standard UTM easting and northing measured from the equator, without the southern false northing."""
    lon = radians(lon_deg)
    lat = radians(lat_deg)
    lon0 = radians(-183 + 6 * zone)
    sine = sin(lat)
    cosine = cos(lat)
    tangent = tan(lat)
    radius = A / sqrt(1 - E2 * sine * sine)
    t = tangent * tangent
    c = EP2 * cosine * cosine
    aa = (lon - lon0) * cosine
    easting = FALSE_EASTING + K0 * radius * (
        aa + (1 - t + c) * aa ** 3 / 6
        + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * aa ** 5 / 120
    )
    northing = K0 * (
        _meridional(lat) + radius * tangent * (
            aa * aa / 2
            + (5 - t + 9 * c + 4 * c * c) * aa ** 4 / 24
            + (61 - 58 * t + t * t + 600 * c - 330 * EP2) * aa ** 6 / 720
        )
    )
    return easting, northing


def _inverse_equator(easting, northing, zone):
    x = easting - FALSE_EASTING
    lon0 = radians(-183 + 6 * zone)
    e1 = (1 - sqrt(1 - E2)) / (1 + sqrt(1 - E2))
    mu = northing / K0 / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    lat1 = (
        mu
        + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * sin(2 * mu)
        + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * sin(4 * mu)
        + (151 * e1 ** 3 / 96) * sin(6 * mu)
        + (1097 * e1 ** 4 / 512) * sin(8 * mu)
    )
    sine = sin(lat1)
    cosine = cos(lat1)
    tangent = tan(lat1)
    radius = A / sqrt(1 - E2 * sine * sine)
    t = tangent * tangent
    c = EP2 * cosine * cosine
    vertical = A * (1 - E2) / (1 - E2 * sine * sine) ** 1.5
    d = x / (radius * K0)
    lat = lat1 - (radius * tangent / vertical) * (
        d ** 2 / 2
        - (5 + 3 * t + 10 * c - 4 * c * c - 9 * EP2) * d ** 4 / 24
        + (61 + 90 * t + 298 * c + 45 * t * t - 252 * EP2 - 3 * c * c) * d ** 6 / 720
    )
    lon = lon0 + (
        d
        - (1 + 2 * t + c) * d ** 3 / 6
        + (5 - 2 * c + 28 * t - 3 * c * c + 8 * EP2 + 24 * t * t) * d ** 5 / 120
    ) / cosine
    return degrees(lon), degrees(lat)


def _pair(text):
    try:
        left, right = (float(value) for value in text.split(','))
    except (AttributeError, TypeError, ValueError):
        return None
    return left, right


def _projected_box(west, south, east, north, zone, false_northing, offset):
    corners = []
    for lon, lat in ((west, south), (east, south), (west, north), (east, north)):
        ex, ny = _forward_equator(lon, lat, zone)
        corners.append((ex + offset[0], ny + false_northing + offset[1]))
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _contains(outer, inner, slack):
    return (outer[0] - slack <= inner[0] and outer[2] + slack >= inner[2]
            and outer[1] - slack <= inner[1] and outer[3] + slack >= inner[3])


def false_northing_for(proj, offset, orig_boundary, conv_boundary):
    """Pick the false northing that places the original boundary around the converted network."""
    zone, south_flag = parse_utm(proj)
    west, south, east, north = orig_boundary
    preferred = SOUTHERN_FALSE_NORTHING if south_flag else 0.0
    fitting = []
    for candidate in (preferred, SOUTHERN_FALSE_NORTHING - preferred):
        box = _projected_box(west, south, east, north, zone, candidate, offset)
        if _contains(box, conv_boundary, 50):
            center_error = abs((box[0] + box[2]) / 2 - (conv_boundary[0] + conv_boundary[2]) / 2)
            center_error += abs((box[1] + box[3]) / 2 - (conv_boundary[1] + conv_boundary[3]) / 2)
            fitting.append((center_error, candidate))
    if not fitting:
        raise ProjectionError(
            f'El netOffset no coincide con «{proj}». La vista 3D no puede alinear la red.')
    fitting.sort()
    return fitting[0][1]


def projection_from_network(network):
    """Read SUMO's location element and return the single projection a new replay must store."""
    root = network.getroot() if isinstance(network, ET.ElementTree) else network
    location = root.find('location') if root is not None else None
    if location is None:
        raise ProjectionError('La red no declara la proyección. La vista 3D no puede construirse.')
    proj = location.get('projParameter')
    offset = _pair(location.get('netOffset'))
    raw_orig = location.get('origBoundary')
    raw_conv = location.get('convBoundary')
    if offset is None:
        raise ProjectionError('La red no declara netOffset. La vista 3D no puede construirse.')
    try:
        orig_values = tuple(float(value) for value in raw_orig.split(','))
        conv_values = tuple(float(value) for value in raw_conv.split(','))
    except (AttributeError, TypeError, ValueError):
        orig_values = conv_values = ()
    if len(orig_values) != 4 or len(conv_values) != 4:
        raise ProjectionError(
            'La red no declara origBoundary y convBoundary, así que no se puede fijar el falso norte.')
    false_northing = false_northing_for(proj, offset, orig_values, conv_values)
    zone, _ = parse_utm(proj)
    return {
        'type': 'utm',
        'projParameter': proj,
        'netOffset': [offset[0], offset[1]],
        'zone': zone,
        'falseNorthing': false_northing,
    }


def _as_utm(projection):
    if not isinstance(projection, dict) or projection.get('type') != 'utm':
        raise ProjectionError('La proyección del replay no es UTM.')
    try:
        zone = int(projection['zone'])
        ox, oy = (float(value) for value in projection['netOffset'])
        false_northing = float(projection['falseNorthing'])
    except (KeyError, TypeError, ValueError):
        raise ProjectionError(
            'La proyección UTM del replay está incompleta: falta la zona, el netOffset o el falso norte.'
        ) from None
    if not 1 <= zone <= 60 or false_northing not in (0.0, SOUTHERN_FALSE_NORTHING):
        raise ProjectionError('La proyección UTM del replay usa una zona o un falso norte que no son válidos.')
    return zone, (ox, oy), false_northing


def to_sumo(lon, lat, projection):
    """Return SUMO Cartesian meters for a geographic point."""
    if projection.get('type') == 'utm':
        zone, offset, false_northing = _as_utm(projection)
        easting, northing = _forward_equator(lon, lat, zone)
        return easting + offset[0], northing + false_northing + offset[1]
    origin = projection['origin']
    east, north = projection['east'], projection['north']
    determinant = east[0] * north[1] - east[1] * north[0]
    if determinant == 0:
        raise ProjectionError('La proyección afín guardada no tiene ejes válidos.')
    dlng, dlat = lon - projection['location'][0], lat - projection['location'][1]
    dx = (dlng * north[1] - dlat * north[0]) / determinant
    dy = (east[0] * dlat - east[1] * dlng) / determinant
    return origin[0] + dx, origin[1] + dy


def to_geographic(point, projection):
    """Return longitude and latitude for a SUMO Cartesian point."""
    x, y = point
    if projection.get('type') == 'utm':
        zone, offset, false_northing = _as_utm(projection)
        return _inverse_equator(x - offset[0], y - offset[1] - false_northing, zone)
    ox, oy = projection['origin']
    return tuple(
        location + (x - ox) * east + (y - oy) * north
        for location, east, north in zip(projection['location'], projection['east'], projection['north'])
    )


def linear_axes(projection):
    """Local degrees-per-meter axes. Affine replays keep the axes that were saved."""
    if not projection or projection.get('type') != 'utm':
        return projection['east'], projection['north'], projection['location'][1]
    lon0, lat0 = to_geographic((0.0, 0.0), projection)
    lonx, latx = to_geographic((1.0, 0.0), projection)
    lony, laty = to_geographic((0.0, 1.0), projection)
    return [lonx - lon0, latx - lat0], [lony - lon0, laty - lat0], lat0
