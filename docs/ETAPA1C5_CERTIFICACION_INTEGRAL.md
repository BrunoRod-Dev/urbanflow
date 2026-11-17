# UrbanFlow · Etapa 1C.5 · Certificación integral del Sector 01

**Veredicto: PASS CON OBSERVACIONES.**

La candidata geométrica de 1C.3b, el reproductor compartido de 1C.4 y las herramientas QA representan la misma corrida de 36 autos. Las cinco alertas geométricas originales siguen visibles en el informe de la red sin corregir. La candidata corregida no agrega alertas de geometría, trayectoria, rumbo ni ruta. Los 23 programas semafóricos siguen inferidos. Esta entrega no autoriza el Sector 02: la expansión espera la inspección visual de esta página.

## Qué certifica el procedimiento automático

| Comprobación | Resultado | Evidencia |
| --- | --- | --- |
| Candidata 1C.3b aceptada, dos compilaciones equivalentes y demanda 36/36 | Reutilizada. Separación compilada al nodo de servicio 0,091 m, solape 0, retroceso de `:2480679873_1_0` en 0 | [Comparación 1C.3b](../results/etapa1c3b-sector01/candidato/comparacion.json) |
| Replay de esa corrida, sin volver a ejecutar SUMO | 36 llegadas, replay de 1.084.990 bytes | [Manifiesto](../results/etapa1c5-sector01/candidata/manifest.json) |
| QA de la candidata | 7.594 muestras, 0 colisiones, 0 teletransportes, 0 viajes incompletos | [Informe](../results/etapa1c5-sector01/qa/QA_REPORT.md) |
| Misma pose 2D y 3D sobre la candidata | 7.594 muestras y 144.286 poses intermedias, 0 retrocesos agregados, error 0,0085 m y 0,000006° | [Poses](../results/etapa1c5-sector01/poses.json) |
| La original y los dos ómnibus archivados no se movieron | La sección original y las dos secciones de ómnibus coinciden byte a byte con la medición de 1C.4 | Mismo archivo |
| Cámaras, zoom, seguimiento, cambio de vista y panel QA | Una pasada visible de Chrome, 0 excepciones | [Chrome](../results/etapa1c5-sector01/chrome/chrome-candidata.json) |
| Rendimiento sostenido | Se citan las tres ventanas de cierre de 1C.4. La ventana nueva es un control, no una campaña | [Cierre 1C.4](ETAPA1C4_CORRECCION_3D.md) |

La clave `connection: false` de 1C.3b se mantiene como diferencia de representación: tres enlaces internos pasaron a declarar la velocidad que ya tenían en el carril. Las velocidades efectivas, los programas, las prioridades y las cuatro correcciones de avenida quedaron iguales. El detalle está en [el cierre de 1C.3b](ETAPA1C3B_CIERRE_GEOMETRIA.md).

## Qué queda para la inspección humana

El automatismo mide posiciones, tiempos e identidades. No juzga si un auto se ve centrado en el carril, si un giro se lee como continuo ni si un modelo tapa la calzada. Esos controles están en el procedimiento de esta página.

Tampoco hay validación física de semáforos ni de los permisos de las vías de servicio. El texto de supuestos del replay ya lo declara, y el QA lo repite con procedencia `inferred`.

## Semáforos inferidos y semáforos validados

Los 23 controladores con estados registrados están inferidos por SUMO. El informe los lista uno por uno, incluido `joinedS_1957626365_2480679875_2535807399_2626589240`, que gobierna el cruce del acceso de servicio. La etiqueta de cada uno es «Programa inferido».

Ningún programa de este sector tiene validación física. Una fase verde o roja en el reproductor muestra el estado que guardó la simulación. No muestra un plan contrastado en la calle.

La prioridad sin corroboración física también sigue presente: una alerta `inferred_priority`.

## 1. Candidata geométrica y reproductores

El replay `01c5b202611140000000000000000001` se armó con `make_replay` a partir de los XML ya simulados en `results/etapa1c3b-sector01/candidato/a`. No hubo `netconvert`, ni una segunda demanda, ni sondas nuevas. La ruta `routes.rou.xml` es idéntica a la de la validación original. `map.nod.xml` y `map.edg.xml` son `final.nod.xml` y `final.edg.xml` de esa candidata. El nodo `1957626365` entra con la muesca ya compilada.

