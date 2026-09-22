import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import osmium
    import h3
except Exception as e:
    print(e); sys.exit(1)
from app.config import settings

LAT0 = settings.DATUM_LAT
LON0 = settings.DATUM_LON

PBF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ukraine-260920.osm.pbf")
if not os.path.exists(PBF):
    import glob
    alt = glob.glob(os.path.join(os.path.dirname(PBF), "*.osm.pbf"))
    PBF = alt[0] if alt else PBF

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "osm_cache.json")
RES = 9
R_M = 15000.0
dlat = R_M / 111132.954
dlon = R_M / (111412.84 * math.cos(math.radians(LAT0)))
S, N, W, E = LAT0 - dlat, LAT0 + dlat, LON0 - dlon, LON0 + dlon
print(f"bbox {S:.6f},{W:.6f} -> {N:.6f},{E:.6f}")
print(f"pbf {PBF} ({os.path.getsize(PBF)/1e6:.0f} MB)")

POI_KEYS = {"amenity","shop","tourism","office","healthcare","craft","emergency"}
LEISURE_POI = {"pitch","sports_centre","stadium","fitness_centre","swimming_pool","playground","track","golf_course"}
GREEN_LEISURE = {"park","garden","nature_reserve","common","recreation_ground"}
GREEN_LANDUSE = {"forest","grass","meadow","recreation_ground","cemetery","greenfield","village_green"}
WATER_NATURAL = {"water","wetland","beach"}
WATER_LANDUSE = {"reservoir","basin"}
WATERWAY = True

def is_poi(tags):
    for k in POI_KEYS:
        if k in tags:
            return True
    if "leisure" in tags and tags["leisure"] in LEISURE_POI:
        return True
    return False

def is_green(tags):
    if tags.get("leisure") in GREEN_LEISURE: return True
    if tags.get("landuse") in GREEN_LANDUSE: return True
    if tags.get("natural") in {"wood","scrub","grassland"}: return True
    return False

def is_water(tags):
    if tags.get("natural") in WATER_NATURAL: return True
    if tags.get("landuse") in WATER_LANDUSE: return True
    if "waterway" in tags: return True
    if tags.get("natural") == "water": return True
    if tags.get("leisure") == "swimming_pool": return False
    if "water" in tags: return True
    return False

def poly_area_m2(lons, lats, ref_lat):
    kx = 111412.84 * math.cos(math.radians(ref_lat))
    ky = 111132.954
    lo0, la0 = lons[0], lats[0]
    s = 0.0
    for i in range(len(lons)):
        x1 = (lons[i]-lo0)*kx; y1 = (lats[i]-la0)*ky
        j = (i+1) % len(lons)
        x2 = (lons[j]-lo0)*kx; y2 = (lats[j]-la0)*ky
        s += x1*y2 - x2*y1
    return abs(s)/2.0

class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.n_in = 0; self.w_in = 0
        self.poi = 0; self.bld = 0; self.road = 0; self.green = 0; self.water = 0
        self.pts = []
    def node(self, n):
        try:
            lon = n.location.lon; lat = n.location.lat
        except: return
        if not (W <= lon <= E and S <= lat <= N): return
        self.n_in += 1
        tags = dict(n.tags)
        if is_poi(tags):
            self.poi += 1
            self.pts.append([lat, lon, "p", 0.0])
        elif is_green(tags) or is_water(tags):
            pass
    def way(self, w):
        try:
            nds = w.nodes
            if len(nds) < 1: return
            lats = []; lons = []
            for nd in nds:
                try: 
                    la = nd.location.lat; lo = nd.location.lon
                except: continue
                lats.append(la); lons.append(lo)
            if not lats: return
            cla = sum(lats)/len(lats); clo = sum(lons)/len(lons)
            if not (W <= clo <= E and S <= cla <= N):
                inside = any(W <= lo <= E and S <= la <= N for lo,la in zip(lons,lats))
                if not inside: return
        except: return
        self.w_in += 1
        tags = dict(w.tags)
        if "building" in tags:
            self.bld += 1
            if len(lons) >= 3:
                ar = poly_area_m2(lons, lats, cla)
                if ar < 5: ar = 60
                if ar > 50000: ar = 50000
            else:
                ar = 120.0
            self.pts.append([cla, clo, "b", round(ar,1)])
            if is_poi(tags):
                self.poi += 1
                self.pts.append([cla, clo, "p", 0.0])
            return
        if is_poi(tags):
            self.poi += 1
            self.pts.append([cla, clo, "p", 0.0])
            return
        if "highway" in tags:
            self.road += 1
            self.pts.append([cla, clo, "r", 0.0])
            return
        if is_water(tags):
            if len(lons) >= 3:
                ar = poly_area_m2(lons, lats, cla)
                self.water += 1
                self.pts.append([cla, clo, "w", round(ar,1)])
            return
        if is_green(tags):
            if len(lons) >= 3:
                ar = poly_area_m2(lons, lats, cla)
                self.green += 1
                self.pts.append([cla, clo, "g", round(ar,1)])
            return

h = H()
print("parsing ... (Kyiv circle filtered)")
h.apply_file(PBF, locations=True)
print(f"nodes_in={h.n_in} ways_in={h.w_in} bld={h.bld} poi={h.poi} road={h.road} green={h.green} water={h.water} pts={len(h.pts)}")

seen=set(); uniq=[]
for p in h.pts:
    k=(round(p[0],6),round(p[1],6),p[2],round(p[3],1) if p[2] in ('b','g','w') else 0)
    if k not in seen:
        seen.add(k); uniq.append(p)
print(f"uniq {len(uniq)} (b={sum(1 for x in uniq if x[2]=='b')} p={sum(1 for x in uniq if x[2]=='p')} r={sum(1 for x in uniq if x[2]=='r')} g={sum(1 for x in uniq if x[2]=='g')} w={sum(1 for x in uniq if x[2]=='w')})")
out={"lat":LAT0,"lon":LON0,"r_m":R_M,"v":3,"pts":uniq}
os.makedirs(os.path.dirname(CACHE), exist_ok=True)
with open(CACHE,"w") as f: json.dump(out,f)
print(f"saved -> {CACHE}")
from app.core.risk_h3 import _cells_from_pts
bld={}; road={}; area={}; poi={}; green={}
for pla,plo,kind,ar in uniq:
    try: cell=h3.latlng_to_cell(pla,plo,RES)
    except: continue
    if kind=='b': bld[cell]=bld.get(cell,0)+1; area[cell]=area.get(cell,0.0)+float(ar)
    elif kind=='r': road[cell]=road.get(cell,0)+1
    elif kind=='p': poi[cell]=poi.get(cell,0)+1
    elif kind=='g': green[cell]=green.get(cell,0.0)+float(ar)
    elif kind=='w': green[cell]=green.get(cell,0.0)+float(ar)
print(f"cells: bld {len(bld)} road {len(road)} poi {len(poi)} green {len(green)}")
