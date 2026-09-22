import json
import math
import os
import urllib.request
from typing import Dict, List, Tuple

try:
    import h3
except Exception:
    h3 = None

RES = 9
GRID_RADIUS_M = 15000.0
W_POP = 0.30
W_BLD = 0.22
W_POI = 0.32
W_ROAD = 0.10
W_GREEN = 0.05
W_WATER = 0.05
_CELL_AREA_CAP = 105000.0
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
UA = "C-UAS-RiskGrid/1.0 (one-shot offline preprocessor; contact: operator of this host)"

_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_base_dir, "data")
GRID_PATH = os.path.join(DATA_DIR, "risk_h3_res9.json")
OSM_CACHE = os.path.join(DATA_DIR, "osm_cache.json")

_cells: Dict[str, dict] = {}
_loaded = False
_max_b = 1
_max_r = 1
_max_a = 1.0


def _ensure_h3():
    if h3 is None:
        raise RuntimeError("h3 lib not installed (pip install -r requirements.txt in venv)")


def _bbox(lat: float, lon: float, r_m: float) -> Tuple[float, float, float, float]:
    d_lat = r_m / 111132.954
    d_lon = r_m / (111412.84 * math.cos(math.radians(lat)))
    return (lat - d_lat, lon - d_lon, lat + d_lat, lon + d_lon)


def _cells_from_pts(cached: dict, lat: float, lon: float) -> dict:
    bld: Dict[str, int] = {}
    road: Dict[str, int] = {}
    area: Dict[str, float] = {}
    poi: Dict[str, int] = {}
    green: Dict[str, float] = {}
    for p in cached.get("pts", []):
        pla, plo, kind = p[0], p[1], p[2]
        ar = float(p[3]) if len(p) > 3 else (120.0 if kind == "b" else 0.0)
        try:
            cell = h3.latlng_to_cell(pla, plo, RES)
        except Exception:
            continue
        if kind == "b":
            bld[cell] = bld.get(cell, 0) + 1
            area[cell] = area.get(cell, 0.0) + ar
        elif kind == "r":
            road[cell] = road.get(cell, 0) + 1
        elif kind == "p":
            poi[cell] = poi.get(cell, 0) + 1
        elif kind in ("g", "w"):
            green[cell] = green.get(cell, 0.0) + ar
    return {"lat": lat, "lon": lon, "bld": bld, "road": road, "area": area, "poi": poi, "green": green}


OSM_TMP = os.path.join(DATA_DIR, "osm_cache_tmp.json")


