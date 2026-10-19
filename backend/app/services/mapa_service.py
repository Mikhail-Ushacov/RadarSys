# backend/app/services/mapa_service.py
import math
import json
import time
import logging
import urllib.request
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.config import settings
from app.core.geo import latlon_to_enu, enu_to_latlon

logger = logging.getLogger(__name__)

MAPA_API_BASE = "https://mapa.ua/api/v1"
USER_AGENT = "Surgical-EW-C2/1.0 (Live Radar Integration; contact: operator)"

# Співставлення типів БПЛА з mapa.ua із внутрішніми характеристиками сенсорів
MAPA_KIND_MAP = {
    "drone_piston": {
        "name": "Shahed-136 (Герань-2)",
        "code": "SHAHED",
        "optical_visibility": 1.0,
        "acoustic_loudness": 1.0,
        "rf_emission": False,
        "base_debris_radius": 170.0,
        "default_speed_kmh": 165.0,
        "default_alt": 190.0,
    },
    "decoy": {
        "name": "Гербера (Decoy/Strike)",
        "code": "GERBERA",
        "optical_visibility": 0.65,
        "acoustic_loudness": 0.55,
        "rf_emission": True,
        "base_debris_radius": 75.0,
        "default_speed_kmh": 140.0,
        "default_alt": 250.0,
    },
    "drone_jet": {
        "name": "Shahed-238 / Бандероль (Реактивний)",
        "code": "SHAHED-JET",
        "optical_visibility": 0.9,
        "acoustic_loudness": 1.2,
        "rf_emission": False,
        "base_debris_radius": 190.0,
        "default_speed_kmh": 450.0,
        "default_alt": 350.0,
    },
    "drone_fpv": {
        "name": "Молнія / FPV Дальній",
        "code": "MOLNIYA",
        "optical_visibility": 0.45,
        "acoustic_loudness": 0.40,
        "rf_emission": True,
        "base_debris_radius": 45.0,
        "default_speed_kmh": 120.0,
        "default_alt": 80.0,
    }
}


class RealDroneLiveTrack:
    """
    Представлення реального БПЛА з API mapa.ua.
    Підпорядковується законам симуляції: перехопленню РЕБ, зриву навігації,
    балістичному падінню, знесенню вітром та оцінці уламків.
    """
    _DRAG_TAU = 2.8

    def __init__(self, raw_obj: Dict[str, Any], initial_enu: tuple, velocity_enu: tuple):
        self.raw_id = str(raw_obj.get("id", int(time.time())))
        subkind = raw_obj.get("subkind") or raw_obj.get("kind") or "drone_piston"
        profile = MAPA_KIND_MAP.get(subkind, MAPA_KIND_MAP["drone_piston"])

        self.drone_type = raw_obj.get("title") or profile["name"]
        self.id = f"MAPA-{profile['code']}-{self.raw_id}"
        self.optical_visibility = profile["optical_visibility"]
        self.acoustic_loudness = profile["acoustic_loudness"]
        self.rf_emission = profile["rf_emission"]
        self.base_debris_radius = profile["base_debris_radius"]

        self.x, self.y, self.z = initial_enu
        self.vx, self.vy, self.vz = velocity_enu

        self.spawn_lat, self.spawn_lon, _ = enu_to_latlon(self.x, self.y, self.z)
        self.spawn_time = datetime.now()
        self.status = "CRUISING"
        self.target_name = raw_obj.get("to_city", "Київ")
        self.interceptor_name = "Невідомо"
        self.downed_saved = False
        self.crashed_timer = 0.0

        self.detection_history: List[dict] = []
        self.last_112_time = 0.0
        self.emergency_112_dispatched = False
        self.emergency_details = ""
        self.actual_debris_radius = self.base_debris_radius
        self.crash_lat = self.spawn_lat
        self.crash_lon = self.spawn_lon

    def apply_jamming(self, interceptor_name: str):
        """Зрив супутникового наведення комплексом РЕБ."""
        if self.status == "CRUISING":
            self.status = "JAMMED"
            self.interceptor_name = interceptor_name
            self.vz = -25.0  # швидкість втрати висоти

    def step(self, dt: float):
        """Фізичний крок оновлення координат."""
        if self.status == "CRASHED":
            self.crashed_timer += dt
            return

        if self.status == "JAMMED":
            # Балістичний зрив з опором повітря та знесенням вітром
            decay = math.exp(-dt / self._DRAG_TAU)
            self.vx *= decay
            self.vy *= decay
            self.x += (self.vx + settings.WIND_VECTOR_X) * dt
            self.y += (self.vy + settings.WIND_VECTOR_Y) * dt
            self.z += self.vz * dt

            if self.z <= 0.0:
                self.z = 0.0
                self.vx = 0.0
                self.vy = 0.0
                self.vz = 0.0
                self.status = "CRASHED"
                self.crashed_timer = 0.0
                c_lat, c_lon, _ = enu_to_latlon(self.x, self.y, 0.0)
                self.crash_lat = c_lat
                self.crash_lon = c_lon
            return

        # Політ за вектором
        self.x += self.vx * dt
        self.y += self.vy * dt


