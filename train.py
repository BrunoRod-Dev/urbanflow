"""
Entrenamiento mínimo con Stable-Baselines3 (PPO) sobre IntersectionEnv.
Ejecutar desde la raíz del proyecto: python train.py
"""

from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env

from src.intersection_env import IntersectionEnv


def run_training(total_timesteps: int = 25_000, n_envs: int = 4) -> Path:
    # Varios entornos en paralelo acelera el muestreo para PPO.
    env = make_vec_env(
        lambda: IntersectionEnv(),
        n_envs=n_envs,
    )

    model = PPO(
        "MlpPolicy",
        env,
        verbose=1,
        learning_rate=3e-4,
        n_steps=128,
        batch_size=64,
        n_epochs=4,
        seed=0,
    )
    model.learn(total_timesteps=total_timesteps)

    out_dir = Path("checkpoints")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / "ppo_intersection"
    model.save(str(path))
    return path


if __name__ == "__main__":
    saved = run_training()
    print(f"Modelo guardado en: {saved}.zip")
