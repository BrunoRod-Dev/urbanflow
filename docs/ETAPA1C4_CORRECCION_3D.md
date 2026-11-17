# UrbanFlow · Etapa 1C.4 · Corrección del reproductor 3D

La implementación comparte la pose y el reloj de 2D y 3D. La revisión manual del Sector 01 y la corrección geométrica de servicio siguen pendientes para la puerta conjunta de calidad. El Sector 02 queda fuera de esta entrega. [Auditoría de origen](AUDITORIA_REPRODUCTOR_3D.md) · [Geometría de 1C.3](ETAPA1C3_GEOMETRIA_SECTOR01.md)

## Movimiento y medición

`app.js` llama a una única interpolación para cada instante del reloj. `lane-motion.js` reconstruye el centro desde el frente, la longitud y el rumbo FCD en las muestras. Entre muestras, interpola el rumbo por el arco más corto y usa la forma del carril sólo para la desviación lateral acotada. Se retiró el camino anterior que reemplazaba el rumbo con la tangente del carril y trasladaba el centro hasta media longitud hacia el lado equivocado. La escena proyecta el mismo centro al plano local, convierte rumbo a yaw, invierte el signo del eje norte en Three.js y dibuja la malla a la altura del pavimento.

Se compararon **7.430 muestras y 141.170 poses intermedias por corrida**, usando la original de 1C y la candidata 1C.3 con la misma demanda. La candidata se empaquetó desde los XML guardados. Cada pose base de 2D y 3D coincidió exactamente. La verificación independiente en el plano SUMO proyectó el frente FCD y reconstruyó centro y yaw en metros. La aproximación geográfica usada por el anclaje deja un error máximo de **0,0085 m** tanto en el centro como en el frente y de **0,000007°** en rumbo para las dos corridas. Los umbrales de aceptación son 0,10 m y 1°. El máximo anterior del centro era de 5,00 m y el del rumbo de 178,00° en la original. Las 97 muestras que excedían 0,5 m y las 195 que excedían 5° bajaron a cero. En la candidata bajaron de 87 y 187 a cero. [Comparación y poses de regresión](../results/etapa1c4-sector01-3d/poses.json)

- **`mansa-1`, 110,5–111 s.** En el eje de Williman, el 3D pasa de −3,190 m a **+1,805 m**, igual que el centro FCD. La mayor variación de rumbo entre subdivisiones de 25 ms queda en 0,040°.
- **`salida-servicio-1`, 202–202,5 s.** En el eje de servicio, el 3D pasa de −2,428 m a **+4,264 m**, igual que el centro FCD. El giro de 110,19° figura en el propio FCD. La interpolación lo reparte en pasos de hasta 5,510° por 25 ms.
- **Retrocesos del reproductor.** Los diez casos de la auditoría original bajan a cero sobre los ejes de las conexiones. Con el criterio adicional que proyecta cada intervalo sobre el eje entre sus dos centros FCD, aparecen 23 casos anteriores en la original y seis en la candidata. Después del cambio se detectan cero en ambas. Los dos conteos anteriores responden a ejes y universos distintos. [Medición por conexión de la original](../results/etapa1c4-sector01-3d/geometria-original.json) · [Medición de la candidata](../results/etapa1c4-sector01-3d/geometria-candidata.json)

El QA de la original conserva cinco anomalías geométricas y diez retrocesos proyectados en las muestras de SUMO. En la candidata queda el retroceso estático de **2,33 m** en `:2480679873_1_0` y dos alertas de trayectoria. Ambas corridas guardadas registran 36/36 viajes terminados, cero colisiones y cero teletransportes. Los 23 controladores siguen marcados como inferidos. [QA original](../results/etapa1c4-sector01-3d/qa-original-final/QA_REPORT.md) · [QA candidata](../results/etapa1c4-sector01-3d/qa-candidata-final/QA_REPORT.md)

## Ómnibus

Se ensayaron **337 muestras de Camacho y 210 de Honduras**, con el ómnibus archivado de 8,54 m. El modelo GLB contiene una sola malla rígida. El cálculo anterior estimaba una segunda pose a partir de un recorrido reconstruido y la aplicaba a toda la malla, incluidos ambos ejes. Se probó también alimentar ese mismo cálculo con la interpolación compartida. Todavía produjo hasta **2,089 m de error del frente y 10,66° de yaw** en Camacho y **0,560 m y 5,15°** en Honduras. Así se aisló el efecto del ajuste del chasis respecto de la interpolación antigua.

