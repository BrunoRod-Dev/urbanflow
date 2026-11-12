# Simulador de tránsito (MVP)

Proyecto local en Python para entrenar un agente de aprendizaje por refuerzo que controle un semáforo en una intersección y reduzca tiempo de espera y longitud de cola (en etapas posteriores, con modelos más realistas).

## UrbanFlow web

En Windows, abrí `Abrir UrbanFlow.cmd` con doble clic. Abre UrbanFlow en tu navegador y muestra la dirección local. Dejá esa ventana abierta mientras uses la web. El puerto habitual es 8000. Si está ocupado por un servidor anterior, el lanzador abre la versión actual en el 8765 o indica otro puerto libre. Usá la pestaña nueva o copiá la dirección exacta de la ventana del servidor.

También podés iniciar UrbanFlow desde la carpeta del proyecto:

```powershell
python abrir_urbanflow.py
```

### Generar un estudio desde el mapa

1. Abrí la dirección que imprime la ventana del servidor, normalmente [UrbanFlow en localhost](http://127.0.0.1:8000/).
2. En **Estudios**, elegí **Nuevo estudio**. Buscá una o dos calles o hacé clic cerca de una intersección. Con el teclado, podés centrar el mapa con las flechas y buscar un cruce con Enter.
3. Revisá el nombre del cruce, sus accesos y el contorno azul. Elegí **Guardar estudio**. Podés volver a abrirlo desde **Estudios** antes de simular.
4. Elegí **Simular con tráfico de muestra**. Cuando termine, abrí la corrida con **Reproducir** y usá los controles del visor para seguir a los vehículos.

Los estudios guardados abren con el mapa, el escenario base y las corridas en la misma pantalla. Las reproducciones de demostración se abren desde **Ayuda → Ejemplos**.

### Base vial regional y semáforos

**Ver región** encuadra la zona de trabajo desde Solanas y Punta Ballena, pasando por Maldonado y Punta del Este, hasta La Barra. La búsqueda por calles, la selección en el mapa y la simulación de un cruce confirmado usan el recorte local de OpenStreetMap, con fecha **10 de noviembre de 2026**. El recorte incluye un margen para conservar los accesos y restricciones cerca del borde. El mapa de fondo carga desde OpenFreeMap. [Fuente del recorte](https://download.geofabrik.de/south-america/uruguay.html) · [Atribución y licencia](https://www.openstreetmap.org/copyright)

En las redes nuevas SUMO usa las señales registradas en OpenStreetMap, reconoce las señales marcadas en los accesos y agrupa las muy próximas que pertenecen a cruces compuestos. En Roosevelt y Honduras, los cuatro nodos del cruce pasan a un controlador. SUMO ajusta las fases a la demanda simulada. Los colores en el mapa muestran los estados de cada acceso durante la corrida. Violeta indica que hay giros con estados distintos en el mismo carril. Las fases son estimadas y quedan pendientes los tiempos municipales para calibrar el escenario.

La Intendencia anunció semáforos en ambos lados de la rotonda de la Interbalnearia y Ruta 12 en Solanas. El recorte usado no tiene nodos semafóricos registrados en el entorno inmediato de ese punto. Queda pendiente verificar las ubicaciones y los tiempos antes de representar ese control en SUMO. [Aviso de la Intendencia de Maldonado](https://maldonado.gub.uy/noticias/nuevos-semaforos-estaran-operativos-solanas-roosevelt)

Para aplicar el control coordinado a Roosevelt–Camacho, generá un estudio nuevo desde el mapa. **Guardar y simular** conserva la red y los controles de la corrida que abriste. Para actualizar el recorte regional, descargá el PBF de Uruguay de Geofabrik y, en un entorno con `osmium` instalado, ejecutá `python -m sumo_scenario.build_regional_map ruta/al/uruguay-latest.osm.pbf`.

### Parámetros de un estudio

El generador necesita `sumo` y `netconvert` disponibles en el PATH o en `SUMO_HOME`. También detecta instalaciones estándar de Eclipse SUMO en Windows y el paquete `eclipse-sumo` cuando está instalado en el Python que inicia la web. Se probó con SUMO 1.26. La vista del mapa necesita internet para cargar [OpenFreeMap](https://openfreemap.org/).

El generador busca un cruce vehicular a hasta 55 m del punto y toma un área de aproximadamente 650 × 650 m alrededor de la intersección. Descarga un recorte más grande para dar contexto a los accesos y a la conversión de la red. Conserva la geometría y los controles disponibles en OpenStreetMap. SUMO completa los carriles, velocidades y conexiones con los datos de cada tipo de vía cuando faltan datos. El área puede necesitar revisión si hay cortes, giros, accesos privados o prioridades que el mapa no refleje.

Los cruces confirmados se guardan en `results/projects/`. Las corridas se guardan en `results/studies/` con el recorte, la red, las rutas, la semilla, los resultados y la reproducción. La primera corrida usa **tráfico de muestra** durante cuatro minutos.

Para repetir la prueba, generá Roosevelt–Camacho (`-34.915848, -54.959516`) y luego 18 de Julio–Burnett (`-34.9149968, -54.9585164`). En el primero se puede seguir a los vehículos desde el ramal de la Terminal hasta la rotonda. En el segundo, la red y los recorridos se construyen para la intersección de 18 de Julio y Enrique G. Burnett.

Para probar la entrada desde Camacho sudoeste, generá un estudio nuevo desde el mapa y reproducí desde el inicio a velocidad 1×. Mirá el empalme inmediatamente antes del anillo. El generador aplica una corrección localizada cuando detecta el retroceso conocido y guarda el diagnóstico de conexiones rectas en `network-diagnostics.json`. El informe identifica el cruce, los carriles y la distancia hacia atrás proyectada sobre el sentido de marcha.

Las corridas nuevas exportan la posición longitudinal de cada vehículo y la geometría de los carriles y conexiones internas. La reproducción usa esos datos para seguir las curvas. Los estudios guardados con el formato anterior siguen abriendo con su reproducción original. Para aplicar la corrección de la red a un estudio anterior de Camacho, generá uno nuevo desde el mapa.

### Configurar tráfico y cargar conteos

1. Abrí un estudio generado y elegí **Configurar tráfico** en el panel al lado del mapa. Podés volver a **Resumen** durante la reproducción.
2. Indicá la duración del período observado, entre 1 y 60 minutos. Ingresá el total de vehículos por giro, de un acceso a una salida, y elegí el origen de los datos. La capacidad de esta versión es de 10.000 vehículos por corrida.
3. Para importar un archivo, descargá la plantilla CSV del estudio y completá la columna `vehiculos` en todas las filas. Poné `0` donde no hubo tránsito y conservá los códigos de `movimiento`. Al cargar el CSV la corrida queda identificada como **Conteos observados**.
4. Elegí **Guardar y simular**. UrbanFlow agrega una nueva corrida al estudio con la misma red y los conteos ingresados.

SUMO reparte los conteos durante el período indicado entre los recorridos válidos de cada movimiento. La corrida editada agrega un minuto para que salgan los vehículos que siguen en la red. Para evaluar si reproduce la congestión real, contrastá el resultado con colas y tiempos medidos en la calle.

### Comparar dos corridas

1. Entrá a **Estudios**, abrí el estudio del cruce y elegí **Comparar corridas**. Si el estudio tiene una sola, creá una segunda desde **Configurar tráfico**.
2. Seleccioná las corridas A y B. La tabla muestra el cambio de A a B por acceso. La espera, la cola y los viajes completados se miden hasta el mismo instante en ambas corridas. Los viajes programados corresponden al período cargado en cada corrida.
3. Tocá la hora que figura junto a una cola máxima para abrir la reproducción en ese instante.

La espera es el `waitingTime` de SUMO durante todo el recorrido, promediado entre quienes completaron el viaje dentro de la ventana común. La cola máxima se estima a partir de las muestras de trayectoria en el último tramo de cada acceso. Se toma el carril con mayor longitud de cola, se usan vehículos detenidos a 0,1 m/s o menos y una separación máxima de 8 m para considerar que están en la misma cola. Si se acerca al inicio del tramo, puede seguir aguas arriba. Los estudios guardados se pueden comparar si conservan la misma red y los archivos de demanda, viajes y trayectorias. [Definición de `waitingTime` en SUMO](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html)

### Piloto guardado de Roosevelt y Antonio Camacho

La [corrida de referencia para el visor 3D](docs/piloto-3d-roosevelt-camacho.md) documenta la incorporación desde la Terminal, el cambio de fase en Roosevelt y Honduras y los datos disponibles para construir la escena.

La geometría proviene de un [recorte de OpenStreetMap](https://www.openstreetmap.org/way/100473863), con atribución a sus colaboradores y licencia [ODbL](https://www.openstreetmap.org/copyright). La Junta Departamental identifica el sitio como la [rotonda José Batlle y Ordóñez](https://www.juntamaldonado.gub.uy/index.php/documentos/versiones-taquigraficas/versiones-2009/oct0609).

El modelo conserva los accesos de Roosevelt y Camacho, los sentidos de circulación registrados y la prioridad del anillo. El tramo norte de Camacho se representa como salida. Se recortaron las calles laterales y se modelaron los giros entre los accesos incluidos. Los límites sin dato se completaron con valores de muestra de 45 km/h en Roosevelt, 40 km/h en Camacho y 25 km/h en el anillo. Las rutas y la demanda de 1.800 veh/h son ilustrativas.

Para regenerar la corrida del piloto con `sumo` y `netconvert` en el PATH o con `SUMO_HOME` configurado:

```powershell
python sumo_scenario/export_pilot.py
```

El exportador recompila el recorte y reproduce seis minutos de tráfico con SUMO. Los archivos de origen están en `sumo_scenario/pilot/`.

### Demo semaforizada

La demo incluye recorridos ilustrativos basados en la red y el ciclo del cruce de `sumo_scenario/`. Para reemplazarlos por trayectorias generadas por SUMO, ejecutá el exportador y recargá la página:

```powershell
python sumo_scenario/export_web.py
```

El exportador busca `sumo` en el PATH o en `SUMO_HOME`, ejecuta seis minutos del escenario y actualiza la reproducción web. También admite `--fcd archivo.xml` para importar una corrida del mismo cruce y `--demo` para restaurar los recorridos ilustrativos.

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
