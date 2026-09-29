# backend/app/services/simulation.py
import math
import random
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.config import settings
from app.core.geo import latlon_to_enu, enu_to_latlon

DRONE_PROFILES: Dict[str, Dict[str, Any]] = {
    "shahed136": {
        "name": "Shahed-136 (Герань-2)",
        "code": "SHAHED-136",
        "speed_range": (50.0, 55.0),
        "alt_range": (140.0, 230.0),
        "acoustic_loudness": 1.0,
        "optical_visibility": 1.0,
        "rf_emission": False,
        "base_debris_radius": 170.0,
        "description": "Важкий далекобійний ударний БПЛА-камікадзе (маса 200 кг)"
    },
    "shahed131": {
        "name": "Shahed-131 (Герань-1)",
        "code": "SHAHED-131",
        "speed_range": (42.0, 48.0),
        "alt_range": (160.0, 260.0),
        "acoustic_loudness": 0.82,
        "optical_visibility": 0.78,
        "rf_emission": False,
        "base_debris_radius": 130.0,
        "description": "Середній ударний БПЛА-камікадзе (маса 135 кг)"
    },
    "gerbera": {
        "name": "Гербера (Decoy/Strike)",
        "code": "GERBERA",
        "speed_range": (36.0, 42.0),
        "alt_range": (200.0, 360.0),
        "acoustic_loudness": 0.55,
        "optical_visibility": 0.65,
        "rf_emission": True,
        "base_debris_radius": 75.0,
        "description": "Легкий БПЛА з пінопласту (фальш-ціль або камікадзе)"
    },
    "orlan10": {
        "name": "Орлан-10 (Розвідник)",
        "code": "ORLAN-10",
        "speed_range": (26.0, 33.0),
        "alt_range": (1200.0, 1850.0),
        "acoustic_loudness": 0.25,
        "optical_visibility": 0.50,
        "rf_emission": True,
        "base_debris_radius": 85.0,
        "description": "Багатоцільовий розвідувальний комплекс (ДВЗ, висота до 2 км)"
    },
    "supercam": {
        "name": "Supercam S350 (Аеророзвідка)",
        "code": "SUPERCAM",
        "speed_range": (28.0, 35.0),
        "alt_range": (800.0, 1450.0),
        "acoustic_loudness": 0.15,
        "optical_visibility": 0.55,
        "rf_emission": True,
        "base_debris_radius": 60.0,
        "description": "Електричний БПЛА типу «літаюче крило» з оптико-тепловізійним підвісом"
    }
}

class DroneSimulation:
    _DRAG_TAU = 2.8

    def __init__(self):
        self.t_sim = 0.0
        self.spawn_random()

    def spawn_random(self, ci_targets: Optional[list] = None):
        profile_key = random.choice(list(DRONE_PROFILES.keys()))
        profile = DRONE_PROFILES[profile_key]
        self.drone_profile = profile
        self.drone_type = profile["name"]
        self.acoustic_loudness = profile["acoustic_loudness"]
        self.optical_visibility = profile["optical_visibility"]
        self.rf_emission = profile["rf_emission"]
        self.base_debris_radius = profile["base_debris_radius"]
        self.description = profile["description"]

        # Спавн за межами кола спостереження 30 км
        dist = random.uniform(34000.0, 45000.0)
        angle_deg = random.uniform(0.0, 360.0)
        rad = math.radians(angle_deg)

        self.x = dist * math.sin(rad)
        self.y = dist * math.cos(rad)
        self.z = random.uniform(profile["alt_range"][0], profile["alt_range"][1])

        self.spawn_lat, self.spawn_lon, _ = enu_to_latlon(self.x, self.y, self.z)
        self.spawn_time = datetime.now()

        if ci_targets and len(ci_targets) > 0:
            chosen = random.choice(ci_targets)
            self.target_name = chosen["name"]
            tgt_x, tgt_y = chosen["x"], chosen["y"]
        else:
            default_targets = [
                ("Київська ГЕС (Турбінний зал)", latlon_to_enu(50.5898, 30.5050)[:2]),
                ("ТЕЦ-6 (Деснянський район)", latlon_to_enu(50.5312, 30.6580)[:2]),
                ("ПС 750кВ «Північна»", latlon_to_enu(50.6200, 30.4500)[:2]),
                ("ТЕЦ-5 (Промислова Теличка)", latlon_to_enu(50.4005, 30.5645)[:2]),
                ("Дарницька ТЕЦ", latlon_to_enu(50.4350, 30.6350)[:2]),
            ]
            chosen = random.choice(default_targets)
            self.target_name = chosen[0]
            tgt_x, tgt_y = chosen[1]

        tgt_x += random.uniform(-150.0, 150.0)
        tgt_y += random.uniform(-150.0, 150.0)

        dx = tgt_x - self.x
        dy = tgt_y - self.y
        dist_to_tgt = math.hypot(dx, dy)

        speed = random.uniform(profile["speed_range"][0], profile["speed_range"][1])
        self.vx = (dx / dist_to_tgt) * speed
        self.vy = (dy / dist_to_tgt) * speed
        self.vz = 0.0

        self.status = "CRUISING"
        self.id = f"{profile['code']}-{random.randint(102, 989)}"
        self.crashed_timer = 0.0
        self.interceptor_name = "Невідомо"
        self.downed_saved = False

        self.detection_history: List[dict] = []
        self.last_112_time = 0.0
        self.emergency_112_dispatched = False
        self.emergency_details = ""
        self.actual_debris_radius = self.base_debris_radius
        self.crash_lat = self.spawn_lat
        self.crash_lon = self.spawn_lon

    def apply_jamming(self, interceptor_name: str):
        if self.status == "CRUISING":
            self.status = "JAMMED"
            self.interceptor_name = interceptor_name
            self.vz = -random.uniform(22.0, 28.0)

    def step(self, dt: float):
        if self.status == "CRASHED":
            self.crashed_timer += dt
            # Залишаємо збитий дрон на карті на 10 секунд перед новим запуском
            if self.crashed_timer >= 10.0:
                self.spawn_random()
            return

        if self.status == "JAMMED":
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

        self.t_sim += dt
        turb_x = math.sin(self.t_sim / 4.0) * 0.25
        turb_y = math.cos(self.t_sim / 4.0) * 0.25
        self.x += (self.vx + turb_x) * dt
        self.y += (self.vy + turb_y) * dt

        if math.hypot(self.x, self.y) > 60000:
            self.spawn_random()