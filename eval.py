"""Evalua el modelo PPO guardado (sin entrenar) y grafica recompensa por episodio."""

from pathlib import Path

import matplotlib.pyplot as plt
from stable_baselines3 import PPO

from src.intersection_env import IntersectionEnv

MODEL_PATH = Path("checkpoints") / "ppo_intersection.zip"
RESULTS_DIR = Path("results")
N_EPISODES = 5


def run_eval(n_episodes: int = N_EPISODES, seed_base: int = 42) -> None:
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"Falta el modelo: {MODEL_PATH} (entrena antes con train.py)")

    env = IntersectionEnv()
    model = PPO.load(str(MODEL_PATH), env=env)

    rewards = []
    for ep in range(n_episodes):
        obs, _ = env.reset(seed=seed_base + ep)
        total_reward = 0.0
        queue_sum = 0.0
        steps = 0
        switches = 0
        done = False
        while not done:
            action, _states = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(int(action))
            total_reward += float(reward)
            queue_sum += float(info["queue_ns"] + info["queue_ew"])
            steps += 1
            if info.get("switched"):
                switches += 1
            done = bool(terminated or truncated)

        avg_queue = queue_sum / max(steps, 1)
        rewards.append(total_reward)
        print(
            f"Episodio {ep + 1}: reward_total={total_reward:.3f}  "
            f"cola_promedio={avg_queue:.3f}  cambios_fase={switches}"
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "reward_por_episodio.png"
    plt.figure(figsize=(6, 4))
    plt.plot(range(1, n_episodes + 1), rewards, marker="o")
    plt.xlabel("Episodio")
    plt.ylabel("Recompensa total")
    plt.title("Evaluacion: recompensa por episodio")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"Grafico guardado en: {out}")


if __name__ == "__main__":
    run_eval()
