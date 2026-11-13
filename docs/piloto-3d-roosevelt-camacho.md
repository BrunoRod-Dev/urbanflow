# Corrida de referencia para el visor 3D

- **ID del estudio** `ea040a66a0414cfe8ebc1a04c78453ab`
- **ID de la corrida** `c44da2efd14c48569d6a9ce276916ba5`

La corrida se generó desde la rotonda de Antonio Camacho y Franklin Delano Roosevelt con SUMO 1.26.0, semilla 42 y cuatro minutos de tráfico de muestra. Ingresaron 45 autos y 37 completaron el recorrido. Se usó el recorte regional de OpenStreetMap del 10 de noviembre de 2026 a las 21:21:39 UTC. [Fuente del recorte](https://download.geofabrik.de/south-america/uruguay.html) · [Atribución de OpenStreetMap](https://www.openstreetmap.org/copyright)

## Área para representar

- **Encuadre principal.** Última cuadra de 18 de Julio junto a la Terminal, ramal de incorporación, calzada de Roosevelt hacia el noroeste y anillo de Camacho. La prueba empieza en el ramal cerca de `-34.91638, -54.95850` (latitud, longitud).
- **Segundo encuadre.** Roosevelt y Honduras, siguiendo Roosevelt hacia el noroeste. Está dentro de la misma red y usa el mismo reloj de reproducción. El acceso oeste de Honduras se puede ubicar cerca de `-34.91437, -54.96148` (latitud, longitud).
- **Recorte propuesto para la escena 3D.** `[-54.96200, -34.91665, -54.95815, -34.91395]` (oeste, sur, este, norte en WGS84). Son aproximadamente 350 × 300 m. Cubre ambos encuadres y el tramo de Roosevelt que los conecta. La corrida usa el área de estudio mayor `[-54.96311, -34.918823, -54.955989, -34.912984]`.

## Cómo comprobar la corrida

Abrí `Abrir UrbanFlow.cmd` y entrá al [estudio guardado de Roosevelt–Camacho](http://127.0.0.1:8000/#proyecto/ea040a66a0414cfe8ebc1a04c78453ab). También lo podés encontrar en **Estudios** buscando **Roosevelt Camacho**. Elegí **Reproducir**. Los enlaces usan el puerto habitual 8000. Si el lanzador indica otro puerto, usá esa dirección y mantené el fragmento que empieza por `#`.

### Auto que toma la incorporación

El auto `f8.0` de SUMO corresponde al ID `7` del visor. Usa la ruta `r8`. Para seguirlo, acercá el mapa a la Terminal y reproducí a **1×** desde los 21 s.

- [00:21 · Ramal de la Terminal](http://127.0.0.1:8000/#estudio/c44da2efd14c48569d6a9ce276916ba5?t=21) — primer registro en `783169882#0_0`, después de salir del carril `230055789#7_0` de 18 de Julio.
- [00:28 · Roosevelt](http://127.0.0.1:8000/#estudio/c44da2efd14c48569d6a9ce276916ba5?t=28) — primer registro en `553842606#1_0`, uno de los dos carriles de ese tramo.
- [00:32 · Entrada al anillo](http://127.0.0.1:8000/#estudio/c44da2efd14c48569d6a9ce276916ba5?t=32) — primer registro en `100473863#1_0`.

### Cambio de fase en Roosevelt y Honduras

Abrí **Vista 3D → Roosevelt y Honduras**. En el acceso oeste de Honduras, el carril `1532518649#0_0` tiene un cabezal con flecha de giro a la derecha para el movimiento `17` y otro con flecha de frente para el `18`. Ambos pertenecen al controlador `joinedS_1360014840_13966777057_13966777058_2375592994`.

- [00:18,5 · Rojo](http://127.0.0.1:8000/#estudio/c44da2efd14c48569d6a9ce276916ba5?t=18.5) — estado `r` en ambos movimientos.
- [00:19 · Verde](http://127.0.0.1:8000/#estudio/c44da2efd14c48569d6a9ce276916ba5?t=19) — estado `G` en ambos movimientos.
- [00:29 · Amarillo](http://127.0.0.1:8000/#estudio/c44da2efd14c48569d6a9ce276916ba5?t=29) — estado `y` en ambos movimientos.

Activá **Movimientos habilitados** para ver las flechas sobre el pavimento. Verde indica paso con prioridad (`G`), celeste indica paso cediendo (`g`) y ámbar indica giro permitido tras detenerse (`s`). La barra muestra segundos enteros. El enlace de 18,5 s posiciona la reproducción en la muestra exacta. [Estados y movimientos en SUMO](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html)

La escena usa los 22 índices de enlace de `network.net.xml` y los estados registrados en `signal-states.xml`. Los postes y cabezales se ubican a partir de la geometría de los carriles. Sus posiciones físicas y los tiempos de campo quedan por relevar. El encuadre también está disponible en la corrida con ómnibus.

## Comprobar la vista 3D

1. Abrí la corrida pausada en [00:21](http://127.0.0.1:8000/#estudio/c44da2efd14c48569d6a9ce276916ba5?t=21). En el mapa 2D ubicá **A** al final del ramal de incorporación y **B** en la entrada al anillo.
2. Elegí **Vista 3D**. Las dos referencias corresponden a los mismos puntos en la vista elevada. Arrastrá la escena para girar y usá `+` o `−` para acercar o alejar.
3. Elegí **Nivel de calle** para bajar la cámara a 1,65 m junto al acceso. **Restablecer cámara** recupera el encuadre de la cámara seleccionada. Volvé a **Mapa 2D** y comprobá que la reproducción sigue pausada en 00:21.

La escena usa metros del sistema de SUMO, con el origen en el centro de la rotonda. Los carriles usan sus puntos cartesianos y los vehículos y las referencias se ubican en el mismo sistema invirtiendo la proyección guardada en `replay.json`. Las referencias A y B coinciden con los extremos de los carriles correspondientes con diferencias de 2,5 y 3,1 cm en esta corrida. El relieve se representa plano. Three.js y Clipper se cargan al abrir **Vista 3D** y requieren acceso a su CDN. [Instalación de Three.js](https://threejs.org/manual/en/installation.html) · [Documentación de Clipper](https://github.com/junmer/clipper-lib/blob/master/Documentation.md)

## Calzada, veredas y entorno

- **Calzada y giros.** La superficie combina los carriles externos, las conexiones internas y los contornos de las uniones de `network.net.xml`. Los carriles del piloto carecen de ancho explícito en ese archivo. Se representan con un ancho de referencia de **3,20 m**. Las isletas se deducen del espacio entre las calzadas. El anillo conserva su isla central. [Formato de red de SUMO](https://sumo.dlr.de/docs/Networks/SUMO_Road_Networks.html)
- **Veredas y cordones.** OpenStreetMap registra veredas a ambos lados de 18 de Julio y Cecilia Burgueño. La ubicación de los bordes se deriva de la calzada simulada. Se estimaron **2 m** de ancho para las veredas y **16 cm de ancho por 15 cm de alto** para el cordón. En los demás tramos se infiere la continuidad en función de la calzada. Los cruces peatonales mapeados se usaron para ubicar sus accesos.
- **Marcas viales.** Se muestran seis flechas de giro o avance en el entorno de Roosevelt y Honduras a partir de `turn:lanes`. Su posición a lo largo del carril se estimó a 6 m de su extremo. OpenStreetMap marca 18 de Julio como vía sin líneas de carril. Los cruces peatonales de Honduras están mapeados, con el patrón de pintura pendiente de confirmar.
- **Edificios.** Nueve huellas provienen del recorte complementario de OpenStreetMap consultado el 12 de noviembre de 2026. Se representan con volúmenes simples, con **3,10 m por planta** cuando hay plantas registradas o **6 m** como altura de referencia. [Recorte complementario de OpenStreetMap](https://api.openstreetmap.org/api/0.6/map?bbox=-54.9623,-34.91693,-54.95791,-34.91369) · [Licencia y atribución](https://www.openstreetmap.org/copyright)

Los materiales se generan en UrbanFlow. Quedan por relevar los anchos de campo, el trazado exacto de los cordones y la pintura de los cruces. El geoportal nacional ofrece ejes de calle y ortofotos como fuentes para esa revisión. [Geoservicios de IDE Uruguay](https://www.gub.uy/infraestructura-datos-espaciales/politicas-y-gestion/geoservicios-ide)

## Corrida con auto y ómnibus 3D

La [corrida de muestra con ómnibus](http://127.0.0.1:8000/#estudio/6dd59f8101b54728a0a909fb6dbb27a7?t=30) conserva el estudio y la red de referencia. Contiene 45 autos y un ómnibus, con semilla 42, cuatro minutos de demanda y un minuto adicional para completar viajes. El ómnibus `f15.0` corresponde al ID `15` del visor. Su ruta `r15` está habilitada para la clase `bus` en SUMO. Entra por 18 de Julio, usa el ramal `783169882#0`, llega al anillo y sigue hacia Honduras.

- [00:30 · Entrada al ramal](http://127.0.0.1:8000/#estudio/6dd59f8101b54728a0a909fb6dbb27a7?t=30). Abrí **Vista 3D → Nivel de calle** y reproducí a 1× para seguir el giro.
- [00:40 · Roosevelt](http://127.0.0.1:8000/#estudio/6dd59f8101b54728a0a909fb6dbb27a7?t=40) y [00:45 · Entrada al anillo](http://127.0.0.1:8000/#estudio/6dd59f8101b54728a0a909fb6dbb27a7?t=45). Pausá y retrocedé a 00:40 para repetir la misma posición y orientación.
- [01:09 · Detenido en Honduras](http://127.0.0.1:8000/#estudio/6dd59f8101b54728a0a909fb6dbb27a7?t=69). A los 69,5 s la posición y la orientación son las mismas.

El perfil del ómnibus usa **8,54 × 2,55 × 3,00 m** (largo, ancho y alto), tomados de la ficha de Paleson para el Ankai G9 de 8,5 m. CODESA incorporó un Ankai de esa longitud en Maldonado. Las dimensiones del perfil y el modelo 3D coinciden. La carrocería y la decoración del modelo son genéricas. [Ficha técnica publicada por MIEM](https://www.gub.uy/ministerio-industria-energia-mineria/sites/ministerio-industria-energia-mineria/files/2025-09/Folleto%20informativo%20-%20Ankai%20Modelo%20%20G9%208.5m%20y%2010.5%20m.pdf) · [Entrevista a CODESA y Paleson](https://www.transportecarretero.com.uy/noticias/transporte-de-pasajeros/codesa-incorporo-su-primer-omnibus-electrico.html)

El visor toma la pose del ómnibus a partir de ambos ejes sobre la trayectoria interpolada por carril. La separación visual de los ejes corresponde al modelo genérico, aproximadamente 3,91 m. Se comprobó el apoyo de las ruedas sobre la calzada en ocho instantes entre 00:30 y 00:45. La pose se reconstruye desde el tiempo de la corrida, por lo que al retroceder se repiten la ubicación y el rumbo.

- **Sedán.** `sedan.glb` de Kenney Car Kit, licencia **CC0 1.0**. Se ajustó en el visor a **5,00 × 1,80 × 1,50 m**, el perfil genérico de SUMO. [Kenney](https://kenney.nl/assets/car-kit?part=e87ebc1a-6413-45e1-9a40-ed1276cc92d6) · [Copia utilizada](https://github.com/Hidencod/tge-assets/blob/ec2281c5239b9e78e4ff06cdd6618a3dfbcb3b73/packs/car-kit/sedan.glb) · [Valores de SUMO](https://sumo.dlr.de/docs/Vehicle_Type_Parameter_Defaults.html)
- **Ómnibus urbano.** `urban-bus.glb` de Quaternius Public Transport Pack, licencia **CC0 1.0**. Se usó una conversión a GLB y se redujo la resolución de sus texturas para el navegador. [Paquete de Quaternius](https://quaternius.com/packs/publictransport.html) · [Conversión y atribución](https://github.com/fastrouter/experiments-costa-vista/blob/23e87108a281ac827e2ea23691aa7bf4b544146e/ATTRIBUTION.md) · [Licencia CC0](https://creativecommons.org/publicdomain/zero/1.0/)

Para repetir la corrida desde la referencia original, la API de corridas acepta `sampleTerminalBus: true` junto a sus conteos, con origen `sample`. El servidor comprueba la ruta habilitada y agrega una unidad. La nueva corrida guarda los tipos y las dimensiones en `vehicleIndex` y `vehicleTypes` y se puede abrir y editar desde el mismo estudio.

## Corrida con autos, ómnibus, motos y camionetas

La [corrida mixta de Roosevelt–Camacho](http://127.0.0.1:8000/#estudio/1326984e1af04135a05c1d17adab271b?t=38) reutiliza la red guardada, SUMO 1.26.0 y la semilla 42. Ingresaron 45 autos, un ómnibus, dos motos y dos camionetas. El registro de SUMO muestra a las dos motos y las dos camionetas usando el ramal de la Terminal, incorporándose a Roosevelt y pasando por la rotonda. La primera unidad de cada tipo llegó al final del recorrido. La segunda seguía en la cola de Roosevelt y Honduras al terminar los cinco minutos de simulación.

- **Moto.** Clase `motorcycle` y dimensiones de **2,20 × 0,90 × 1,50 m**, incluido el conductor en el modelo 3D. El perfil de muestra usa aceleración de 3,5 m/s², desaceleración de 5 m/s², separación mínima de 1,5 m y velocidad máxima de 25 m/s. Circula por el carril asignado por SUMO. El modelo de la moto y el conductor se genera en UrbanFlow. [Dimensiones de referencia de SUMO](https://sumo.dlr.de/docs/Vehicle_Type_Parameter_Defaults.html)
- **Camioneta.** Pickup liviana de clase `passenger`, con dimensiones estimadas de **5,30 × 1,90 × 1,85 m**. El perfil de muestra usa aceleración de 2,2 m/s², desaceleración de 4,5 m/s², separación mínima de 2,5 m y velocidad máxima de 33,33 m/s. El modelo se ajusta a esas medidas y proviene del **Car Kit de Kenney**, licencia **CC0 1.0**. [Kenney Car Kit](https://kenney.nl/assets/car-kit) · [Copia del modelo utilizado](https://github.com/Hidencod/tge-assets/blob/ec2281c5239b9e78e4ff06cdd6618a3dfbcb3b73/packs/car-kit/truck-flat.glb)

Los parámetros de conducción son de muestra. El servidor revisa, por clase, los permisos de los carriles y sus conexiones en la red guardada. En la corrida, las primeras unidades de los tres tipos adicionales siguieron el mismo recorrido desde 18 de Julio. La incorporación usa el carril `783169882#0_0` y conecta con `553842606#1_0` en Roosevelt. [Permisos vehiculares en SUMO](https://sumo.dlr.de/docs/Simulation/VehiclePermissions.html)

En **Vista 3D → Nivel de calle**, reproducí a **1×** desde los 38 s. El ómnibus `f15.0` va adelante, seguido por la moto `f16.0` y la camioneta `f17.0`. Los tres pasan por el empalme con Roosevelt entre los 37 y los 44 s. Para repetir la corrida desde la referencia original, abrí **Configurar tráfico**, marcá **Completar la flota de muestra con ómnibus, motos y camionetas** y elegí **Guardar y simular**. Los vehículos agregados quedan como filas editables en la nueva corrida.

## Cebra de Burnett antes de Sarandí

El escenario toma la cebra de **Enrique G. Burnett**, unos 7 m al oeste de Sarandí, del nodo `1961589755` marcado como `crossing:markings=zebra` en el recorte de OpenStreetMap. Está dentro de la red de Roosevelt–Camacho, hacia el este del encuadre 3D de la Terminal. Se modeló con prioridad peatonal y sin fase semafórica, según la señalización registrada y la regla de preferencia en pasos reglamentarios. Las dos veredas de **2 m**, sus trazados de aproximación y el ancho de la cebra de **3 m** son estimados. [Cebra en OpenStreetMap](https://www.openstreetmap.org/node/1961589755) · [Artículo 17 de la Ley 18.191](https://www.impo.com.uy/bases/leyes/18191-2007/17)

La red conserva los movimientos y programas semafóricos de la corrida mixta. Se dividió el tramo de Burnett en la cebra y se ajustaron sus dos conexiones hacia Sarandí. SUMO construye un área peatonal en cada extremo del paso. Se agregaron tres peatones de muestra en ambos sentidos y un auto de prueba por Burnett. [Cruces y veredas en SUMO](https://sumo.dlr.de/docs/Simulation/Pedestrians.html)

Abrí `results/pilot-burnett-pedestrians/burnett.sumocfg` en **SUMO GUI** con **Archivo → Abrir simulación** y tocá **▶**. La vista arranca enfocada en la cebra.

- **11 s.** `peaton-01` se aproxima por la vereda sur.
- **14–16 s.** El peatón atraviesa la cebra con prioridad. `auto-cebra-01` frena y está detenido a **15,5 s** en `184791610#2_0`.
- **16,5–17 s.** El auto retoma la marcha y la persona continúa por la vereda norte.

En la prueba de control con la misma red, la misma semilla y la demanda vehicular sola, el auto entra al cruce a los 14 s y a los 15,5 s ya está pasando por Sarandí a 9,45 m/s. Se comprobó que los 51 vehículos de la corrida principal usaron carriles permitidos para su clase. Los tres peatones pasaron de una vereda a la otra.

`pedestrian-replay.json` guarda `personIndex` con los IDs `peaton-01` a `peaton-03` y cuadros cada 0,5 s en el mismo reloj que `trajectories.xml`. Cada muestra contiene ID, longitud y latitud WGS84, rumbo, velocidad, tramo y posición longitudinal. `pedestrians.fcd.xml` conserva la salida original de SUMO. [Formato FCD de SUMO](https://sumo.dlr.de/docs/Simulation/Output/FCDOutput.html)

Para regenerar los archivos, ejecutá `python -m sumo_scenario.pedestrian_pilot` desde el proyecto. El comando usa la corrida mixta guardada como origen. Con `--base` podés indicar otra corrida con la misma geometría de Burnett. Con `--output` podés generar el escenario en otra carpeta sin sobrescribir la primera corrida.

## Peatones 3D en la cebra de Burnett

En **Estudios**, abrí **Cebra de Burnett y Sarandí** y elegí **Reproducir → Vista 3D**. La vista abre la cámara **Cebra de Burnett**. La [corrida web desde 01:50](http://127.0.0.1:8000/#estudio/9d24c5425f424b309e86bd7d8e8af361?t=110) deja al peatón de camisa naranja aproximándose por la vereda sur.

- **01:57–02:01.** `peaton-04` hace una pausa de muestra de cuatro segundos en la vereda, registrada por SUMO.
- **02:03–02:05.** Atraviesa la cebra. El visor anima los pasos según la distancia y la velocidad de la trayectoria.
- **02:06.** Continúa por la vereda norte.

Los tres recorridos de la primera prueba conservan sus muestras. Podés saltar a [00:15,5](http://127.0.0.1:8000/#estudio/9d24c5425f424b309e86bd7d8e8af361?t=15.5) para ver al primer peatón cruzando y al auto detenido. El cuarto recorrido incluye una parada programada en un ensanche de vereda estimado para probar la animación en reposo. La cebra tiene prioridad peatonal. [Etapas de caminata y parada en SUMO](https://sumo.dlr.de/docs/Specification/Persons.html)

El modelo de peatón se construye en UrbanFlow con piezas 3D simples. El visor usa la proyección de la red y un solo reloj para peatones, autos y estados de semáforos. La cámara **Roosevelt y Honduras** permite inspeccionar las luces de la misma corrida. En ese cruce, el movimiento `0` pasa de verde a amarillo a los **118 s**, mientras el peatón 04 está en la vereda.

Para publicar otra corrida local con esta prueba, ejecutá `python -m sumo_scenario.pedestrian_pilot --web`. El comando guarda un estudio nuevo con las posiciones de peatones y autos y las fases registradas en la misma ejecución.

## Accesos y estacionamiento en Cecilia Burgueño

La **revisión documental del 12 de noviembre de 2026** cubre los aproximadamente **105 m** entre **18 de Julio y Sarandí**, frente a la Terminal. En una [corrida del piloto](http://127.0.0.1:8000/#estudio/1326984e1af04135a05c1d17adab271b?t=38), elegí **Vista 3D → Accesos y estacionamiento**. Usá **Recorrer la cuadra** para avanzar por la vereda norte o **Ubicar un elemento** para orientar la cámara hacia su ubicación. La ficha de cada elemento enlaza la fuente y el punto en el mapa.

- **Entradas vehiculares.** El acceso oeste está en `-34.9163516, -54.9583009` y el este en `-34.9163367, -54.9575986` (latitud, longitud). Sus ejes provienen de dos vías de servicio conectadas a Cecilia Burgueño, editadas en el mapa el **20/06/2022** y consultadas el **12/11/2026**. Se representan aberturas en el cordón con un ancho estimado de **3,6 m**. El perfil y la altura de los rebajes quedan pendientes de una comprobación en sitio. [Acceso oeste](https://www.openstreetmap.org/way/253350938) · [Acceso este](https://www.openstreetmap.org/way/253350940)
- **Estacionamiento habilitado.** Se muestran las dos playas de superficie del lado sur, mapeadas como públicas y gratuitas el **20/06/2022**. URUBUS identifica el estacionamiento de la Terminal como gratuito. El contorno verde y la **P** identifican las playas en el visor. Quedan pendientes las plazas individuales y el estacionamiento junto al cordón de la calle. [Playa oeste](https://www.openstreetmap.org/way/253350937) · [Playa este](https://www.openstreetmap.org/way/253350939) · [Estacionamiento de la Terminal](https://urubus.com.uy/blog/terminal-de-maldonado/#como-llegar-a-la-terminal-maldonado)
- **Prohibición.** La banda roja señala el frente aproximado de cada entrada, donde aplica el artículo **18.2(h)** del Reglamento Nacional de Circulación Vial, con su excepción para autorizaciones expresas. Los indicadores son anotaciones del visor. Quedan pendientes la ubicación de carteles, el color de la pintura y los límites físicos exactos. Los tramos restantes se muestran en gris como **Pendientes de verificar**. [Reglamento Nacional de Circulación Vial](https://www.impo.com.uy/bases/decretos-reglamento/118-1984/18)

La calzada de esta cuadra se representa con el eje mapeado y un ancho estimado de **6,4 m**. La ficha muestra **Solo visual** para la cuadra, sus accesos, el estacionamiento y sus restricciones en la corrida del piloto. En la red simulada vecina sí hay vehículos registrados por **18 de Julio** y por el **ramal hacia Roosevelt**. [Eje de Cecilia Burgueño](https://www.openstreetmap.org/way/121504384)

## Verificación de la escena completa

Abrí la [corrida de referencia en localhost](http://127.0.0.1:8000/#estudio/9d24c5425f424b309e86bd7d8e8af361) y elegí **Vista 3D**. La corrida contiene 51 vehículos, 4 peatones y 600 muestras sincronizadas de SUMO.

- **Roosevelt y Honduras, 02:04.** Activá **Resaltar detenidos** y **Movimientos habilitados**. El carril `426635857_2` de Roosevelt muestra cinco vehículos detenidos y su señal está en rojo. La flecha del giro desde Honduras está en verde. En el registro de SUMO corresponden a los movimientos 2 y 17, respectivamente.
- **Nivel de calle, 00:30 a 00:38.** El ómnibus toma el ramal de la Terminal y alcanza Roosevelt. En **Cebra de Burnett**, al pausar en **00:15,5**, el peatón 01 está cruzando y el auto espera.
- **Accesos y estacionamiento.** Seleccioná el acceso oeste, la playa oeste y el tramo prohibido frente al acceso. Cada ficha muestra su ubicación, fuente y la etiqueta **Solo visual**. Al volver a **Mapa 2D**, el visor conserva el tiempo de la corrida. También se comprobó la apertura directa de la [corrida histórica](http://127.0.0.1:8000/#estudio/c44da2efd14c48569d6a9ce276916ba5?t=21) en ambas vistas.

La escena usa luz de día y sombras de contacto en dos lotes, uno para vehículos y otro para peatones. Se agruparon las piezas de los vehículos y de los semáforos para reducir las llamadas de dibujo. [Sombras en Three.js](https://threejs.org/manual/pages/shadows.html)

La medición en Chrome 157 con Intel UHD Graphics usó un lienzo de 969 × 443, el encuadre **Roosevelt y Honduras** y **Movimientos habilitados** activo. En cada pasada se calentaron 40 muestras y se recorrieron las 600 muestras completas, una por refresco. Las llamadas de dibujo por cuadro bajaron de 198 a 48,5 en promedio. Ambas pasadas midieron cerca de 144 FPS y un intervalo entre cuadros de 7,1 ms en el percentil 95. La reproducción continua a 8× llegó a 04:59,5 en 37,47 segundos.

## Calzada continua y semáforos del cruce compuesto

La misma vista 3D se ofrece en los estudios que conservan la proyección y los carriles de SUMO. El pavimento se estima con los carriles, giros y polígonos de cada intersección. En un cruce con varios nodos próximos unidos por el mismo controlador se rellenan los huecos dentro de su contorno. Se renderizan como isletas los polígonos físicos mapeados en OpenStreetMap y el interior estimado de los anillos identificados por SUMO. Un punto `crossing:island=yes` indica que hay un refugio, con su contorno todavía pendiente. Los datos de la vista registran los identificadores y las fuentes. Las veredas siguen los trazados y lados mapeados cuando existen. Una cebra registrada como punto usa la dirección del carril más cercano para estimar el trazo. Eso agrega una marca visual. La prioridad peatonal se simula en las corridas que incluyen la red peatonal. [Red de SUMO](https://sumo.dlr.de/docs/Networks/SUMO_Road_Networks.html) · [Isletas en OpenStreetMap](https://wiki.openstreetmap.org/wiki/Tag%3Aarea%3Ahighway%3Dtraffic_island)

Se contrastaron los ejes de Roosevelt, Honduras, Camacho, 18 de Julio y Enrique G. Burnett con el CSV departamental de IDE, que registra Burnett como **Enrique G. Burnet**. La comparación proyectó los puntos de UrbanFlow a EPSG:32721, el sistema indicado en las geometrías descargadas. El mosaico aéreo urbano 2017–2018 muestra la superficie abierta en el centro de Honduras y la isla de Camacho. IDE se usó como referencia de contraste. Sus ejes describen calles y la ortofoto corresponde a una fecha anterior a la red de estudio. [Ejes de Maldonado](https://catalogodatos.gub.uy/dataset/ide-ejes-vias-circulacion/resource/75289c47-1aad-4d3f-9157-f9e470a06b41) · [Ortofotos de IDE](https://www.gub.uy/infraestructura-datos-espaciales/politicas-y-gestion/geoservicios-ide)

En la cámara de semáforos, los postes estimados se colocan en los accesos exteriores y se comprueba que sus bases queden fuera de la calzada. Los movimientos internos siguen disponibles en **Movimientos habilitados**, sincronizados con los estados de SUMO. Se conserva el identificador del nodo semafórico de OpenStreetMap cuando existe. **Ver cruce en Street View** abre el panorama como referencia. Su API de metadatos identifica el panorama, su ubicación y fecha. El inventario de postes, cabezales y fases físicas queda pendiente de datos de Movilidad. [Semáforos de Honduras en la IDM](https://www.maldonado.gub.uy/noticias/movilidad-idm-concreto-varias-intervenciones-mitigar-los-danos-generados-lluvias-fuertes) · [Metadatos de Street View](https://developers.google.com/maps/documentation/streetview/metadata)

### Pruebas y reporte regional

- **Honduras, prueba visual histórica.** La corrida `7aa8eace2961434d9446b0eb77fe3d0a` cerró el hueco de 6,38 m² del cruce y verificó cuatro postes fuera del pavimento. La corrida `a468e3a79abe4e0c9d55adcb790d6395` usó un giro hipotético de ómnibus hacia Honduras para inspeccionar la calzada. La prueba de circulación vigente usa el recorrido publicado sobre Roosevelt y la red reconstruida.
- **Camacho y Burnett.** La [rotonda regenerada](http://127.0.0.1:8000/#estudio/f2cac09376554d76991d90888016e4de) conserva la isla. El [estudio de 18 de Julio y Burnett](http://127.0.0.1:8000/#estudio/5d65eb998ec8410494b4de1570c8c8d2) muestra la cebra de Burnett cerca de Sarandí como marca mapeada. La [corrida peatonal guardada](http://127.0.0.1:8000/#estudio/9d24c5425f424b309e86bd7d8e8af361?t=15.5) sigue disponible para probar la prioridad.
- **Chequeo de la corrida original.** El informe confirma una detención de `f15.0` entre 110 y 139,5 s en `:1360014840_1_1` y otra entre 144,5 y 158,5 s en `1532518647_0`. En la segunda, la salida que efectivamente usó estaba en rojo al empezar la detención. El carril intermedio tiene 1,19 m en esa corrida.

El chequeo regional evalúa la geometría de conexiones contra superficies no transitables mapeadas y las fases modeladas entre enlaces de un mismo controlador. Con una corrida guardada también revisa detenciones de al menos cinco segundos en los enlaces semaforizados internos y en tramos cortos entre señales. Una alerta de espacio señala una combinación posible de la red. Una detención confirmada corresponde a muestras de la corrida. Una invasión confirmada corresponde a una intersección geométrica con una superficie mapeada. Estas categorías describen el modelo.

La pasada regional de esa versión examinó **5.915 nodos viales y 36.345 conexiones**. Encontró **13** secuencias con espacio intermedio insuficiente, **19** conexiones rectas con un posible retroceso y **4** refugios mapeados sin contorno. La cobertura para comprobar invasiones se limita a los polígonos físicos registrados en el recorte. En la prueba visual histórica con ómnibus, SUMO volvió a registrar una espera de **7 s** en el tramo de 1,19 m de Honduras. Esa espera quedó registrada para comprobar la corrección de la red.

Para regenerar el informe `results/road-audit.json` con la instalación habitual de SUMO:

```powershell
python -m pip install "shapely>=2,<3" "pyproj>=3.6,<4"
python -m sumo_scenario.network_audit --region --run results/studies/9d24c5425f424b309e86bd7d8e8af361
```

Para inventariar programas y permisos semafóricos de una corrida guardada, usá `python -m sumo_scenario.network_audit --signals-only --run results/studies/ID --output results/signal-coverage-audit.json` y reemplazá `ID` por el identificador de la corrida. Este modo lee la red compilada y registra que el programa aún no fue contrastado en campo. Las corridas e informes de `results/` se guardan localmente.

### Control de una sola intersección en Roosevelt y Honduras

El generador reúne los cuatro nodos que delimitan el cruce en una intersección física de SUMO. Compara los accesos y salidas con la red importada y conserva los 12 movimientos entre calles, con 16 conexiones por carril. Elimina las vueltas en U introducidas al unir los nodos. La revisión 2 usa tres fases principales. La primera habilita los avances y giros a la derecha de Roosevelt. La segunda habilita sus giros a la izquierda y el giro a la derecha desde Honduras. La tercera habilita las calles laterales con cesión de paso en sus giros a la izquierda. Cada fase principal tiene amarillo y un intervalo de despeje. El programa y los tiempos están pendientes de contrastar en campo. [Unión física de nodos en SUMO](https://sumo.dlr.de/docs/Networks/PlainXML.html#joining_nodes) · [Regla de mantener libre la intersección](https://sumo.dlr.de/docs/Simulation/Intersections.html)

La [corrida actual de Honduras](http://127.0.0.1:8000/#estudio/32f97a5d36954c94a02793eea5892e9c) se generó desde el mapa. En una corrida de verificación extendida se completaron los 12 movimientos sin colisiones ni muestras con vehículos detenidos dentro de la intersección. En otra prueba se ocuparon los dos carriles de salida. El ómnibus esperó en su acceso y entró una vez liberada la salida. El [chequeo regional actualizado](../results/honduras-control-audit.json) conserva cuatro alertas de tramos cortos fuera de Honduras. Las corridas con el controlador anterior se identifican como históricas en el visor.

La [prueba de la línea 9 sobre Roosevelt a 01:24](http://127.0.0.1:8000/#estudio/bceb3ad9e5bf40408d95652f9595084a?t=84) usa una unidad de muestra en el tramo sobre Roosevelt entre Joaquín de Viana y Camacho, siguiendo el recorrido publicado por CODESA. La unidad cruza Honduras de frente. La opción de flota del estudio de Camacho agrega un ómnibus por el tramo publicado de la línea 52 de Maldonado Turismo, desde 18 de Julio por Roosevelt hasta Camacho. El volumen y la hora de salida de ambas unidades son de muestra. [Línea 9 de CODESA](https://www.codesa.com.uy/p/linea-9-ida.html) · [Línea 52 de Maldonado Turismo](https://maldonadoturismo.com/recorrido-linea-52/)

Waze for Cities ofrece un feed de congestión e incidentes para el polígono habilitado en Partner Hub. Para incorporar ese dato hace falta acceso al feed correspondiente a Maldonado. Los recorridos de ómnibus de esta prueba provienen de las publicaciones de los operadores. [Feed de Waze for Cities](https://support.google.com/waze/partners/answer/10618035)

## Datos para la siguiente iteración

- **Red y trayectorias.** `network.net.xml` contiene los carriles y los enlaces internos. `map.edg.xml` contiene sus trazados geográficos. `trajectories.xml` conserva el ID de SUMO, el tipo, el carril, la posición longitudinal, el rumbo y la velocidad. `replay.json` contiene 480 muestras de 0 a 239,5 s a intervalos de 0,5 s, además de la geometría que ya usa la reproducción por carril.
- **Semáforos.** `signal-states.xml` contiene los estados simulados de tres controladores. El visor 3D muestra el de Roosevelt y Honduras. El mapa 2D conserva las señales del área de estudio.
- **Vehículos y peatones.** Las corridas de muestra incluyen autos, ómnibus, motos y camionetas con rutas verificadas. La cebra de Burnett aporta tres trayectorias peatonales con el reloj de la corrida vehicular.
- **Geometría de calle.** Los carriles de la incorporación aportan ejes, conexiones y longitudes. Queda por contrastar en campo los anchos de calzada y vereda, los rebajes y la señalización de estacionamiento junto al cordón.

La corrida se guarda localmente en `results/studies/c44da2efd14c48569d6a9ce276916ba5/`. Para regenerarla con otro ID, creá un estudio nuevo para **Roosevelt y Camacho** y elegí **Simular con tráfico de muestra** con el mismo recorte regional y la misma versión de SUMO.
