# UrbanFlow · Etapa 1C.1 · Observabilidad del Sector 01

La auditoría de Punta del Este–Mansa reutiliza las dos corridas de Etapa 1C. En cada una SUMO registró **36 llegadas de 36 vehículos insertados, cero colisiones y cero teletransportes**. El análisis de 7.430 muestras FCD detectó retrocesos proyectados en tres conexiones y un desplazamiento adicional introducido por el cálculo de posiciones del reproductor 2D. [Resumen QA](../results/etapa1c1-sector01-final/qa-summary.json) · [Eventos](../results/etapa1c1-sector01-final/qa-events.json) · [Informe generado](../results/etapa1c1-sector01-final/QA_REPORT.md)

## Las cinco conexiones

- **Williman, nodo `2535807404`.** Las formas retroceden 1,02 m en `:2535807404_0_0` y 1,05 m en `:2535807404_0_1`. Hubo cinco y cuatro muestras directas respectivamente. En los nueve pasos observados, el frente se desplazó 0,59–0,62 m contra el eje de la conexión al entrar al carril interno. Por ejemplo, `mansa-1` a 110,5 s registra velocidad de 2,60 m/s y rumbo de 359,45°, con rumbo casi idéntico al de la muestra anterior.
- **Servicio, nodo `2480679873`.** La forma de `:2480679873_1_0` retrocede 2,33 m. En la única muestra directa, `salida-servicio-1` registra un desplazamiento de 1,76 m contra el eje entre 201,5 y 202 s. A los 202,5 s su orientación cambia 110,19°. Se detectaron otros dos cambios bruscos de orientación en la misma salida, de 149,03° y 138,16°. Esos intervalos tienen muestras en carriles vecinos y el giro queda señalado para revisión.
- **Bulevar Artigas, nodo `4462688320`.** Las formas de `:4462688320_0_0` y `:4462688320_0_1` retroceden 1,51 m y 1,65 m. Los dos carriles tienen cero muestras directas. Los eventos estáticos conservan las coordenadas del nodo y dejan vacíos el vehículo y el instante.

El análisis mide desplazamiento en coordenadas y conserva el rumbo, la velocidad y la posición longitudinal informados por SUMO. En los diez intervalos con desplazamiento proyectado hacia atrás, la velocidad registrada es positiva. La trayectoria muestreada confirma el desplazamiento geométrico y permite localizarlo. Los datos de la corrida tienen un paso de 0,5 s.

Para medir el efecto del reproductor ejecuté su función `createLaneMotion` en Node sobre los mismos pares de muestras, con 20 subdivisiones por intervalo. También reconstruí el centro a partir del frente y del rumbo FCD para comparar el mismo punto del auto. Para `mansa-1` entre **110,5 y 111 s**, ese centro avanza **1,81 m** en el eje del carril. El centro calculado por el reproductor termina **3,19 m hacia atrás**. Su retroceso máximo durante ese intervalo llega a **5,06 m**. El patrón se repite en los nueve pasos de Williman y aparece también en la salida de servicio. El cálculo establece diez casos de retroceso adicional del reproductor y los vincula a sus intervalos originales. [Muestras FCD y cálculo del reproductor](../results/etapa1c1-sector01-final/qa-replay-geometry.json)

## Alcance de la auditoría

`python -B -m sumo_scenario.replay_qa` lee la red, demanda, logs, trayectorias, llegadas, colisiones, resumen y estados semafóricos de una corrida guardada. El informe registra los umbrales, las huellas de los archivos y la evidencia de cada alerta. Las coordenadas se expresan en longitud y latitud cuando hay datos geográficos disponibles. En un evento estático corresponden al nodo y en un evento FCD a la muestra indicada.