La primera apertura 3D respondió 422 porque a la carpeta del replay le faltaba `recorte.osm.xml`. Ese archivo ya estaba en la candidata 1C.3b, con SHA-256 `33d5750cd247cac4301558ad7e7d5eef51a3efac7a0c79d9ca3f3335636736df`. Se copió y la escena de calle respondió 200. El reproductor no se modificó.

`audit_replay_geometry.cjs` aceptó las 7.594 muestras: cada muestra FCD coincide con el auto del replay en longitud, latitud, ángulo, velocidad, carril y posición. Como la candidata ya no tiene alertas `reverse_geometry`, esa auditoría queda con 0 ventanas de conexión. El barrido completo de intervalos está en `poses.json`, no en ese archivo de 0 ventanas.

## 2. La misma pose en 2D y 3D

`compare_replay_3d.cjs` comparó la original de 1C, esta candidata y los replays archivados de Camacho y Honduras. El código de referencia es el `lane-motion.js` anterior y el cálculo de chasis retirado.

En la candidata, 2D y 3D entregan la misma pose base. El error geográfico máximo es 0,0085 m en centro y frente, y 0,000006° de yaw. Los umbrales siguen en 0,10 m y 1°. Hay 0 muestras por encima de 0,5 m y 0 por encima de 5°. El cálculo retirado, sobre esta misma geometría, todavía llega a 3,284 m de centro y 82,49° de yaw.

La original permanece en 7.430 muestras y 141.170 poses intermedias, con los mismos errores y 0 retrocesos agregados que en 1C.4. `mansa-1` entre 110,5 y 111 s avanza 1,966 m sobre el centro registrado y la misma distancia sobre la proyección. En 110,5 s va por `482520536#12_0`.

Chrome, en la candidata, comparó los autos dibujados en 3D y en 2D en 110,5, 110,75, 111, 202, 202,25 y 202,5 s. En los seis instantes el tiempo y la lista de poses coinciden. En cada uno hay 10 vehículos.

## 3. Cámaras, zoom, seguimiento y alertas

La pasada usa el script ya existente, Chrome 157 visible, Intel UHD Graphics, canvas 1.205 × 482 y escala 1,25. Inicialización 3D: 1.112 ms. Excepciones de runtime: ninguna.

Quedó comprobado en esa pasada:

- encuadre del sector en vista elevada;
- selección de `mansa-1`, cámara de calle y un paso de zoom;
- el botón de calle queda presionado;
- al volver al mapa y otra vez a 3D se conservan el vehículo elegido y el tiempo;
- a tiempo 0, con el vehículo todavía inactivo, el panel dice «El vehículo seleccionado no está activo en este instante.»;
- ubicar y saltar llevan a la primera alerta con tiempo, permanecen en 3D y el reloj se mueve. Esa alerta es la detención de `mansa-2` a los 185 s en `482520536#8_0`, 34,5 s detenido;
- la capa de autos se apaga y se vuelve a encender;
- el modo de muestras FCD sin interpolar se activa y se desactiva.

Al elegir `mansa-1` en 110,75 s el panel informa «8 vehículos activos fuera del encuadre 3D.» Es el aviso de cobertura de la cámara de calle, con el seguimiento ya tomado.

## 4. Carriles, giros y ómnibus

La demanda del Sector 01 tiene un solo tipo, `car`, longitud 5 m. Los 36 vehículos son autos. No hay un ómnibus que seguir en este sector.

El giro que antes aparecía como un salto de 106° a 149° en un paso de 0,5 s ahora queda repartido. El mayor paso que permanece, medido en el FCD de la candidata, es 39,12°:

| Vehículo | Intervalo | Carriles | Paso de rumbo |
| --- | --- | --- | --- |
| `salida-servicio-1` | 185,0–185,5 s | `:1957626365_2_0` → `-185203633#1_0` | 34,18° |
| `salida-servicio-1` | 185,5–186,0 s | `-185203633#1_0` | 27,97° |
| `salida-servicio-2` | 306,5–307,0 s | `-185203633#2_0` → `-185203633#1_0` | 39,12° |
| `salida-servicio-2` | 307,0–307,5 s | `-185203633#1_0` | 24,02° |
| `salida-servicio-3` | 385,5–386,0 s | `-185203633#1_0` | 38,34° |