La escena usa la pose compartida para mover el chasis rígido. Conserva las dimensiones del modelo y la distancia de **3,91132 m** entre los puntos de ejes de referencia. Se midió un error máximo en centro y frente de **0,0146 m** en Camacho y **0,0094 m** en Honduras, y menos de **0,000011°** de rumbo. Esta decisión prioriza la pose que registró SUMO y elimina el salto entre el chasis estimado y su respaldo. El ajuste anterior queda en la evidencia para repetir la comparación. El ensayo mide la pose de un modelo rígido y su distancia entre ejes. La huella de los neumáticos, el barrido físico de los ejes sobre el pavimento y la perspectiva del ómnibus en la revisión manual siguen fuera de esa medición. [Comparación del ómnibus](../results/etapa1c4-sector01-3d/poses.json) · [Cálculo previo](../results/etapa1c4-sector01-3d/vehicle-path-before.mjs)

## Cámara, reloj y QA

- **Encuadrar sector** ajusta la vista elevada al tamaño del corredor y al aspecto del canvas. **Nivel de calle**, zoom, giro y restablecimiento usan la cámara existente. En seguimiento, 3D conserva el desplazamiento de cámara respecto al objetivo mientras el vehículo se mueve.
- El selector QA busca el ID de SUMO, centra el auto y lo resalta en 3D. Al alternar se conserva la selección, el tiempo y el centro de inspección disponible. Cada vista mantiene su propio zoom. El panel avisa si el vehículo seleccionado está fuera de su intervalo de actividad o si hay vehículos activos fuera del encuadre 3D.
- **Ubicar** enfoca la coordenada registrada sin abandonar la vista activa. **Ir al instante** pausa y usa el tiempo de la alerta. Las alertas sin tiempo sólo se pueden ubicar. Las capas permiten alternar vías, conexiones, señales y vehículos en ambas vistas. Los marcadores QA de señal en 3D indican ubicación. Para inspeccionar el estado registrado de todos los controladores usá el mapa 2D.
- En sectores genéricos la cobertura del terreno se amplía hasta abarcar las muestras FCD, con margen. Se retiró el filtro que descartaba vehículos al salir del rectángulo anterior. Ese rectángulo dejaba afuera 128 poses de la original y 129 de la candidata. El conteo de fuera de cuadro usa la proyección del centro a la cámara, con independencia del estado de circulación.
- **Muestras FCD sin interpolar** conserva la evidencia registrada. En el mapa el modo crudo muestra el frente FCD. En 3D el modelo centrado muestra esa misma muestra desplazada media longitud hacia atrás según el rumbo registrado.

## Chrome visible y rendimiento

En Chrome 157 para Windows, con Intel UHD Graphics, 16 hilos lógicos y canvas de 1.205 × 482 píxeles, se probaron el encuadre, la cámara de calle, el zoom, el seguimiento, las capas, la localización y el salto a **185 s** sin salir de 3D. Se cotejaron seis instantes alrededor de las dos transiciones críticas y se confirmó el mismo tiempo y la misma pose al cambiar de vista. El seguimiento y la selección permanecieron activos en el cambio. [Captura aérea original](../results/etapa1c4-sector01-3d/chrome-verificado/original-aerea.png) · [Seguimiento en la candidata](../results/etapa1c4-sector01-3d/chrome-candidata/candidata-seguimiento.png)

Cada ventana sostenida duró aproximadamente 62 s a velocidad 1×, con hasta 11 autos activos y diez segundos de calentamiento. La primera pareja de mediciones sostenidas arrojó, para la original y la candidata respectivamente, **7,7 y 7,6 ms** de intervalo p95, **1,2 y 1,1 ms** de CPU p95 dentro del dibujo y **13,3 y 19,3 ms** de intervalo máximo. La inicialización del 3D desde el clic tardó **2,49 y 2,60 s**. Los intervalos de cuadro miden la cadencia observada del reproductor. El tiempo de dibujo incluye preparación y envío de comandos WebGL en CPU. El informe de Chrome también registra tiempo acumulado de tareas, scripts y layout. La duración de ejecución en GPU se mantiene sin instrumentar. [Original](../results/etapa1c4-sector01-3d/chrome-final/chrome-original.json) · [Candidata](../results/etapa1c4-sector01-3d/chrome-final/chrome-candidata.json)

La pasada exploratoria sin calentamiento registró **307,5 ms** de intervalo máximo. Una repetición posterior de la original, que instrumentó las dos entradas reales a los visores, conservó 7,7 ms p95 y 1,0 ms de CPU p95 pero registró una interrupción de **9.802,8 ms**. El dibujo individual más largo de esa ventana fue de 5,6 ms. Otra sesión encontró el mapa 2D en estado de error de carga y se reintentó con el control existente. Los ensayos favorables y las interrupciones se mantienen en evidencia. [Primera pasada](../results/etapa1c4-sector01-3d/chrome-original.json) · [Repetición original](../results/etapa1c4-sector01-3d/chrome-verificado/chrome-original.json)