def _poly_area_m2(geom: list, ref_lat: float) -> float:
    kx = 111412.84 * math.cos(math.radians(ref_lat))
    ky = 111132.954
    lo0 = geom[0]["lon"]
    la0 = geom[0]["lat"]
    s = 0.0
    for i in range(len(geom)):
        x1 = (geom[i]["lon"] - lo0) * kx
        y1 = (geom[i]["lat"] - la0) * ky
        x2 = (geom[(i + 1) % len(geom)]["lon"] - lo0) * kx
        y2 = (geom[(i + 1) % len(geom)]["lat"] - la0) * ky
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _query(s: float, w: float, n: float, e: float, part: str) -> list:
    if part == "b":
        q = f"[out:json][timeout:180];(way[\"building\"]({s},{w},{n},{e}););out geom 50000;"
    else:
        q = f"[out:json][timeout:180];(way[\"highway\"]({s},{w},{n},{e}););out center 50000;"
    for url in OVERPASS_URLS:
        try:
            req = urllib.request.Request(
                url, data=q.encode(),
                headers={
                    "Content-Type": "text/plain",
                    "Accept": "application/json",
                    "User-Agent": UA,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=190) as r:
                data = json.load(r)
            pts = []
            for el in data.get("elements", []):
                tags = el.get("tags") or {}
                if part == "b":
                    if "building" not in tags:
                        continue
                    geom = el.get("geometry") or []
                    if len(geom) >= 3:
                        cx = sum(g["lon"] for g in geom) / len(geom)
                        cy = sum(g["lat"] for g in geom) / len(geom)
                        area = _poly_area_m2(geom, cy)
                    else:
                        cx = el.get("lon", el.get("center", {}).get("lon"))
                        cy = el.get("lat", el.get("center", {}).get("lat"))
                        area = 120.0
                    if cx is None or cy is None:
                        continue
                    pts.append([cy, cx, "b", round(area, 1)])
                else:
                    if "highway" not in tags:
                        continue
                    cla = el.get("lat", el.get("center", {}).get("lat"))
                    clo = el.get("lon", el.get("center", {}).get("lon"))
                    if cla is None or clo is None:
                        continue
                    pts.append([cla, clo, "r", 0.0])
            return pts
        except Exception:
            continue
    return []


def _save_tmp(state: dict):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(OSM_TMP, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def fetch_osm_counts(lat: float, lon: float, r_m: float = GRID_RADIUS_M) -> dict:
    import time
    s, w, n, e = _bbox(lat, lon, r_m)
    if os.path.exists(OSM_CACHE):
        try:
            with open(OSM_CACHE) as f:
                cached = json.load(f)
            if (abs(cached.get("lat", 0) - lat) < 1e-6
                    and abs(cached.get("lon", 0) - lon) < 1e-6
                    and abs(cached.get("r_m", 0) - r_m) < 1e-6
                    and cached.get("v", 0) >= 2
                    and "pts" in cached):
                return _cells_from_pts(cached, lat, lon)
        except Exception:
            pass
    tiles = []
    n_lat, n_lon = 3, 3
    for i in range(n_lat):
        for j in range(n_lon):
            tiles.append((
                s + (n - s) * i / n_lat, w + (e - w) * j / n_lon,
                s + (n - s) * (i + 1) / n_lat, w + (e - w) * (j + 1) / n_lon,
            ))
    state = {"lat": lat, "lon": lon, "r_m": r_m, "v": 2, "done": [], "pts": []}
    if os.path.exists(OSM_TMP):
        try:
            with open(OSM_TMP) as f:
                prev = json.load(f)
            if (abs(prev.get("lat", 0) - lat) < 1e-6
                    and abs(prev.get("lon", 0) - lon) < 1e-6
                    and abs(prev.get("r_m", 0) - r_m) < 1e-6
                    and prev.get("v", 0) >= 2):
                state = prev
        except Exception:
            pass
    done = {tuple(t) for t in state.get("done", [])}
    for k, (ts, tw, tn, te) in enumerate(tiles):
        key = (ts, tw, tn, te)
        if key in done:
            print(f"tile {k + 1}/{len(tiles)} cached", flush=True)
            continue
        t0 = time.time()
        pts = _query(ts, tw, tn, te, "b")
        time.sleep(8)
        pts += _query(ts, tw, tn, te, "r")
        if len(pts) >= 90000:
            mid_lat, mid_lon = (ts + tn) / 2.0, (tw + te) / 2.0
            for qs, qw, qn, qe in (
                (ts, tw, mid_lat, mid_lon), (ts, mid_lon, mid_lat, te),
                (mid_lat, tw, tn, mid_lon), (mid_lat, mid_lon, tn, te),
            ):
                time.sleep(8)
                pts += _query(qs, qw, qn, qe, "b")
                time.sleep(8)
                pts += _query(qs, qw, qn, qe, "r")
        state["pts"].extend(pts)
        state["done"].append(list(key))
        _save_tmp(state)
        print(f"tile {k + 1}/{len(tiles)} +{len(pts)} pts ({time.time() - t0:.0f}s)", flush=True)
        time.sleep(8)
    pts = state["pts"]
    seen = set()
    uniq = []
    for p in pts:
        pla, plo, kind = p[0], p[1], p[2]
        ar = float(p[3]) if len(p) > 3 else 0.0
        key = (round(pla, 6), round(plo, 6), kind)
        if key not in seen:
            seen.add(key)
            uniq.append([pla, plo, kind, ar])
    out = {"lat": lat, "lon": lon, "r_m": r_m, "v": 2, "pts": uniq}
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(OSM_CACHE, "w") as f:
            json.dump(out, f)
        if os.path.exists(OSM_TMP):
            os.remove(OSM_TMP)
    except Exception:
        pass
    print(f"osm total: {len(uniq)} pts", flush=True)
    return _cells_from_pts(out, lat, lon)


def sample_raster(_tif_path: str, _lat: float, _lon: float) -> float:
    return 0.0


def build_static_cells(lat: float, lon: float, r_m: float = GRID_RADIUS_M) -> Dict[str, dict]:
    _ensure_h3()
    center = h3.latlng_to_cell(lat, lon, RES)
    k = int(r_m / 250.0) + 2
    cells: Dict[str, dict] = {}
    for c in h3.grid_disk(center, k):
        try:
            la, lo = h3.cell_to_latlng(c)
        except Exception:
            continue
        dx = (lo - lon) * 111412.84 * math.cos(math.radians(lat))
        dy = (la - lat) * 111132.954
        if dx * dx + dy * dy > r_m * r_m:
            continue
        cells[c] = {"lat": la, "lon": lo}
    osm = fetch_osm_counts(lat, lon, r_m)
    bld = osm.get("bld", {})
    road = osm.get("road", {})
    area = osm.get("area", {})
    poi = osm.get("poi", {})
    green = osm.get("green", {})
    green_c = {k: min(v, _CELL_AREA_CAP) for k, v in green.items()}
    max_a = max(1.0, max(area.values()) if area else 1.0)
    max_r = max(1, max(road.values()) if road else 1)
    _raw_max_poi = max(poi.values()) if poi else 1
    max_poi = min(_raw_max_poi, 50)
    max_g = max(1.0, max(green_c.values()) if green_c else 1.0)
    for c, info in cells.items():
        nb = bld.get(c, 0)
        nr = road.get(c, 0)
        ar = area.get(c, 0.0)
        np_ = poi.get(c, 0)
        ag = min(green.get(c, 0.0), _CELL_AREA_CAP)
        pop_proxy = ar / 25.0
        pop_n = math.log10(1.0 + pop_proxy) / math.log10(1.0 + max_a / 25.0)
        b_n = math.log1p(ar) / math.log1p(max_a)
        r_n = math.log1p(nr) / math.log1p(max_r)
        poi_n = math.log1p(np_) / math.log1p(max_poi)
        g_n = math.log1p(ag) / math.log1p(max_g)
        r_raw = W_POP * pop_n + W_BLD * b_n + W_POI * poi_n + W_ROAD * r_n - W_GREEN * g_n
        cells[c]["static_risk"] = max(0.0, min(1.0, r_raw))
        cells[c]["bld"] = nb
        cells[c]["road"] = nr
        cells[c]["poi"] = np_
        cells[c]["green"] = round(ag, 1)
        cells[c]["area"] = round(ar, 1)
    blurred = {}
    for c, info in cells.items():
        try:
            ring = h3.grid_disk(c, 1)
        except Exception:
            ring = [c]
        vals = [cells[x]["static_risk"] for x in ring if x in cells]
        blurred[c] = sum(vals) / max(1, len(vals))
    for c in cells:
        cells[c]["static_risk"] = blurred[c]
        cells[c]["safety"] = 1.0 - blurred[c]
    return cells


def save_grid(cells: Dict[str, dict], path: str = GRID_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"res": RES, "cells": cells}, f)


def load_grid(path: str = GRID_PATH) -> bool:
    global _cells, _loaded, _max_b, _max_r, _max_a
    global _max_poi, _max_g
    _ensure_h3()
    try:
        with open(path) as f:
            data = json.load(f)
        _cells = data.get("cells", {})
        _max_b = max([1] + [int(v.get("bld", 0)) for v in _cells.values()])
        _max_r = max([1] + [int(v.get("road", 0)) for v in _cells.values()])
        _max_a = max([1.0] + [float(v.get("area", 0.0)) for v in _cells.values()])
        _max_poi = max([1] + [int(v.get("poi", 0)) for v in _cells.values()])
        _max_g = max([1.0] + [float(v.get("green", 0.0)) for v in _cells.values()])
        _loaded = True
        return True
    except Exception:
        _loaded = False
        return False

_max_poi = 1
_max_g = 1.0


def _why(nb: int, nr: int, ar: float = 0.0, np_: int = 0, ag: float = 0.0) -> str:
    if np_ > 0 and np_ >= 3 and math.log1p(np_)/math.log1p(_max_poi) * W_POI >= 0.08:
        return "POI/людність: %d об'єктів (кафе/магазини)" % np_
    if ag > 8000:
        return "Зелена/водна зона (~%.0f м² парку/води)" % ag
    if nb <= 0 and nr <= 0 and np_ <= 0:
        return "Відкрита місцевість, об'єктів не знайдено"
    tp = W_POP * math.log10(1.0 + ar / 25.0) / math.log10(1.0 + _max_a / 25.0)
    tb = W_BLD * math.log1p(ar) / math.log1p(_max_a)
    tr = W_ROAD * math.log1p(nr) / math.log1p(_max_r)
    tpoi = W_POI * math.log1p(np_) / math.log1p(_max_poi)
    if tb >= tp and tb >= tr and tb >= tpoi:
        return "Забудова: %d буд. (~%.0f м²)" % (nb, ar)
    if tpoi >= tp and tpoi >= tb and tpoi >= tr:
        return "POI: %d об'єктів" % np_
    if tr >= tp and tr >= tb and tr >= tpoi:
        return "Дорожня мережа: %d сегм." % nr
    return "Щільна забудова поруч (~%.0f м²)" % ar


def _fallback_safety(x: float, y: float, safe_polys, danger_polys, ci_assets) -> float:
    from shapely.geometry import Point
    pt = Point(x, y)
    try:
        for dz in danger_polys or []:
            if dz.contains(pt):
                s = 0.05
                break
        else:
            s = None
        if s is None:
            for sz in safe_polys or []:
                if sz.contains(pt):
                    s = 0.90
                    break
            else:
                s = 0.45
        if s > 0.5:
            try:
                dmin = min((dz.distance(pt) for dz in (danger_polys or [])), default=1e9)
                if dmin < 150.0:
                    s = 0.45 + (s - 0.45) * (dmin / 150.0)
            except Exception:
                pass
        for ci in ci_assets or []:
            dx = x - ci["x"]
            dy = y - ci["y"]
            d2 = dx * dx + dy * dy
            s -= 0.40 * math.exp(-d2 / (2.0 * 800.0 * 800.0))
        return max(0.02, min(0.98, s))
    except Exception:
        return 0.45


def safety_at_enu(x: float, y: float, lat: float, lon: float,
                  safe_polys, danger_polys, ci_assets) -> float:
    base = None
    if _loaded and _cells and h3 is not None:
        try:
            c = h3.latlng_to_cell(lat, lon, RES)
            info = _cells.get(c)
            if info:
                base = float(info.get("safety", 0.5))
        except Exception:
            base = None
    zone_v = _fallback_safety(x, y, safe_polys, danger_polys, [])
    if base is None:
        s = zone_v
    else:
        s = 0.7 * zone_v + 0.3 * base
    for ci in ci_assets or []:
        dx = x - ci["x"]
        dy = y - ci["y"]
        d2 = dx * dx + dy * dy
        s -= 0.40 * math.exp(-d2 / (2.0 * 800.0 * 800.0))
    return max(0.02, min(0.98, s))


def grid_for_frontend(limit: int = 2500) -> list:
    if not _loaded or not _cells:
        return []
    items = sorted(_cells.items(), key=lambda kv: kv[1].get("safety", 0.5))
    out = []
    stride = max(1, len(items) // limit)
    for i in range(0, len(items), stride):
        c, info = items[i]
        try:
            b = h3.cell_to_boundary(c)
        except Exception:
            continue
        out.append({
            "cell": c,
            "safety": round(float(info.get("safety", 0.5)) * 100.0, 1),
            "risk": round(float(info.get("static_risk", 0.5)) * 100.0, 1),
            "b": int(info.get("bld", 0)),
            "r": int(info.get("road", 0)),
            "poi": int(info.get("poi", 0)),
            "green": round(float(info.get("green", 0.0)), 1),
            "why": _why(int(info.get("bld", 0)), int(info.get("road", 0)), float(info.get("area", 0.0)), int(info.get("poi", 0)), float(info.get("green", 0.0))),
            "boundary": [[p[0], p[1]] for p in b],
        })
        if len(out) >= limit:
            break
    return out
