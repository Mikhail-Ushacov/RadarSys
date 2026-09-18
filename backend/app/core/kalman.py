import numpy as np

class DroneKalmanFilter:
    """
    3D Лінійний фільтр Калмана з постійною моделлю швидкості (Constant Velocity).
    Вектор стану X = [x, y, z, vx, vy, vz]^T у системі ENU (метри та м/с).
    """
    def __init__(self, x: float, y: float, z: float):
        self.state = np.array([x, y, z, 0.0, 0.0, 0.0], dtype=float)
        self.P = np.eye(6) * 50.0  # Невизначеність коваріації
        
        # Матриця шуму вимірювань (довіра сенсорам: акустика ~30м, оптика ~5м)
        self.R = np.eye(3) * 20.0
        
        # Матриця шуму процесу (маневреність цілі)
        self.q_var = 1.5
        
        # Матриця вимірювань H: зчитуємо лише позицію [x, y, z]
        self.H = np.zeros((3, 6))
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        self.H[2, 2] = 1.0

    def predict(self, dt: float):
        F = np.eye(6)
        F[0, 3] = dt
        F[1, 4] = dt
        F[2, 5] = dt
        
        # Дискретний шум процесу Q
        G = np.zeros((6, 3))
        G[0:3, :] = 0.5 * (dt ** 2) * np.eye(3)
        G[3:6, :] = dt * np.eye(3)
        Q = G @ G.T * self.q_var
        
        self.state = F @ self.state
        self.P = F @ self.P @ F.T + Q

    def update(self, z_meas: np.ndarray):
        y = z_meas - (self.H @ self.state)  # Інновація
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)  # Коефіцієнт Калмана
        
        self.state = self.state + K @ y
        self.P = (np.eye(6) - K @ self.H) @ self.P

    def extrapolate(self, seconds: float) -> tuple[float, float, float]:
        """Екстраполяція вектора руху без зміни коваріації."""
        x = self.state[0] + self.state[3] * seconds
        y = self.state[1] + self.state[4] * seconds
        z = self.state[2] + self.state[5] * seconds
        return x, y, z