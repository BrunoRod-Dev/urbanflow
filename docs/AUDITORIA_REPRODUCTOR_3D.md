# UrbanFlow · Etapas 1C.4 y 1C.5 · Auditoría del reproductor 3D

**Certificación visual pendiente.** En la corrida original del Sector 01, el 3D reproduce los diez retrocesos que la Etapa 1C.2 eliminó del mapa 2D. Ambos visores comparten el reloj, pero eligen funciones de movimiento distintas para el mismo instante. La geometría candidata elimina cuatro inversiones de SUMO. El acceso de servicio queda pendiente en la red y en la auditoría del visor. [Resultado de geometría](ETAPA1C3_GEOMETRIA_SECTOR01.md) · [Medición 2D y 3D](../results/etapa1c3-sector01/auditoria-3d.json)

## Movimiento y coordenadas

- `app.js` calcula un único tiempo de simulación, busca el cuadro FCD y elige la interpolación según la vista activa. El mapa 2D usa `fcdAnchored`. Cuando se activa el 3D, se usa el modo anterior de `createLaneMotion`. Este ubica el frente sobre la forma del carril con la posición longitudinal y sustituye el rumbo FCD por la tangente local. Luego desplaza el frente media longitud para dibujar el centro.
- `vehicle-models.js` recibe esos centros y rumbos para los autos. `scene-coordinates.js` convierte las coordenadas geográficas al plano SUMO local, transforma el rumbo a yaw y la escena usa `z = -norte`. El GLB se ajusta al ancho, alto y largo del tipo de vehículo y se centra horizontalmente. En los dos casos medidos el error aparece en los datos que recibe el visor, antes de la proyección y del modelo.
- El ómnibus `terminal-bus` tiene otro recorrido de renderizado. `vehicle-path.js` vuelve a muestrear el modo anterior, reconstruye el frente, acumula distancia y estima la pose del chasis desde los ejes. En ciertos tramos usa la pose común como respaldo. El Sector 01 contiene autos. Para certificar el ómnibus se necesita una prueba con la referencia existente que incluya el cambio entre ambas poses. [Selección e interpolación](../urbanflow-web/app.js) · [Modelos](../urbanflow-web/vehicle-models.js) · [Proyección](../urbanflow-web/scene-coordinates.js) · [Ómnibus](../urbanflow-web/vehicle-path.js)

## Defectos medidos

Se ejecutó la función de interpolación de `app.js` para ambas vistas sobre los mismos 20 intervalos y se aplicó la transformación de escena del 3D. El 2D coincide con los centros obtenidos del frente y rumbo FCD en los extremos. Se usó la corrida guardada para conservar los mismos instantes de las regresiones. Los desplazamientos firmados se proyectan sobre el eje de la conexión.

| Caso de la corrida original | Centro FCD / 2D | Centro 3D | Mayor error de rumbo en los extremos |
|---|---:|---:|---:|
| `mansa-1`, 110,5–111 s | +1,805 m | −3,190 m | 177,70° |
| `salida-servicio-1`, 202–202,5 s | +4,264 m | −2,428 m | 178,01° |

En `mansa-1`, la orientación 3D salta hasta **179,33°** entre subdivisiones de 0,025 s. En Chrome, el mismo instante de 110,5 s produjo **177,15° en el 3D** frente a **359,45° en FCD**. El centro que recibe el 3D se desplaza hasta **5,00 m** respecto al 2D, medido en el plano local. La cámara y el modelo no participan en el cálculo que crea ese error. [Registro de Chrome](../results/etapa1c3-sector01/chrome-3d.json)

En las 7.430 muestras de los 36 viajes, **97** difieren más de 0,5 m en posición y **195** más de 5° en rumbo. Fuera de los casos de inversión, las sondas de Sader, Miami, El Pinar y Pirineos presentan diferencias máximas de entre **1,18 y 1,36 m** y de **27,32° a 31,66°**. La sonda de Península por carril 1 presenta hasta **0,17 m y 3,76°**. El JSON guarda los instantes, carriles y poses de esos casos. Los giros reales de SUMO siguen como referencia y cualquier diferencia de los visores se calcula contra su propio instante FCD.

## Cámara, seguimiento, sincronización y rendimiento

En Chrome, se abrió el canvas 3D y se probaron los controles de cámara elevada, nivel de calle, acercar, alejar y restablecer. Cambiar de 3D a 2D conservó **110,5 s**. La selección de vista y la prueba de reproducción confirman que hay un reloj compartido. El 3D usa ese tiempo para vehículos, semáforos y peatones disponibles. Los indicadores de cola usan el cuadro FCD correspondiente.

Para el sector, la cámara elevada usa una cobertura fija de 63 m en ausencia de referencias especiales. El área 3D calculada mide aproximadamente **747 × 1.911 m**. La vista inicial queda centrada en una parte del corredor. La cámara de calle elige un carril cercano al centro. La rueda y los controles permiten acercar y orbitar. El botón de encuadre y el seguimiento QA actúan sobre el mapa. **Ubicar** e **Ir al instante** regresan a 2D. La flota descarta poses fuera del rectángulo de escena. El cálculo encontró **128 muestras** fuera de esos límites, que el mapa puede mostrar. Son poses fuera del marco 3D, incluidas aproximaciones más allá del polígono de selección. Un límite de recorte explícito debe distinguirse de un vehículo perdido.

