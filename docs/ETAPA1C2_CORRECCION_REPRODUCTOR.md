# UrbanFlow · Etapa 1C.2 · Corrección del reproductor 2D

El reproductor 2D usa la posición y el rumbo registrados por SUMO en ambos extremos de cada intervalo. En los **20 intervalos auditados** de Punta del Este–Mansa, los retrocesos añadidos por el reproductor bajaron de **10 a 0**. El informe QA conserva las cinco alertas de geometría, los diez desplazamientos hacia atrás registrados en las trayectorias y la evidencia del reproductor anterior. [Informe QA actualizado](../results/etapa1c2-sector01/qa/QA_REPORT.md) · [Antes](../results/etapa1c2-sector01/replay-antes.json) · [Después](../results/etapa1c2-sector01/replay-despues.json)

## Causa demostrada

Cada muestra FCD guarda la posición del frente, el rumbo, el avance longitudinal y la longitud del vehículo. Para dibujarlo con el icono anclado en el centro se desplaza el frente media longitud en sentido opuesto al rumbo. El reproductor anterior usaba el avance longitudinal para colocar nuevamente el frente sobre la forma del carril. También calculaba el rumbo con la tangente local de esa forma. Entre muestras repetía el cálculo con la tangente del recorrido interpolado. En carriles internos cortos, las dos tangentes podían apuntar en sentidos opuestos.

En `mansa-1` a 110,5 s, el segmento de `:2535807404_0_0` va de `[462.87, 1158.28]` a `[462.90, 1157.26]` en coordenadas de red. SUMO registra **359,45°**, mientras la tangente da **177,15°**. Para un vehículo de 5 m, aplicar el desplazamiento de 2,5 m a rumbos casi opuestos sitúa el centro en lados contrarios del frente. El error proyectado en ese extremo alcanza **4,995 m**. Al comenzar a interpolar, el cálculo anterior volvía a tomar una tangente cercana a 356°, con un cambio de rumbo de hasta 179,34° entre las subdivisiones medidas.

En el acceso de servicio a 202 s, la tangente daba **211,48°** frente a los **33,47°** de SUMO. A 202,5 s daba **76,46°** frente a **143,66°**. La geometría local alteraba tanto el frente calculado como el desplazamiento de medio vehículo. Las coordenadas y orientaciones de cada muestra se cotejaron con el replay guardado. [Muestras y posiciones antes del cambio](../results/etapa1c2-sector01/replay-antes.json) · [Fixture de regresión](../tests/fixtures/lane_motion_sector01.json)

## Corrección

En 2D, cada muestra se dibuja en el centro calculado desde el frente, el rumbo y la longitud registrados. La interpolación avanza entre esos centros. La forma del recorrido sólo aporta una curvatura lateral acotada a un cuarto de la distancia entre extremos y su aporte se reduce a cero en los anclajes. Esto impide que una tangente invertida cambie la dirección del avance entre dos referencias. El rumbo sigue el arco más corto entre los ángulos registrados, incluidos los pasos por 0°. Si falta una forma utilizable se interpola entre los mismos centros y rumbos FCD.

Los desplazamientos hacia atrás presentes en los extremos se conservan. El modo **Muestras FCD sin interpolar** sigue mostrando el frente registrado. La comparación de posiciones entre ambos modos tiene en cuenta la diferencia entre frente y centro. La corrección se selecciona en el mapa 2D. El visor 3D y el cálculo de sus trayectorias de ómnibus siguen usando el recorrido anterior. [Interpolación](../urbanflow-web/lane-motion.js) · [Selección de vista en el reproductor](../urbanflow-web/app.js)

## Medición antes y después

Se ejecutó el código de ambas versiones con las mismas muestras. El desplazamiento firmado se proyecta en el eje de cada conexión. El error de anclaje compara centros en metros y rumbos en grados, usando como referencia el frente FCD convertido a centro. Los saltos se midieron sobre 20 subdivisiones por intervalo de 0,5 s.

