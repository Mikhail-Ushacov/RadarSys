import math
from shapely.geometry import Point, Polygon
from app.config import settings

class InterceptionPlanner:
    """
    Планувальник точкового та адаптивного придушення:
    1. Рахує траєкторію балістично-інерційного зриву після глушіння GPS.
    2. Перевіряє безпеку падіння над зеленою, помаранчевою або червоною зоною.
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
        beamwidth = 50.0 - norm_dist * 35.0
        return round(max(14.0, min(60.0, beamwidth)), 1)

    @staticmethod
    def predict_crash_point(x: float, y: float, z: float, vx: float, vy: float, vz: float):
        imp_x, imp_y, t_fall, _, _, _ = InterceptionPlanner.predict_impact_ellipse(x, y, z, vx, vy, vz)
        return imp_x, imp_y, t_fall

    _M = 50.0
    _CD = 1.0
    _A = 1.2
    _RHO = 1.225
    _G = 9.81

    @staticmethod
    def predict_impact_ellipse(x: float, y: float, z: float, vx: float, vy: float, vz: float, P: object = None):
        g = InterceptionPlanner._G
        v_term = math.sqrt(2.0 * InterceptionPlanner._M * g / (InterceptionPlanner._RHO * InterceptionPlanner._CD * InterceptionPlanner._A))
        tau = v_term / g
        current_alt = max(z, 10.0)
        t_fall = tau * math.acosh(math.exp(g * current_alt / v_term ** 2))
        drag = tau * (1.0 - math.exp(-t_fall / tau))
        imp_x = x + vx * drag + settings.WIND_VECTOR_X * t_fall
        imp_y = y + vy * drag + settings.WIND_VECTOR_Y * t_fall
        speed = math.sqrt(vx ** 2 + vy ** 2)
        wind_mag = math.sqrt(settings.WIND_VECTOR_X ** 2 + settings.WIND_VECTOR_Y ** 2)
        if P is not None:
            try:
                import numpy as _np
                cov_xy = _np.array(P[0:2, 0:2], dtype=float)
                cov_v = _np.array(P[3:5, 3:5], dtype=float) if P.shape[0] >= 5 else _np.eye(2)*10
                sigma = cov_xy + (drag**2) * cov_v + _np.eye(2) * (8.0 + 0.05*wind_mag*t_fall)**2
                hdg = math.atan2(vx, vy)
                c, s = math.cos(hdg), math.sin(hdg)
                R = _np.array([[c, s], [-s, c]])
                rot = R @ sigma @ R.T
                sigma_along = float(min(math.sqrt(max(float(rot[0,0]), 1.0)), 1500.0))
                sigma_cross = float(min(math.sqrt(max(float(rot[1,1]), 1.0)), 1500.0))
                sigma_along = max(sigma_along, min(60.0 + 0.04*speed*t_fall, 1500.0))
                sigma_cross = max(sigma_cross, min(40.0 + 0.03*speed*t_fall, 1500.0))
                heading = hdg
                return imp_x, imp_y, t_fall, sigma_along, sigma_cross, heading
            except Exception:
                pass
        sigma_along = min(60.0 + 0.08 * speed * t_fall, 1500.0)
        sigma_cross = min(40.0 + 0.05 * speed * t_fall + 0.1 * wind_mag * t_fall, 1500.0)
        heading = math.atan2(vx, vy)
        return imp_x, imp_y, t_fall, sigma_along, sigma_cross, heading

    @staticmethod
    def is_safe_drop(
        impact_x: float, 
        impact_y: float, 
        safe_zones: list[Polygon], 
        danger_zones: list[Polygon],
        caution_zones: list[Polygon] = None
    ) -> bool:
        pt = Point(impact_x, impact_y)
        # Червоні зони: суворо заборонено
        for d_zone in danger_zones:
            if d_zone.contains(pt):
                return False
        # Помаранчеві зони (буферні): утримання від ураження
        if caution_zones:
            for c_zone in caution_zones:
                if c_zone.contains(pt):
                    return False
        # Зелені зони: дозволено
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