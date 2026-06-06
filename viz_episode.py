"""Un episodio con el modelo cargado: grafico de barras actualizado paso a paso (matplotlib)."""

from pathlib import Path

import matplotlib.pyplot as plt
from stable_baselines3 import PPO

from src.intersection_env import IntersectionEnv

MODEL_PATH = Path("checkpoints") / "ppo_intersection.zip"
PAUSE_S = 0.03


def main() -> None:
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"Falta el modelo: {MODEL_PATH}")

    env = IntersectionEnv()
    model = PPO.load(str(MODEL_PATH), env=env)
    obs, _ = env.reset(seed=0)

    plt.ion()
    fig, ax = plt.subplots(figsize=(7, 4.5))

    def draw(paso: int, ultima_accion: int | None) -> None:
        ax.clear()
        ax.bar(
            ["Cola NS", "Cola EW"],
            [env.queue_ns, env.queue_ew],
            color=["#2a6f97", "#a23b72"],
        )
        ax.set_ylim(0, env.max_queue + 2)
        ax.set_ylabel("Vehiculos")
        fase = "Verde NS" if env.phase == 0 else "Verde EW"
        acc_txt = "-" if ultima_accion is None else str(ultima_accion)
        ax.set_title(
            f"Paso {paso}  |  Fase: {fase}  |  Accion (pedida): {acc_txt}"
        )
        fig.canvas.draw()
        fig.canvas.flush_events()
        plt.pause(PAUSE_S)

    draw(0, None)
    paso = 0
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        a = int(action)
        obs, _r, terminated, truncated, info = env.step(a)
        paso += 1
        draw(paso, a)
        done = bool(terminated or truncated)

    plt.ioff()
    plt.show()
    print(f"Episodio terminado en {paso} pasos.")


if __name__ == "__main__":
    main()