El umbral de alerta es 75°. Esos pasos quedan debajo y el informe ya no emite `heading_change` para esos tres autos. La secuencia de `salida-servicio-1` entre 183,5 y 186,5 s es 352,93°, 355,98°, 3,04°, 14,56°, 48,74°, 76,71° y 77,70°, con velocidad de paso entre 5,53 y 11,06 m/s. El sentido del avance se conserva.

`entrada-servicio-2` recorre el sentido opuesto entre 180 y 195 s, por `185203633` y `:2480679873`, sin un paso de rumbo de 20° o más.

La pose rígida del ómnibus se volvió a calcular con los mismos estudios archivados y coincidió con 1C.4: Camacho, 337 muestras, 0,0146 m; Honduras, 210 muestras, 0,0094 m. La distancia entre ejes de referencia sigue en 3,91132 m. La huella de los neumáticos y la lectura visual del modelo de ómnibus siguen fuera de esta medición, y este sector no ofrece un ómnibus para mirarlas.

## 5. Alertas que se conservan y alertas que se cierran

El informe original, empaquetado en la raíz del ZIP, conserva el recuento de la red sin la muesca: 5 `reverse_geometry`, 10 `trajectory_reverse_projection`, 3 `heading_change`, 6 `prolonged_stop`, 23 `inferred_signal` y 1 `inferred_priority`. Ahí siguen `:2480679873_1_0` y las cuatro avenidas.

La candidata de 1C.3, anterior a la muesca, tenía 36 eventos. La candidata de 1C.3b tiene 30. Los seis que faltan son exactamente el retroceso estático de `:2480679873_1_0`, las dos proyecciones de `salida-servicio-1` a los 202 s y `salida-servicio-3` a los 367 s, y los tres cambios de rumbo de 106° a 149° que ese retroceso producía. No aparece ningún tipo nuevo ni ningún evento con otro vehículo, tiempo o carril.

Las seis detenciones prolongadas quedan en el mismo vehículo, segundo y carril: `peninsula-carril-1-1` 88,5 s, `miami-entre-calzadas-1` 96,5 s, `mansa-2` 185 s, `salida-servicio-2` 250,5 s, `salida-pirineos-2` 247,5 s y `salida-miami-3` 305,5 s. Las cuatro últimas comparten `482520536#8_0`.

## 6. Rendimiento

La certificación de cadencia sigue siendo el cierre de 1C.4, con el código final y visibilidad registrada. Tres ventanas de unos 62 s, sin intervalos por encima de 250 ms: p95 de 7,8, 7,8 y 7,7 ms, y máximos de 13,1, 53,0 y 15,2 ms.

La ventana de esta etapa dura 62,0 s sobre la candidata corregida, con visibilidad `visible` y ningún cambio de visibilidad. Intervalo p50 6,9 ms, p95 7,1 ms, máximo 8,4 ms. CPU de dibujo p95 0,6 ms, máximo 1,8 ms. Vehículos activos p95 11. Intervalos por encima de 250 ms: 0. Frames registrados: 8.931. Sirve como control de esta geometría. No reemplaza las tres ventanas anteriores.

Siguen en la evidencia de 1C.4, sin repetirse, el máximo exploratorio de 307,5 ms y la interrupción de 9.802,8 ms cuya causa quedó indeterminada. El tiempo de GPU sigue sin instrumentar.

## 7. Inspección manual

Ejecutá los comandos desde la raíz del repositorio. Cada servidor elige un puerto libre e imprime la URL. Cerrá el servidor con Ctrl+C antes de abrir el otro, para mirar una corrida por vez. El panel QA se abre con `?qa=1`, que la herramienta ya incluye.

### Red original, para comprobar que las alertas siguen a la vista

```text
python -B tools/open_replay_qa.py results/etapa1c-sector01-validacion/manifest.json results/etapa1c4-sector01-3d/qa-original-final results/etapa1c-sector01-validacion/sector01.geojson
```

1. En el selector de alertas, confirmá que existen «Retroceso en la geometría de un carril interno» para `:2480679873_1_0` y las alertas de las cuatro avenidas. Tienen que ser cinco alertas de geometría.
2. Elegí la de `:2480679873_1_0`, pulsá Ubicar y después Ir al instante. El mapa tiene que mostrar el tramo de servicio, no una lista vacía.
3. Buscá `salida-servicio-1` y andá a 202 s y a 202,5 s. El FCD de esa red gira 110,19° en ese paso. Es el archivo histórico. En la candidata ese instante ya no es el cruce del servicio.

