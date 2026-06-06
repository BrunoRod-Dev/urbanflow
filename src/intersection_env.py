"""Toy env: NS/EW queues, min green, switch cost, variable Poisson arrivals (no SUMO)."""

from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces


class IntersectionEnv(gym.Env):
    """Discrete phase 0=green NS, 1=green EW. Min-green blocks switches; switching costs."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        max_steps: int = 256,
        max_queue: int = 40,
        discharge: int = 3,
        min_green_steps: int = 10,
        switch_penalty: float = 0.35,
        w_queue: float = 1.0,
        w_imbalance: float = 0.35,
        arrival_rate_min: float = 0.35,
        arrival_rate_max: float = 2.2,
        arrival_rate_drift: float = 0.15,
        max_arrivals_per_step: int = 8,
    ):
        super().__init__()
        self.max_steps = max_steps
        self.max_queue = max_queue
        self.discharge = discharge
        self.min_green_steps = min_green_steps
        self.switch_penalty = switch_penalty
        self.w_queue = w_queue
        self.w_imbalance = w_imbalance
        self.arrival_rate_min = arrival_rate_min
        self.arrival_rate_max = arrival_rate_max
        self.arrival_rate_drift = arrival_rate_drift
        self.max_arrivals_per_step = max_arrivals_per_step

        self.action_space = spaces.Discrete(2)
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(5,), dtype=np.float32
        )

        self.queue_ns = 0
        self.queue_ew = 0
        self.phase = 0
        self._t = 0
        self._time_in_phase = 0
        self.arrival_rate = (arrival_rate_min + arrival_rate_max) / 2.0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        self.queue_ns = 0
        self.queue_ew = 0
        self.phase = 0
        self._t = 0
        self._time_in_phase = self.min_green_steps
        self.arrival_rate = float(
            self.np_random.uniform(self.arrival_rate_min, self.arrival_rate_max)
        )
        return self._obs(), {}

    def step(self, action):
        desired = int(action)
        old_phase = self.phase

        # Verde minimo: si aun no cumplimos, el semaforo ignora el pedido de cambio.
        blocked = desired != old_phase and self._time_in_phase < self.min_green_steps
        effective = old_phase if blocked else desired
        switched = effective != old_phase

        self.phase = effective
        if switched:
            self._time_in_phase = 1
        else:
            self._time_in_phase += 1

        if self.phase == 0:
            self.queue_ns = max(0, self.queue_ns - self.discharge)
        else:
            self.queue_ew = max(0, self.queue_ew - self.discharge)

        # Llegadas: intensidad aleatoria con deriva (Poisson por paso, con tope).
        self.arrival_rate += float(
            self.np_random.normal(0.0, self.arrival_rate_drift)
        )
        self.arrival_rate = float(
            np.clip(self.arrival_rate, self.arrival_rate_min, self.arrival_rate_max)
        )
        a_ns = min(
            self.max_arrivals_per_step,
            int(self.np_random.poisson(self.arrival_rate)),
        )
        a_ew = min(
            self.max_arrivals_per_step,
            int(self.np_random.poisson(self.arrival_rate)),
        )
        self.queue_ns = min(self.max_queue, self.queue_ns + a_ns)
        self.queue_ew = min(self.max_queue, self.queue_ew + a_ew)

        # Recompensa: presion por cola total + desbalance NS/EW + coste si hubo cambio de fase.
        total = self.queue_ns + self.queue_ew
        imbalance = abs(self.queue_ns - self.queue_ew)
        reward = -self.w_queue * (total / max(self.max_queue, 1))
        reward -= self.w_imbalance * (imbalance / max(self.max_queue, 1))
        if switched:
            reward -= self.switch_penalty

        self._t += 1
        truncated = self._t >= self.max_steps
        terminated = False

        info = {
            "queue_ns": self.queue_ns,
            "queue_ew": self.queue_ew,
            "switched": switched,
            "blocked_switch": blocked,
            "arrival_rate": self.arrival_rate,
        }
        return self._obs(), float(reward), terminated, truncated, info

    def _obs(self) -> np.ndarray:
        return np.array(
            [
                min(self.queue_ns, self.max_queue) / max(self.max_queue, 1),
                min(self.queue_ew, self.max_queue) / max(self.max_queue, 1),
                float(self.phase),
                min(1.0, self._time_in_phase / max(self.min_green_steps, 1)),
                (self.arrival_rate - self.arrival_rate_min)
                / max(self.arrival_rate_max - self.arrival_rate_min, 1e-6),
            ],
            dtype=np.float32,
        )
