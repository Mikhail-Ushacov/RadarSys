import math
from app.config import settings

# Проста та надшвидка проекція Flat-Earth / ENU (East-North-Up)
# для локальної зони радіусом до 100 км навколо базової точки (Datum).
METERS_PER_DEGREE_LAT = 111132.954

def latlon_to_enu(lat: float, lon: float, alt: float = 0.0):
    d_lat = lat - settings.DATUM_LAT
    d_lon = lon - settings.DATUM_LON
    
    lat_rad = math.radians(settings.DATUM_LAT)
    meters_per_degree_lon = 111412.84 * math.cos(lat_rad)
    
    x = d_lon * meters_per_degree_lon  # East (метри)
    y = d_lat * METERS_PER_DEGREE_LAT  # North (метри)
    z = alt - settings.DATUM_ALT       # Up (метри)
    return x, y, z

def enu_to_latlon(x: float, y: float, z: float = 0.0):
    lat_rad = math.radians(settings.DATUM_LAT)
    meters_per_degree_lon = 111412.84 * math.cos(lat_rad)
    
    d_lat = y / METERS_PER_DEGREE_LAT
    d_lon = x / meters_per_degree_lon
    
    lat = settings.DATUM_LAT + d_lat
    lon = settings.DATUM_LON + d_lon
    alt = settings.DATUM_ALT + z
    return lat, lon, alt

def calculate_azimuth_elevation(src_x: float, src_y: float, src_z: float,
                                dst_x: float, dst_y: float, dst_z: float):
    dx = dst_x - src_x
    dy = dst_y - src_y
    dz = dst_z - src_z
    
    dist_horizontal = math.sqrt(dx**2 + dy**2)
    azimuth_deg = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
    elevation_deg = math.degrees(math.atan2(dz, dist_horizontal))
    
    return azimuth_deg, elevation_deg, math.sqrt(dx**2 + dy**2 + dz**2)