El cierre usó el código final y el script que además registra cada cambio de visibilidad de la página. Se midieron tres ventanas sostenidas de 62 s: la original, la candidata y una repetición de la original. Ninguna registró intervalos por encima de 250 ms, cambios de visibilidad ni excepciones. Los intervalos p95 fueron **7,8, 7,8 y 7,7 ms** y los máximos **13,1, 53,0 y 15,2 ms**. La CPU de dibujo p95 se mantuvo entre **1,1 y 1,6 ms** y la inicialización del 3D entre **3,18 y 3,51 s**. Una ventana previa de la candidata con este mismo script dio 7,5 ms p95 y 44,2 ms de máximo. Con este cierre, el criterio de ninguna pausa por encima de 250 ms se cumple en las cuatro ventanas medidas con el código final y el registro de visibilidad. La interrupción de 9.802,8 ms no se reprodujo y su causa sigue indeterminada. Esa ventana no registraba la visibilidad. [Cierre original](../results/etapa1c4-sector01-3d/cierre/chrome-original.json) · [Cierre candidata](../results/etapa1c4-sector01-3d/cierre/chrome-candidata.json) · [Repetición original](../results/etapa1c4-sector01-3d/cierre/repeticion/chrome-original.json) · [Candidata previa](../results/etapa1c4-sector01-3d/chrome-candidata/chrome-candidata.json)

## Pruebas y archivos

- Reproductor y controles QA en Node, **9 aprobadas**. QA Python, **4 aprobadas**. Contrato de compilador 1A, **11 aprobadas**. Baseline estricta, **9 aprobadas**. Total **33**, sin fallos ni omisiones. [Logs](../results/etapa1c4-sector01-3d/regresiones/)
- Después de esos logs cambiaron `app.js`, `replay-views.js` y `maldonado.js`. Se repitieron las 9 pruebas de Node con el código final y volvieron a aprobar. El comparador, que toma `interpolate` de `app.js`, se volvió a correr y produjo un `poses.json` idéntico al anterior, con sus aserciones de error y retrocesos aprobadas. QA Python, compilador y baseline dependen de archivos sin cambios desde sus logs y no se repitieron. [Reproductor final](../results/etapa1c4-sector01-3d/cierre/reproductor.log) · [Poses finales](../results/etapa1c4-sector01-3d/cierre/poses.json)
- Se verificaron los nombres y SHA-256 de **93 archivos históricos** contra el inventario certificado, **54 artefactos de la corrida original** contra su manifiesto y **11 archivos fuente de la candidata** usados para preparar el replay. También coincidieron las **16 huellas** de ese replay nuevo con su manifiesto. Las redes, demanda, programas y trayectorias de origen se reutilizaron sin ejecutar SUMO. Al cierre se repitió la verificación completa con el mismo resultado y se registraron las huellas de los cuatro replays comparados. [Integridad](../results/etapa1c4-sector01-3d/integridad.json) · [Integridad al cierre](../results/etapa1c4-sector01-3d/cierre/integridad.json) · [Manifiesto de la candidata](../results/etapa1c4-sector01-3d/candidata/manifest.json)
- `app.js` y `lane-motion.js` unifican el cálculo. `scene-coordinates.js` y `vehicle-models.js` convierten y dibujan la pose. `vehicle-path.js` se retiró tras la prueba comparativa. `viewer3d.js`, `replay-views.js`, `replay-qa.js`, `maldonado.js` e `index.html` conectan cámara, capas, estado y continuidad entre vistas. Las pruebas de Node quedaron en `test_lane_motion.cjs` y `test_replay_qa_controls.cjs`. Las herramientas de evidencia son `prepare_sector01_replay.py`, `compare_replay_3d.cjs` y `check_sector01_chrome.py`. `package_replay_qa.py` acepta `--extra` para sumar archivos de revisión bajo `review/` con la misma verificación de rutas y huellas.

## Prueba manual en Chrome

Desde PowerShell, en la raíz de UrbanFlow, abrí una corrida a la vez. El lanzador imprime la URL local de QA. Si se abre en otro navegador, pegala en Chrome.

