# backend/app/core/planner.py
import math
from shapely.geometry import Point, Polygon
from app.config import settings

class InterceptionPlanner:
    """
    Планувальник точкового та адаптивного придушення:
    1. Рахує траєкторію балістично-інерційного зриву після глушіння GPS.
    2. Перевіряє безпеку падіння над зеленою зоною.
    3. Рахує кути наведення турелі з упередженням (Lead-Angle Prediction).
    4. Адаптує ширину діаграми спрямованості антени (Adaptive Beamwidth).
    5. Виявляє загрозу критичній інфраструктурі (Emergency CI Override).
    """

    @staticmethod
    def predict_lead_point(x: float, y: float, z: float, vx: float, vy: float, vz: float, lead_time_sec: float = 2.0):
        """Розрахунок точки випередження для наведення турелі на ціль."""
        lead_x = x + vx * lead_time_sec
        lead_y = y + vy * lead_time_sec
        lead_z = z + vz * lead_time_sec
        return lead_x, lead_y, lead_z

    @staticmethod
    def calculate_adaptive_beamwidth(distance: float, max_range: float = 5000.0) -> float:
        """
        Адаптація діаграми спрямованості:
        - Дальня дистанція (>3500м): вузький промінь 15-20° для високої щільності енергії.
        - Близька дистанція (<1500м): широкий промінь до 45-55° для утримання високої кутової швидкості.
        """
        norm_dist = max(0.1, min(1.0, distance / max_range))
        # Лінійна інтерполяція від 50° на нульовій дистанції до 15° на граничній
        beamwidth = 50.0 - norm_dist * 35.0
        return round(max(14.0, min(60.0, beamwidth)), 1)

    @staticmethod
    def predict_crash_point(x: float, y: float, z: float, vx: float, vy: float, vz: float):
        current_alt = max(z, 10.0)
        v_descent = 4.0 if vz >= 0 else abs(vz)
        fall_time = current_alt / v_descent
        
        impact_x = x + (vx + settings.WIND_VECTOR_X) * fall_time
        impact_y = y + (vy + settings.WIND_VECTOR_Y) * fall_time
        return impact_x, impact_y, fall_time

    @staticmethod
    def is_safe_drop(impact_x: float, impact_y: float, safe_zones: list[Polygon], danger_zones: list[Polygon]) -> bool:
        pt = Point(impact_x, impact_y)
        for d_zone in danger_zones:
            if d_zone.contains(pt):
                return False
        for s_zone in safe_zones:
            if s_zone.contains(pt):
                return True
        return False

    @staticmethod
    def evaluate_ci_proximity(target_x: float, target_y: float, ci_assets: list[dict], threshold_m: float = 2500.0):
        """
        Перевірка наближення цілі до об'єктів критичної інфраструктури (ТЕЦ, ГЕС, ПС).
        Повертає: (is_critical, min_distance, nearest_asset_name)
        """
        min_dist = float('inf')
        nearest_ci = None
        for ci in ci_assets:
            dx = target_x - ci["x"]
            dy = target_y - ci["y"]
            dist = math.sqrt(dx**2 + dy**2)
            if dist < min_dist:
                min_dist = dist
                nearest_ci = ci["name"]

        is_critical = min_dist <= threshold_m
        return is_critical, min_dist, nearest_ci