| Caso | Referencia FCD del centro | Reproductor anterior | Reproductor corregido |
|---|---:|---:|---:|
| `mansa-1`, 110,5–111 s | +1,805 m | −3,190 m | +1,805 m |
| `salida-servicio-1`, 202–202,5 s | +4,264 m | −2,428 m | +4,264 m |
| `mansa-1`, 110–110,5 s | −0,591 m | +4,406 m | −0,591 m |
| `salida-servicio-1`, 201,5–202 s | −1,893 m | +2,699 m | −1,893 m |

| Máximo en los 20 intervalos | Antes | Después |
|---|---:|---:|
| Error de posición en un extremo | 5,005 m | 0 m |
| Error de rumbo en un extremo | 178,01° | 0° |
| Cambio de rumbo entre subdivisiones | 179,34° | 5,51° |
| Cambio de posición entre subdivisiones | 5,065 m | 0,252 m |
| Intervalos con avance FCD y retroceso añadido de al menos 0,35 m | 10 | 0 |

El cambio de rumbo real de 110,19° en servicio permanece visible a lo largo de su intervalo. En Bulevar Artigas siguen las dos alertas geométricas con cero muestras directas. La forma dibujada entre muestras es una aproximación. El paso FCD de 0,5 s fija la resolución de la evidencia de SUMO.

## Prueba en Chrome

Desde PowerShell, en la raíz de UrbanFlow, ejecutá:

```powershell
$study = 'results/etapa1c-sector01-validacion'
$qa = 'results/etapa1c2-sector01/qa'
python -B tools/open_replay_qa.py "$study/manifest.json" $qa "$study/sector01.geojson"
```

En **Mapa 2D**, elegí la alerta de `mansa-1` a **110,5 s** y pulsá **Ir al instante**. Seleccioná ese vehículo en **Seguir vehículo**. A velocidad lenta, reproducí hasta **111 s** y observá que el auto avanza sin darse vuelta al salir del carril interno. Para `salida-servicio-1`, repetí entre **202 y 202,5 s**. El giro registrado se mantiene durante el avance. Activá **Muestras FCD sin interpolar** para ver el frente y el rumbo en los instantes guardados. Las alertas de los intervalos previos, 110–110,5 s y 201,5–202 s, ubican los desplazamientos hacia atrás que ya estaban en SUMO.

La prueba automatizada en Chrome cargó el mapa, saltó a 110,5 s y registró los datos que el reproductor envió al mapa en ambos modos. Se verificaron los tres instantes y un punto intermedio de cada caso. La revisión visual de los iconos queda disponible con el procedimiento anterior. [Evidencia de Chrome](../results/etapa1c2-sector01/qa/browser-map-qa.json)

## Archivos y regresiones

- `urbanflow-web/lane-motion.js` incorpora los anclajes FCD. `app.js` y `replay-views.js` seleccionan el movimiento 2D. `index.html` actualiza las versiones de los recursos.
- `tests/test_lane_motion.cjs` y `tests/fixtures/lane_motion_sector01.json` cubren los dos casos reales, recta, vehículo largo, giro, cambio de carril y una muestra detenida sin geometría utilizable.
- `tools/audit_replay_geometry.cjs` mide error de anclaje, pasos y rumbos. `sumo_scenario/replay_qa.py` conserva los resultados anterior y posterior. `tools/package_replay_qa.py` incorpora la evidencia anterior al paquete.

Pasaron **32 pruebas** sin omisiones, incluidas ocho del reproductor y sus controles, cuatro de auditoría QA, 11 del compilador y nueve de baseline estricta. La comparación usó los registros originales de la corrida. Se verificaron los 93 archivos históricos, los 54 artefactos del sector y la igualdad de las 48 alertas ajenas al reproductor. [Reproductor](../results/etapa1c2-sector01/qa/reproductor.log) · [Auditoría](../results/etapa1c2-sector01/qa/auditoria-qa.log) · [Compilador](../results/etapa1c2-sector01/qa/compilador-1a.log) · [Baseline estricta](../results/etapa1c2-sector01/qa/baseline-estricta.log) · [Integridad](../results/etapa1c2-sector01/qa/integridad.json) · [ZIP QA](../results/etapa1c2-sector01/urbanflow-sector01-qa-1c2.zip)
