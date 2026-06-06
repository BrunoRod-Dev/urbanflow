# Simulador de tránsito (MVP)

Proyecto local en Python para entrenar un agente de aprendizaje por refuerzo que controle un semáforo en una intersección y reduzca tiempo de espera y longitud de cola (en etapas posteriores, con modelos más realistas).

## Requisitos

- Python 3.10+ (recomendado)
- Entorno virtual `.venv` con dependencias instaladas según `requirements.txt`

## Comandos

| Comando | Propósito |
|---------|-----------|
| `python main.py` | Comprobación rápida del intérprete (`Base Python OK`). |
| `python train.py` | Entrena PPO sobre el entorno toy y guarda el modelo en `checkpoints/`. |

## Arquitectura mínima

| Pieza | Rol |
|-------|-----|
| `src/intersection_env.py` | Entorno Gymnasium: colas NS/EW, semáforo de dos fases, recompensa por congestión. |
| `train.py` | Crea el vector de entornos, instancia PPO (Stable-Baselines3) y guarda el checkpoint. |
| `main.py` | Punto de entrada mínimo (smoke test), sin lógica de entrenamiento. |

## Estructura de carpetas

```
.
├── main.py
├── train.py
├── requirements.txt
├── README.md
├── .gitignore
├── .vscode/
│   └── settings.json    # Fuerza UTF-8 al guardar en este workspace
├── checkpoints/         # Generado al entrenar (modelo .zip); no versionar
└── src/
    ├── __init__.py
    └── intersection_env.py
```

| Carpeta / archivo | Descripción |
|-------------------|-------------|
| `src/` | Código del entorno Gymnasium y, más adelante, utilidades compartidas. |
| `src/__init__.py` | Declara `src` como paquete para imports estables (`from src...`). |
| `src/intersection_env.py` | Simulación mínima de intersección + API Gymnasium. |
| `train.py` | Script de entrenamiento SB3 invocable con `python train.py`. |
| `main.py` | Entrada mínima de verificación del proyecto. |
| `checkpoints/` | Salida del entrenamiento (creada por `train.py` si no existe). |
| `requirements.txt` | Dependencias versionadas del entorno virtual. |
| `.vscode/settings.json` | Codificación UTF-8 por defecto en este proyecto (evita UTF-16). |

## Próximos pasos posibles

- Evaluación explícita del política y gráficos de cola con `matplotlib`/`pandas`.
- Sustituir la dinámica toy por un modelo más fiel (p. ej. SUMO) manteniendo la misma interfaz Gymnasium.
