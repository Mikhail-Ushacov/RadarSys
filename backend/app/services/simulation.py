# backend/app/services/simulation.py
import math
import random
from datetime import datetime
from typing import List, Optional

from app.config import settings
from app.core.geo import latlon_to_enu, enu_to_latlon

class DroneSimulation:
    """
    Фізична модель польоту ворожого БПЛА (Shahed-136).
    Дрон з'являється глибоко за межами міста (18-26 км),
    вибирає стратегічну ціль і прямує до неї на висоті 160-240м.
    Поки жоден сенсор або свідок його не засік — він залишається невидимим для C2.
    """
    _DRAG_TAU = 2.8

    def __init__(self):
        self.t_sim = 0.0
        self.spawn_random()

    def spawn_random(self, ci_targets: Optional[list] = None):
        # Поява на рубежах 18-26 км
        angle_deg = random.choice([
            random.uniform(-70.0, -25.0), # Північний захід
            random.uniform(-25.0, 25.0),  # Північ
            random.uniform(25.0, 75.0)    # Північний схід
        ])
        dist = random.uniform(18000.0, 26000.0)
        rad = math.radians(angle_deg)

        self.x = dist * math.sin(rad)
        self.y = dist * math.cos(rad)
        self.z = random.uniform(160.0, 240.0)

        self.spawn_lat, self.spawn_lon, _ = enu_to_latlon(self.x, self.y, self.z)
        self.spawn_time = datetime.now()

        default_targets = [
            ("Київська ГЕС (Турбінний зал)", latlon_to_enu(50.5898, 30.5050)[:2]),
            ("ТЕЦ-6 (Деснянський район)", latlon_to_enu(50.5312, 30.6580)[:2]),
            ("ПС 750кВ «Північна»", latlon_to_enu(50.6200, 30.4500)[:2]),
            ("ТЕЦ-5 (Промислова Теличка)", latlon_to_enu(50.4005, 30.5645)[:2]),
            ("Дарницька ТЕЦ", latlon_to_enu(50.4350, 30.6350)[:2]),
        ]

        if ci_targets and len(ci_targets) > 0:
            chosen = random.choice(ci_targets)
            self.target_name = chosen["name"]
            tgt_x, tgt_y = chosen["x"], chosen["y"]
        else:
            chosen = random.choice(default_targets)
            self.target_name = chosen[0]
            tgt_x, tgt_y = chosen[1]

        tgt_x += random.uniform(-250.0, 250.0)
        tgt_y += random.uniform(-250.0, 250.0)

        dx = tgt_x - self.x
        dy = tgt_y - self.y
        dist_to_tgt = math.hypot(dx, dy)

        speed = random.uniform(49.0, 54.0)  # ~175-195 км/год
        self.vx = (dx / dist_to_tgt) * speed
        self.vy = (dy / dist_to_tgt) * speed
        self.vz = 0.0

        self.status = "CRUISING"
        self.id = f"SHAHED-{random.randint(102, 989)}"
        self.crashed_timer = 0.0
        self.interceptor_name = "Невідомо"
        self.downed_saved = False

        self.detection_history: List[dict] = []
        self.last_112_time = 0.0
        self.last_sensor_time = 0.0

    def apply_jamming(self, interceptor_name: str):
        if self.status == "CRUISING":
            self.status = "JAMMED"
            self.interceptor_name = interceptor_name
            self.vz = -random.uniform(20.0, 25.0)

    def step(self, dt: float):
        if self.status == "CRASHED":
            self.crashed_timer += dt
            if self.crashed_timer >= 5.0:
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
            return

        self.t_sim += dt
        turb_x = math.sin(self.t_sim / 4.0) * 0.3
        turb_y = math.cos(self.t_sim / 4.0) * 0.3
        self.x += (self.vx + turb_x) * dt
        self.y += (self.vy + turb_y) * dt

        if math.hypot(self.x, self.y) > 50000:
            self.spawn_random()