- **Resultados registrados.** Cero viajes incompletos y cero alertas de ruta o continuidad en los recorridos muestreados. Se cotejó el orden de las aristas con las rutas de entrada y se comprobaron las conexiones por carril, incluyendo carriles internos y cambios laterales. La inferencia de continuidad entre muestras no reconstruye todas las posiciones intermedias.
- **Detenciones y orientación.** Se detectaron seis detenciones con velocidad inferior a 0,1 m/s durante al menos 30 s entre la primera y última muestra quieta. La mayor fue de 43 s entre muestras. Se detectaron tres cambios de rumbo de al menos 75° en movimiento y cero saltos de posición sobre el umbral de desplazamiento de la prueba. La detención por sí sola no identifica un bloqueo.
- **Repetibilidad.** Se recalcularon las comparaciones de trayectorias, viajes, resumen, estados y colisiones, con coincidencia en los cinco archivos. Para el resumen se omitió el tiempo de cómputo por paso. Las huellas normalizadas coinciden con `simulation-comparison.json` de 1C.
- **Controles.** Los 23 programas inferidos tienen estados registrados. El informe deja la corroboración física pendiente y registra las prioridades como una alerta agregada. El atributo `--physical inferred` se activa para corridas cuya procedencia lo justifica. La auditoría acepta vehículos explícitos con ruta XML y deja constancia de otras formas de demanda que no puede enumerar.

## Probar en el reproductor

Desde PowerShell, en la raíz de UrbanFlow, ejecutá:

```powershell
$study = 'results/etapa1c-sector01-validacion'
$qa = 'results/etapa1c1-sector01-final'
python -B tools/open_replay_qa.py "$study/manifest.json" $qa "$study/sector01.geojson"
```

El comando abre una instancia local del reproductor con el modo QA activado. En **Mapa 2D** podés encuadrar el sector, controlar las cuatro capas y seguir un vehículo por su ID SUMO. Elegí una alerta y pulsá **Ubicar** para centrar sus coordenadas. **Ir al instante** pausa y posiciona la corrida en la marca registrada cuando existe. Para comparar el caso de `mansa-1`, seleccioná el retroceso observado a 110,5 s o la alerta del reproductor a 111 s y alterná **Muestras FCD sin interpolar**. La marca QA muestra el punto registrado y las muestras FCD dibujan el frente del vehículo. Si elegís una alerta estática de Bulevar Artigas, sólo queda disponible **Ubicar**.

El modo se activa al abrir la URL QA que imprime el comando. El reproductor usa las mismas rutas de estudio de UrbanFlow y un archivo de alertas servido por el lanzador local. En Chrome se comprobaron la carga de la corrida y del mapa, la interacción con los cuatro controles de capas, la selección de vehículo, el encuadre, la localización, el salto a 202,5 s y la ausencia de los controles QA al abrir el estudio sin la opción. La comparación numérica del movimiento del vehículo se hizo con el código de reproducción en Node. [Comprobación HTTP](../results/etapa1c1-sector01-final/replay-qa-http.json) · [Controles en Chrome](../results/etapa1c1-sector01-final/browser-qa.json) · [Mapa en Chrome](../results/etapa1c1-sector01-final/browser-map-qa.json)

## Repetir y compartir

```powershell
$study = 'results/etapa1c-sector01-validacion'
$id = (Get-Content "$study/manifest.json" -Raw | ConvertFrom-Json).replayId
$run = "$study/$id"
$suffix = [guid]::NewGuid().ToString('N')
$fcd = "results/etapa1c1-fcd-$suffix"
$qa = "results/etapa1c1-qa-$suffix"
python -B -m sumo_scenario.replay_qa $run $fcd --compare "$study/repeticion-b" --physical inferred
node tools/audit_replay_geometry.cjs "$run/replay.json" "$fcd/qa-events.json" "$fcd/render.json"
python -B -m sumo_scenario.replay_qa $run $qa --compare "$study/repeticion-b" --physical inferred --replay-geometry "$fcd/render.json"
python -B tools/package_replay_qa.py $study $qa "$qa/urbanflow-sector01-qa.zip"
```

El ZIP contiene el informe, eventos, huellas, red, demanda, FCD completo de la primera corrida, resultados, logs y estados semafóricos cuando cambian. El manifiesto conserva las huellas originales y las huellas de los archivos incluidos. Las copias de los XML de red y nodos se exportaron sin los comentarios de generación con rutas personales. Para la repetición incluye la comparación y las huellas normalizadas de ambas corridas. [Paquete portátil](../results/etapa1c1-sector01-final/urbanflow-sector01-qa.zip)

Pasaron cuatro pruebas dirigidas de auditoría, dos de controles del reproductor, 11 del contrato 1A y nueve de baseline histórica estricta. Se verificaron los 54 archivos del manifiesto del sector y los nombres y SHA-256 de los 93 archivos históricos. [Integridad](../results/etapa1c1-sector01-final/integridad.json)
