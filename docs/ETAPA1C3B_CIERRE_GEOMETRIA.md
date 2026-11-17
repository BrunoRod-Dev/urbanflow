# UrbanFlow · Etapa 1C.3b · Cierre geométrico del acceso de servicio

**PASS.** La conexión `:2480679873_1_0` dejó de retroceder. El retroceso estático pasó de **2,33 m a 0 m** y los dos sentidos del acceso avanzan en cada tramo. Se conservan las cuatro correcciones de 1C.3, la topología, los programas semafóricos y las velocidades efectivas. No hizo falta una segunda variante. [Comparación](../results/etapa1c3b-sector01/candidato/comparacion.json) · [Red](../results/etapa1c3b-sector01/candidato/a/network.net.xml)

## Corrección

La candidata de 1C.3 se recompiló en una carpeta nueva con los mismos insumos y el mismo `netconvert` 1.26.0. El archivo de nodos copia las cuatro formas ya aceptadas y agrega una forma propia solo para `1957626365`. `2480679873` y `1957626362` no se modifican: en la red compilada conservan posición y contorno, y no quedan marcados como forma propia.

La forma nueva es el polígono del semáforo menos la franja que lo cubría hasta pasar `2480679873`, con el margen de **0,10 m** medido sobre el nodo de servicio. El recorte sigue el eje entre los dos centros y se abre hacia el borde lejano, del lado opuesto a la salida `1346593267#0`. Quedan **19** vértices, un anillo simple, sin huecos ni autointersecciones. El área retirada es de 46,38 m². En la red compilada la separación respecto de `2480679873` es de **0,091 m** y el solape es 0. La diferencia de 9 mm corresponde al redondeo de `--precision.geo 7` que ya usaba 1C.3. Ningún otro cruce aumentó su solape con este nodo. [Muesca](../results/etapa1c3b-sector01/candidato/muesca.json) · [Nodos](../results/etapa1c3b-sector01/candidato/a/geometry.nod.xml)

La segunda pasada restituye las velocidades efectivas de la candidata anterior. La primera compilación había recalculado ocho enlaces internos, entre ellos los cinco ya restituidos en 1C.3 y los dos del acceso. Todos volvieron al valor anterior. No quedó ningún carril con velocidad distinta. Tres conexiones pasan a declarar esa velocidad de forma explícita, con el mismo valor que ya tenía el carril: `5,56` m/s en `:2480679873_1_0`, `4,57` m/s en `:2480679873_0_0` y `5,02` m/s en `:1957626365_0_0`. [Velocidades](../results/etapa1c3b-sector01/candidato/a/speeds.con.xml)

## Comparación con la candidata 1C.3

Coinciden los programas semafóricos, las rotondas, la proyección, los pedidos y conflictos de cada nodo, los permisos y el identificador de cada conexión, incluidos origen, destino, dirección, estado e índice. Las formas de los carriles corregidos en Williman y Bulevar Artigas quedan iguales. Cambian ocho carriles, todos del acceso o de sus enlaces internos:

| Carril | Longitud antes → después | Retroceso estático antes → después |
|---|---:|---:|
| `:2480679873_1_0` | 2,61 → 1,05 m | 2,330 → 0 m |
| `:2480679873_0_0`, sentido contrario | 1,18 → 3,19 m | 0,271 → 0 m |
| `-185203633#2_0` y `185203633#2_0` | 0,20 → 0,10 m | — |
| `:1957626365_0_0` | 7,62 → 7,28 m | 0 → 0 m |
| `:1957626365_1_0` | 18,83 → 15,44 m | 0 → 0 m |
| `:1957626365_2_0` | 15,76 → 12,65 m | 0 → 0 m |
| `230776458_0` | 0,59 → 0,60 m | — |

Los tres enlaces del semáforo se acortan porque su extremo estaba sobre el tramo que el polígono anterior se tragaba. Sus pasos quedan todos hacia adelante y las uniones siguen con separación 0. `1346593267#0` y los dos carriles de `482520536#15` no se mueven. El extremo de `230776458` se desplaza **1 cm**, dentro de la precisión geográfica de la red; la conexión no cambia. Las otras cuatro conexiones que 1C.3 ya había dejado en 0 m siguen en 0 m. No aparece ningún retroceso nuevo de 1 m o más.

## Sondas y demanda

Se reutilizaron las cinco sondas de 1C.3 y se agregó `185203633#1 → 185203633#2 → 1346593267#0` para el sentido contrario. Cada paso se proyecta sobre el mismo rumbo de referencia de la red original.

| Carril interno | Muestras internas antes → después | Menor paso antes → después |
|---|---:|---:|
| Servicio `:2480679873_1_0` | 26 → 11 | −0,089 → **+0,094 m** |
| Sentido contrario `:2480679873_0_0` | sin sonda → 32 | −0,271 m estáticos → **+0,094 m** |
| Bulevar Artigas `:4462688320_0_0` | 2 → 2 | +0,123 → +0,123 m |
| Bulevar Artigas `:4462688320_0_1` | 3 → 3 | +0,071 → +0,071 m |
| Williman `:2535807404_0_0` | 3 → 3 | +0,101 → +0,101 m |
| Williman `:2535807404_0_1` | 3 → 3 | +0,096 → +0,096 m |

Las seis sondas llegan, sin colisiones, teletransportes ni avisos. La demanda original también llega **36 de 36**, con cero colisiones, teletransportes, vehículos pendientes y avisos de ruta. Las dos compilaciones producen las mismas trayectorias, viajes y colisiones.

## Reproducibilidad e integridad

Dos compilaciones independientes generan el mismo árbol XML. Sus SHA-256 de archivo difieren porque el comentario de `netconvert` incluye la hora de generación: `05889e643344613c7af6fd0d354f9bffc5323ab064364f8456edc3e032de4a37` y `daafb8a5d0b04a829b7272b1396748b1b1882db475c5ee406e0c0bcd1e814063`. Sin ese comentario, los archivos son iguales. Los avisos de `netconvert` son los mismos que ya registraba la candidata 1C.3.

Se verificaron **246** huellas antes y después, incluidas las 93 históricas, los 54 artefactos originales del sector, la candidata 1C.3 y los fuentes de `sumo_scenario`, `urbanflow-web` y `src`. No hubo diferencias. [Antes](../results/etapa1c3b-sector01/candidato/integridad-antes.json) · [Después](../results/etapa1c3b-sector01/candidato/integridad-despues.json)

## Repetir

```powershell
$out = 'results/1c3b-' + [guid]::NewGuid().ToString('N')
python -B results/etapa1c3b-sector01/cerrar.py $out
```

El comando recompila dos veces, restituye velocidades, corre la demanda y las seis sondas, y termina con código 0 solo si la compuerta acepta el resultado. Usa una carpeta nueva: no reescribe `results/etapa1c3b-sector01/candidato`.
