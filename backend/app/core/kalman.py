import numpy as np

class DroneKalmanFilter:
    """
    9-state Singer/CWNA: X=[x,y,z,vx,vy,vz,ax,ay,az] ENU.
    F(tau) maneuver time constant, Q from continuous white noise jerk.
    """
    def __init__(self, x: float, y: float, z: float, tau: float = 8.0):
        self.tau = tau
        self.state = np.array([x, y, z, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=float)
        self.P = np.eye(9) * 50.0
        self.P[6:, 6:] *= 2.0
        self.R = np.eye(3) * 20.0
        self.q_var = 1.5
        self.H = np.zeros((3, 9))
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        self.H[2, 2] = 1.0

    def _F(self, dt: float) -> np.ndarray:
        F = np.eye(9)
        tau = self.tau
        a = np.exp(-dt / tau) if tau > 1e-9 else 0.0
        b = tau * (1.0 - a)
        c = tau * dt - tau * tau * (1.0 - a)
        for i in range(3):
            F[i, 3+i] = dt
            F[i, 6+i] = c
            F[3+i, 6+i] = b
            F[6+i, 6+i] = a
        return F

    def predict(self, dt: float):
        F = self._F(dt)
        G = np.zeros((9, 3))
        G[0:3, :] = 0.5 * (dt ** 2) * np.eye(3)
        G[3:6, :] = dt * np.eye(3)
        G[6:9, :] = np.eye(3)
        Q = G @ G.T * self.q_var * max(0.5, dt)
        self.state = F @ self.state
        self.P = F @ self.P @ F.T + Q

    def update(self, z_meas: np.ndarray, R: float | None = None):
        if R is not None:
            Rm = np.eye(3) * R
        else:
            Rm = self.R
        y = z_meas - (self.H @ self.state)
        S = self.H @ self.P @ self.H.T + Rm
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.state = self.state + K @ y
        self.P = (np.eye(9) - K @ self.H) @ self.P

    def extrapolate(self, seconds: float) -> tuple[float, float, float]:
        x = self.state[0] + self.state[3]*seconds + 0.5*self.state[6]*seconds**2
        y = self.state[1] + self.state[4]*seconds + 0.5*self.state[7]*seconds**2
        z = self.state[2] + self.state[5]*seconds + 0.5*self.state[8]*seconds**2
        return x, y, z

    def pos_cov2d(self) -> np.ndarray:
        return self.P[0:2, 0:2].copy()

    def vel(self) -> tuple[float,float,float]:
        return float(self.state[3]), float(self.state[4]), float(self.state[5])