```powershell
$ev = 'results/etapa1c4-sector01-3d'
python -B tools/open_replay_qa.py results/etapa1c-sector01-validacion/manifest.json "$ev/qa-original-final" results/etapa1c-sector01-validacion/sector01.geojson
# Cerrá el servidor con Ctrl+C antes de abrir la candidata.
python -B tools/open_replay_qa.py "$ev/candidata/manifest.json" "$ev/qa-candidata-final" "$ev/candidata/sector01.geojson"
```

1. En **Vista 3D**, presioná **Encuadrar sector**. Revisá que se vea el corredor completo y probá acercar, alejar y girar.
2. En la corrida original, seleccioná la alerta FCD de `mansa-1` alrededor de 111 s y usá **Ir al instante**. Volvé a seleccionar el vehículo para seguirlo. Alterná **Mapa 2D** y **Vista 3D** con la corrida pausada y luego en reproducción.
3. Hacé lo mismo con `salida-servicio-1` alrededor de 202,5 s. Activá **Muestras FCD sin interpolar** para distinguir el giro registrado de la animación entre cuadros. En ambas corridas la alerta de servicio debe seguir disponible.
4. Alterná a **Nivel de calle**, comprobá la alineación del centro con el carril al cruzar y observá que el contador de vehículos fuera del encuadre cambia al abrir o cerrar la cámara.

### Repetir la regresión numérica y de navegador

```powershell
$ev = 'results/etapa1c4-sector01-3d'
$original = 'results/etapa1c-sector01-validacion'
$id = (Get-Content "$original/manifest.json" -Raw | ConvertFrom-Json).replayId
$cid = (Get-Content "$ev/candidata/manifest.json" -Raw | ConvertFrom-Json).replayId
$out = (New-Item -ItemType Directory ('results/1c4-revision-' + [guid]::NewGuid().ToString('N'))).FullName
node tools/compare_replay_3d.cjs "$original/$id/replay.json" "$ev/candidata/$cid/replay.json" results/etapa1c2-sector01/lane-motion-before.js "$ev/vehicle-path-before.mjs" results/studies/1326984e1af04135a05c1d17adab271b/replay.json results/studies/bceb3ad9e5bf40408d95652f9595084a/replay.json "$out/poses.json"
python -B tools/check_sector01_chrome.py "$original/manifest.json" "$ev/qa-original-final" $out
python -B tools/check_sector01_chrome.py "$ev/candidata/manifest.json" "$ev/qa-candidata-final" $out --candidate
```

El [ZIP QA portátil](../results/etapa1c4-sector01-3d/urbanflow-sector01-qa-1c4.zip) reúne el informe, comparaciones, capturas, alertas, casos de regresión, resultados de Chrome y un manifiesto de huellas por archivo. La raíz contiene el QA y la evidencia de la original. Este documento, la evidencia 1C.4 y las herramientas quedan bajo `review/` con sus rutas relativas.

```powershell
$ev = 'results/etapa1c4-sector01-3d'
$extra = 'docs/ETAPA1C4_CORRECCION_3D.md', 'docs/AUDITORIA_REPRODUCTOR_3D.md', "$ev/poses.json", "$ev/geometria-original.json",
  "$ev/geometria-candidata.json", "$ev/integridad.json", "$ev/vehicle-path-before.mjs", "$ev/candidata/manifest.json",
  "$ev/chrome-original.json", "$ev/original-aerea.png", "$ev/original-seguimiento.png", "$ev/qa-candidata-final",
  "$ev/regresiones", "$ev/chrome-final", "$ev/chrome-verificado", "$ev/chrome-candidata", "$ev/chrome-entrega", "$ev/cierre",
  'tools/compare_replay_3d.cjs', 'tools/check_sector01_chrome.py', 'tools/prepare_sector01_replay.py',
  'tests/test_lane_motion.cjs', 'tests/test_replay_qa_controls.cjs'
python -B tools/package_replay_qa.py results/etapa1c-sector01-validacion "$ev/qa-original-final" "$ev/urbanflow-sector01-qa-1c4.zip" ($extra | ForEach-Object { '--extra'; $_ })
```

## Estado de la entrega

La etapa queda en **PASS CON OBSERVACIONES**. La paridad de pose con FCD, la eliminación de retrocesos añadidos, el ómnibus rígido, los controles QA y la ventana sostenida de Chrome cumplen sus criterios con el código final. Siguen abiertos el retroceso estático de 2,33 m en `:2480679873_1_0`, visible en el QA de la candidata, y la revisión visual humana del Sector 01. También quedan abiertas la causa de la interrupción de 9.802,8 ms, la duración en GPU y la huella física de los neumáticos del ómnibus. Los 23 controladores siguen inferidos.