La escena usa geometría vial derivada de las formas y anchos de SUMO, y vehículos instanciados. El pavimento se genera a altura fija y el centro de los autos se proyecta al mismo plano. La auditoría comprobó desalineaciones horizontales en los datos de pose y no cubrió pendientes ni niveles separados. El 3D muestra las señales de un controlador seleccionado para la escena, mientras el 2D puede mostrar todos los estados registrados. El Sector 01 conserva 23 controladores en la corrida.

En una prueba corta de Chrome sin ventana, con Intel UHD Graphics y hasta diez autos activos, se registraron 208 llamadas de dibujo. El tiempo de CPU alrededor del dibujo tuvo mediana de **0,4 ms** y percentil 95 de **0,9 ms**. Los intervalos de animación tuvieron mediana de **6,9 ms**, percentil 95 de **7,1 ms** y una pausa máxima de **673,5 ms**. Es una medición exploratoria con el visor recién abierto. Queda pendiente una prueba visible y sostenida que separe inicialización, fluidez y trabajo de GPU. [Datos de la sesión](../results/etapa1c3-sector01/chrome-3d.json) · [Cámara y escena](../urbanflow-web/viewer3d.js)

## Propuesta de corrección 3D

1. Hacer que la vista 3D de autos consuma las mismas poses ancladas a FCD que el mapa, en el mismo reloj. Mantener la proyección, el centro de la malla, el yaw y la altura como adaptaciones de render. Medir la pose antes y después de la proyección para distinguir errores de movimiento, escala y orientación del activo.
2. Mantener las poses de frente y centro como un contrato explícito. Para el ómnibus, alimentar el cálculo de ejes desde la misma trayectoria y comprobar la continuidad en los extremos y al activar el modelo de chasis. Usar las referencias guardadas de Honduras y Camacho. El cálculo actual del ómnibus queda pendiente de validación dinámica.
3. Permitir encuadrar el corredor, enfocar un vehículo por ID y ubicar alertas en 3D usando los controles QA existentes. Conservar el tiempo y el vehículo seleccionado al alternar vistas. Definir el área visible a partir del corredor o marcar cuándo un vehículo sale del área activa.
4. Ejecutar el conjunto de regresión sobre la corrida original y la candidata revisada. Usar `mansa-1`, `salida-servicio-1`, las cinco sondas de geometría, las sondas de Miami, El Pinar, Pirineos, Emilio Sader y Península y el ómnibus de referencia. La corrida original conserva las anomalías como casos de prueba reproducibles.

La auditoría se reproduce desde la raíz del proyecto con la misma corrida y eventos QA.

```powershell
$study = 'results/etapa1c-sector01-validacion'
$id = (Get-Content "$study/manifest.json" -Raw | ConvertFrom-Json).replayId
$suffix = [guid]::NewGuid().ToString('N')
node results/etapa1c3-sector01/auditar-3d.cjs "$study/$id/replay.json" results/etapa1c2-sector01/qa/qa-events.json "results/etapa1c3-sector01/3d-$suffix.json"
```

## Puerta de calidad propuesta para 1C.5

| Control | Evidencia requerida |
|---|---|
| Red y simulación | Cerrar el acceso de servicio y repetir las cinco sondas, el control negativo de giro y la demanda original. Las diferencias de geometría, rutas, prioridades, conflictos y programas se registran en la candidata. Todos los viajes esperados deben finalizar sin colisiones registradas ni teletransportes. |
| Reloj y pose | Igual tiempo, ID y centro en 2D y 3D para el mismo cuadro. Comparar la pose común y la pose renderizada contra FCD en todos los extremos. Tolerancias propuestas de 0,10 m y 1° tras la proyección. |
| Transiciones | Medir subdivisiones en los dos casos críticos, en giros, cambios de carril y entradas internas. Cero retrocesos o inversiones añadidas. Mantener visibles las anomalías reales de SUMO en el control original. |
| Inspección | En Chrome visible, encuadrar el sector, acercar, seguir un auto en ambas vistas, saltar a una alerta y alternar durante pausa y reproducción. Los eventos estáticos deben permitir ubicar su coordenada. Verificar límites de escena, alineación con carriles y anclaje frente/centro. |
| Rendimiento | En el equipo de prueba, registrar resolución, navegador, GPU y vehículos activos. Medir al menos 60 s tras cargar el visor, con tiempo de cuadro p95 ≤ 33,3 ms y sin pausas de más de 250 ms durante reproducción estable. Registrar el tiempo de primera carga aparte. |
| Referencias | Pasar regresiones de movimiento, QA, compilador y baseline estricta. Verificar huellas de Honduras, Camacho y los estudios históricos. Conservar los archivos de evidencia de cada candidato. |

La hoja de ruta es cerrar y revisar la geometría de servicio, autorizar el ajuste 3D tras revisar este diagnóstico y ejecutar la puerta conjunta con Chrome visible. El Sector 02 queda sujeto a la aprobación de esa puerta.