### Candidata corregida

```text
python -B tools/open_replay_qa.py results/etapa1c5-sector01/candidata/manifest.json results/etapa1c5-sector01/qa results/etapa1c5-sector01/candidata/sector01.geojson
```

4. El selector debe listar 23 programas inferidos, 1 prioridad inferida y 6 detenciones. No debe listar retroceso de geometría, retroceso de trayectoria ni cambio brusco de orientación.
5. Elegí la detención de `mansa-2` a los 185 s. Ubicar e Ir al instante tienen que dejar la vista 3D activa y el reloj en 185 s. Mirá si el auto está detenido sobre `482520536#8_0` y si el modelo apoya dentro del carril.
6. Encuadre del sector. Pasá a 110,75 s, elegí `mansa-1` y activá el seguimiento. Cambiá a cámara de calle y acercá con el zoom. Anotá si el auto queda sobre el carril en la curva de Williman, en 110,5 s y en 111 s.
7. Volvé al mapa 2D y regresá a 3D. El vehículo elegido y el tiempo tienen que mantenerse. Compará el auto del mapa con el modelo: misma posición relativa al eje y mismo sentido.
8. Seguí `salida-servicio-1` desde 183,5 s hasta 186,5 s, en cámara de calle y también en vista elevada. El rumbo tiene que recorrer 352,93° → 77,70° en varios pasos, con el mayor en 34,18°. El auto tiene que entrar a `-185203633#1_0` hacia adelante. Activá «Muestras FCD sin interpolar» y comprobá que el marcador crudo y el modelo describen el mismo avance.
9. Repetí el paso con `salida-servicio-2` entre 306,5 y 307,5 s. Es el mayor giro que queda: 39,12° y después 24,02°. Después `salida-servicio-3` entre 385,5 y 386,5 s, con 38,34°.
10. Seguí `entrada-servicio-2` entre 180 y 195 s. Es el sentido opuesto del mismo servicio. El auto tiene que avanzar por `185203633` y por `:2480679873` sin un salto de rumbo ni un retroceso visible.
11. Apagá y encendé la capa de autos en las dos vistas. Los demás vehículos tienen que desaparecer y volver; la selección de `entrada-servicio-2` se mantiene.
12. Abrí cualquiera de los 23 programas en el selector. La etiqueta dice «Programa inferido». Mirá el cruce, y dejá asentado que el color de la señal es el estado simulado. No es un plan medido en campo.
13. No busques un ómnibus en este sector. Los 36 vehículos son autos. La pose del modelo rígido de ómnibus quedó medida en Camacho y Honduras; su apariencia sobre el pavimento no forma parte de los controles de esta corrida.

Si un auto se sale del carril, el giro se ve como un salto o una alerta original deja de aparecer en la red histórica, la certificación queda observada y el Sector 02 sigue detenido.

## Paquete portátil

`results/etapa1c5-sector01/urbanflow-sector01-qa-1c5.zip`

SHA-256 `207eb3f144d030377fda49029dddca7539df92d0194cd6380e40d2037f779b4f`. 41 miembros, 40 huellas de contenido verificadas y `testzip` limpio. La copia de este documento dentro del ZIP es la que se selló con esa huella; esta línea se agregó después, en la copia de trabajo.

La raíz es el estudio original y su QA final, para que las cinco alertas geométricas viajen con el paquete. Bajo `review/` va solo la evidencia de esta etapa: el informe, el QA de la candidata, las poses, la auditoría del reproductor, el manifiesto, el replay, el GeoJSON, el recorte OSM y el control de Chrome. Las trayectorias, los registros de SUMO y la red compilada quedan en el repositorio: sus comentarios contienen la ruta local de la máquina y el empaquetador los rechaza a propósito.

## Qué se reutilizó

Se reutilizaron la comparación y los XML de 1C.3b, el generador `make_replay`, el QA, la auditoría de geometría del reproductor, la comparación 2D/3D, el control de Chrome y el empaquetador con `--extra`. Las tres ventanas de rendimiento del cierre de 1C.4 se citan y no se repitieron. No se repitieron la demanda, las sondas, `netconvert`, las suites históricas ni la auditoría general de hashes.

Lo que sí se ejecutó para esta puerta: el empaquetado del replay, el QA de la candidata, la comparación de poses y una ventana de Chrome sobre el conjunto de alertas nuevo.
