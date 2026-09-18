import math
from shapely.geometry import Point, Polygon
from app.config import settings

class InterceptionPlanner:
    """
    Планувальник точкового придушення:
    1. Рахує траєкторію балістично-інерційного зриву після глушіння GPS.
    2. Перевіряє безпеку падіння над зеленою зоною.
    3. Рахує кути наведення для спрямованої антени РЕБ (Pan-Tilt).
    """
    @staticmethod
    def predict_crash_point(x: float, y: float, z: float, vx: float, vy: float, vz: float):
        # Shahed при глушінні або дезорієнтації планує за глісадою (L/D ~12) або падає.
        # Оцінимо час контакту з землею (z=0)
        current_alt = max(z, 10.0)
        # Швидкість спуску за відмови автопілота або зриву навігації (~4 м/с)
        v_descent = 4.0 if vz >= 0 else abs(vz)
        fall_time = current_alt / v_descent
        
        # Точка падіння враховує вектор польоту + вітрове знесення
        impact_x = x + (vx + settings.WIND_VECTOR_X) * fall_time
        impact_y = y + (vy + settings.WIND_VECTOR_Y) * fall_time
        return impact_x, impact_y, fall_time

    @staticmethod
    def is_safe_drop(impact_x: float, impact_y: float, safe_zones: list[Polygon], danger_zones: list[Polygon]) -> bool:
        pt = Point(impact_x, impact_y)
        for d_zone in danger_zones:
            if d_zone.contains(pt):
                return False  # Падіння на населений пункт чи інфраструктуру
        for s_zone in safe_zones:
            if s_zone.contains(pt):
                return True   # Поле, лісосмуга, пустир
        return False

    @staticmethod
    def evaluate_interception(ew_x: float, ew_y: float, ew_z: float, 
                              target_x: float, target_y: float, target_z: float, 
                              max_range: float = 4000.0, beamwidth: float = 30.0):
        dx = target_x - ew_x
        dy = target_y - ew_y
        dz = target_z - ew_z
        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        
        if dist > max_range:
            return False, 0.0, 0.0, dist
            
        azimuth = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
        elevation = math.degrees(math.atan2(dz, math.sqrt(dx**2 + dy**2)))
        return True, azimuth, elevation, dist