class MapaUAService:
    def __init__(self):
        self.last_fetch_time: float = 0.0
        self.cached_raw_objects: List[dict] = []
        self.active_tracks: Dict[str, RealDroneLiveTrack] = {}
        self.source_mode: str = "live"  # 'live' або 'replay'
        self.last_attack_id: Optional[int] = None

    def _http_get_json(self, url: str) -> Optional[dict]:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"[MAPA.UA API] Помилка запиту до {url}: {e}")
        return None

    async def fetch_threats(self) -> List[dict]:
        """
        Отримує об'єкти з mapa.ua API:
        1. Спроба отримати живі загрози через /api/v1/nearby або /api/v1/current.
        2. Якщо небо чисте — завантажуються об'єкти з останньої зафіксованої атаки (/api/v1/attacks).
        """
        loop = asyncio.get_running_loop()

        # 1. Запит загроз у радіусі операційної зони (Київ + 150 км)
        nearby_url = f"{MAPA_API_BASE}/nearby?lat={settings.DATUM_LAT}&lon={settings.DATUM_LON}&radius_km=150"
        data = await loop.run_in_executor(None, self._http_get_json, nearby_url)

        objects = []
        if data and data.get("threats"):
            objects = data["threats"]
            self.source_mode = "live"
        else:
            # 2. Якщо навколо немає, перевіряємо загальний /current
            current_url = f"{MAPA_API_BASE}/current"
            curr_data = await loop.run_in_executor(None, self._http_get_json, current_url)
            if curr_data and curr_data.get("objects"):
                objects = curr_data["objects"]
                self.source_mode = "live"

        # 3. Якщо небо чисте (атак зараз немає), підтягуємо реальні БПЛА з останньої атаки для тестування
        if not objects:
            attacks_url = f"{MAPA_API_BASE}/attacks?limit=3"
            att_data = await loop.run_in_executor(None, self._http_get_json, attacks_url)
            if att_data and att_data.get("attacks"):
                latest_attack = att_data["attacks"][0]
                att_id = latest_attack.get("id")
                self.last_attack_id = att_id
                obj_url = f"{MAPA_API_BASE}/objects?attack_id={att_id}"
                obj_data = await loop.run_in_executor(None, self._http_get_json, obj_url)
                if obj_data and obj_data.get("objects"):
                    objects = obj_data["objects"][:4]  # беремо до 4 БПЛА
                    self.source_mode = "replay"

        self.cached_raw_objects = objects
        self.last_fetch_time = time.time()
        return objects

    def sync_tracks(self, raw_objects: List[dict]):
        """Синхронізує об'єкти з API із внутрішніми треками."""
        seen_keys = set()

        for obj in raw_objects:
            obj_id = str(obj.get("id"))
            seen_keys.add(obj_id)

            if obj_id in self.active_tracks:
                track = self.active_tracks[obj_id]
                # Якщо дрон вже збитий нашими РЕБ, не відновлюємо його політ
                if track.status in ("JAMMED", "CRASHED"):
                    continue

            # Координати з API
            lat = float(obj.get("lat", settings.DATUM_LAT + 0.35))
            lon = float(obj.get("lon", settings.DATUM_LON - 0.25))

            # Перетворення у Flat-Earth ENU
            enu_x, enu_y, _ = latlon_to_enu(lat, lon, 0.0)

            # Якщо об'єкт задалеко від зони (>45 км), проєктуємо його на підльотний рубіж (35 км)
            dist_to_center = math.hypot(enu_x, enu_y)
            if dist_to_center > 45000.0 or dist_to_center < 1000.0:
                angle = math.atan2(enu_y, enu_x)
                enu_x = 36000.0 * math.cos(angle)
                enu_y = 36000.0 * math.sin(angle)

            # Швидкість та курс
            heading_deg = float(obj.get("heading") or 135.0)
            subkind = obj.get("subkind") or obj.get("kind") or "drone_piston"
            profile = MAPA_KIND_MAP.get(subkind, MAPA_KIND_MAP["drone_piston"])
            speed_kmh = float(obj.get("speed_kmh") or profile["default_speed_kmh"])
            speed_ms = speed_kmh / 3.6
            alt = float(profile["default_alt"])

            # Вектор швидкості у навігаційних кутах (0° = North, 90° = East)
            heading_rad = math.radians(heading_deg)
            vx = speed_ms * math.sin(heading_rad)
            vy = speed_ms * math.cos(heading_rad)

            if obj_id not in self.active_tracks:
                track = RealDroneLiveTrack(
                    raw_obj=obj,
                    initial_enu=(enu_x, enu_y, alt),
                    velocity_enu=(vx, vy, 0.0)
                )
                self.active_tracks[obj_id] = track
            else:
                track = self.active_tracks[obj_id]
                track.vx = vx
                track.vy = vy

        # Очищення старих завершених треків
        to_delete = []
        for tid, t in self.active_tracks.items():
            if tid not in seen_keys and t.status == "CRASHED" and t.crashed_timer > 20.0:
                to_delete.append(tid)
        for tid in to_delete:
            del self.active_tracks[tid]

    def get_primary_track(self) -> Optional[RealDroneLiveTrack]:
        """Повертає пріоритетну ціль для автосупроводу РЕБ."""
        if not self.active_tracks:
            return None
        # Спочатку шукаємо БПЛА, що летять (CRUISING або JAMMED)
        for t in self.active_tracks.values():
            if t.status in ("CRUISING", "JAMMED"):
                return t
        # Якщо всі збиті — повертаємо останній збитий
        return list(self.active_tracks.values())[-1]

    def step_tracks(self, dt: float):
        for t in self.active_tracks.values():
            t.step(dt)


mapa_service = MapaUAService()