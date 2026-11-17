# UrbanFlow · Etapa 1C · Sector 01 Punta del Este → Mansa

**PASS CON OBSERVACIONES.** El sector quedó simulable con SUMO 1.26.0 como **candidato técnico**. Dos importaciones independientes produjeron la misma red semántica y dos corridas completaron los mismos 36 viajes con trayectorias idénticas. Los permisos de servicio, las prioridades, los programas semafóricos y la geometría observada en el reproductor requieren inspección antes de aceptar el sector como referencia vial. [Manifiesto](../results/etapa1c-sector01-validacion/manifest.json) · [Auditoría de la red](../results/etapa1c-sector01-validacion/network-audit.json)

## Delimitación y procedencia

El núcleo va del empalme peninsular `840834919` (`-54.9405228, -34.9577546`) al cruce de Pirineos `1761803640` (`-54.9424518, -34.9451265`). Son aproximadamente **1.452 m** por el eje OSM de ida. El sentido hacia la Mansa sigue `99944425 → 482520536 → 1346593267`. El sentido hacia la Península usa la calzada `164559876` y continúa por Rambla General Artigas `99944449`. El recorte incluye ambas calzadas, las aproximaciones al empalme peninsular, ambos cruces de Miami y margen para pasar Pirineos antes de terminar las sondas de la rambla. [Perímetro v002](ETAPA1B_PERIMETRO_CONSOLIDADO.md)

El único insumo vial fue el snapshot regional fijado del **10/11/2026, 21:21:39 UTC**, SHA-256 `868b473a814999649af1d03ba164be232320c9dd82a229d5514315c0afc3a272`. Se usó el lector regional existente para extraer vías completas y miembros de restricciones. En orden oeste, sur, este, norte, el rectángulo de extracción fue `[-54.945, -34.9618, -54.9358, -34.9429]`. El recorte contiene **1.521 nodos, 280 vías y cinco relaciones**, SHA-256 `33d5750cd247cac4301558ad7e7d5eef51a3efac7a0c79d9ca3f3335636736df`. [Extracto OSM](../results/etapa1c-sector01-validacion/01c20261113000000000000000000001/recorte.osm.xml)

La selección de compilación usa el siguiente polígono, en longitud y latitud. Al conservar tramos que intersectan el polígono, algunos extremos quedan fuera de él. El GeoJSON muestra el polígono y la extensión efectiva de los carriles.

```text
(-54.94415, -34.9608)
(-54.93640, -34.9608)
(-54.93640, -34.9488)
(-54.93700, -34.9488)
(-54.93700, -34.9437)
(-54.94415, -34.9437)
```

La esquina este conserva Emilio Sader hasta su empalme con avenida Francia y el giro restringido sobre Bulevar Artigas. El límite norte deja la conexión de avenida París fuera del área de prueba. La primera importación rectangular dejaba circular una secuencia de retorno que contradecía `18469702`. Con todos sus miembros presentes, SUMO 1.26.0 descartó esa relación mixta de varios miembros `via`. El polígono final no contiene los tramos necesarios para realizar esa secuencia. Antes de incorporar avenida París habrá que representar y probar la restricción completa. [Evidencia de los ensayos iniciales](../results/etapa1c-sector01-20261113/) · [Implementación del importador en SUMO 1.26.0](https://github.com/eclipse-sumo/sumo/blob/v1_26_0/src/netimport/NIImporter_OpenStreetMap.cpp#L2638-L2686)

El ensayo reutiliza las opciones de importación de UrbanFlow para conexiones, geometría y semáforos. Fija además procedencia por vía y conserva calles de servicio con un archivo de tipos local. El tipo portátil de fábrica para `highway.service` habilita reparto, peatones y bicicletas. Con el filtro de autos y ómnibus, el acceso `230776458` desaparecía. La variante local agrega permiso de auto al tipo, manteniendo los demás valores y las etiquetas OSM. Así se conservan los accesos para probarlos y el giro `7104488` puede verificarse con ambas vías presentes. El permiso por defecto se registra como supuesto en el manifiesto. El sector no requiere los archivos de corrección de Camacho ni los controles de Honduras. [Opciones efectivamente ejecutadas](../results/etapa1c-sector01-validacion/01c20261113000000000000000000001/netconvert-command.json) · [Importación OSM de SUMO](https://eclipse.dev/sumo/docs/Networks/Import/OpenStreetMap.html)

## Cruces, carriles y controles

La red tiene **626 aristas dirigidas, 789 carriles exteriores, 317 nodos exteriores, 1.240 conexiones exteriores por carril y 23 programas actuados inferidos por SUMO**. Los tres tramos principales `482520536`, `1346593267` y `164559876` conservan los dos carriles y los 60 km/h etiquetados en OSM. La entrada peninsular `99944425` conserva los 50 km/h y SUMO asigna un carril por tipo de vía.

| Punto | Sentidos y conexiones de la red compilada |
|---|---|
| Empalme peninsular `840834919` | El Remanso e Inzaurraga conectan con Williman. El programa agrupado es inferido. El sentido hacia el sur continúa por `1761803535` a Rambla General Artigas. |
| Emilio Sader `1918169993` | Salida de sentido único desde el carril derecho de Williman. Los dos carriles rectos continúan hacia Mansa. SUMO asigna prioridad en el nodo. |
| Miami `1918169990` y `1761803419` | Dos empalmes distintos con un tramo OSM común entre calzadas. La red conserva incorporaciones y salidas según cada nodo. La sonda hacia el sur observó la incorporación 0 → 1. |
| El Pinar `1761803556` | Calle de sentido único hacia Williman. La incorporación entra al carril 0 de Mansa. Control `GS_1761803556` inferido. |
| Pirineos `1761803640` | Calle de doble sentido con entrada al carril 0 hacia Mansa y salida desde ese carril. Los dos carriles rectos atraviesan el cruce. SUMO asigna prioridad. |
| Servicio `1957626365` | Entrada y salida local con programa agrupado inferido. El giro directo `482520536#15 → 230776458` está ausente y SUMO lo rechazó con código 1 en un ensayo negativo. |

Los empalmes auditados están sustentados por nodos OSM compartidos. El cotejo del conjunto de conexiones, incluyendo los IDs originales de tramos fusionados, dio **cero conexiones sin procedencia resuelta** y **cero aristas en contra de un sentido OSM explícito o de rotonda**. Hay 15 terminales dirigidas en accesos o extremos de la selección. Ninguna cae en los ocho nodos de control del núcleo. El nodo semafórico periférico `2804978473` quedó como entrada sin movimiento controlable por el recorte, y SUMO descartó su programa.

Los **dos anillos compilados** forman ciclos dirigidos con continuidad verificada. El explícito de Bulevar Artigas tiene nueve tramos SUMO. SUMO recompuso su clasificación después de simplificar la geometría. El de avenida Francia tiene diez tramos y la clasificación de rotonda es heurística. En un ensayo con la heurística desactivada, el de Francia dejó de figurar como rotonda y SUMO avisó que el anillo explícito tenía una referencia a un tramo absorbido por la simplificación. Se conservó la importación que produce los dos ciclos completos. La prioridad física de avenida Francia queda pendiente. [Ensayo sin heurística](../results/etapa1c-sector01-20261113/diagnostico-poligono-sin-heuristica/netconvert.log)

De las cinco restricciones del extracto, se comprobó la ausencia de los tres giros prohibidos con ambos tramos compilados (`6666686`, `7104488`, `13211345`). Las dos relaciones descartadas por SUMO corresponden a un movimiento fuera de la selección oriental (`2468855`) y al retorno de París (`18469702`). Los carriles, sentidos y restricciones se cotejaron con el snapshot. Las flechas pintadas, las fases reales, las prioridades de los cruces y los permisos locales requieren corroboración física. De las 176 vías OSM representadas, 126 carecen de carriles explícitos, 135 de velocidad máxima y las 176 de flechas por carril. [Control negativo del giro prohibido](../results/etapa1c-sector01-validacion/control-negativo/sumo.log)

## Dos compilaciones independientes

Se usaron los ejecutables portátiles oficiales de Windows x64 en `results/baseline-v001-tools/portable/sumo-1.26.0/bin`. Ambos devolvieron **Eclipse SUMO 1.26.0**, compilación MSVC 19.29.30133.0 Release. [Versión de netconvert](../results/etapa1c-sector01-validacion/netconvert-version.txt) · [Versión de SUMO](../results/etapa1c-sector01-validacion/sumo-version.txt)

| Binario o artefacto | SHA-256 |
|---|---|
| `netconvert.exe` | `4174c17db813d413c85cdf7ad99a5f59b537ddf80f8caac9e1dfe87a35cb6b51` |
| `sumo.exe` | `dcdbf4fe1f8268816cda2d0631d407fd8e63b0cad5f3e57fe9cf235d9dece926` |
| Red A | `4ca6c765b519693b9671f3eb766a695de7f0fcc09ff79b01630227fe1d3f2ede` |
| Red B | `631d5fb94726850e60505b2be845ab80cfd3444dfdc68252853b71d6fd07752d` |

A y B se construyeron desde dos extracciones independientes del mismo snapshot. Las extracciones tuvieron la misma huella. La comparación estricta de baseline coincidió en **proyección, aristas y carriles, geometría, nodos y matrices de conflicto, conexiones y visibilidad, programas y rotondas**. También coincidió el árbol XML completo de las redes al parsearlo. Las huellas de los archivos brutos difieren por la cabecera de generación. [Comparación y huellas por componente](../results/etapa1c-sector01-validacion/semantic-comparison.json) · [Red A](../results/etapa1c-sector01-validacion/01c20261113000000000000000000001/network.net.xml) · [Red B](../results/etapa1c-sector01-validacion/repeticion-b/network.net.xml)

## Circulación y limitaciones observadas

Se ejecutó la misma demanda en cada red, con **12 itinerarios y tres autos por itinerario**, semilla 42, paso de 0,5 s y horizonte de 540 s. Las sondas recorrieron la rambla en ambos sentidos, usaron ambos carriles en pasos rectos y cubrieron la salida por Emilio Sader, las incorporaciones y salida por Miami, la incorporación de El Pinar, la entrada y salida de Pirineos y la entrada y salida del servicio. Antes de correr se comprobó que cada itinerario tiene una cadena de conexiones permitida desde su carril inicial. Las trayectorias registraron directamente el paso 0 → 0 y 1 → 1 en una conexión recta de cada sentido. [Demanda reproducible](../results/etapa1c-sector01-validacion/01c20261113000000000000000000001/routes.rou.xml) · [Sondas observadas por carril](../results/etapa1c-sector01-validacion/lane-observations.json)

En cada corrida **36 autos ingresaron y 36 terminaron**, sin vehículos pendientes, colisiones registradas, teletransportes ni errores de ruta. Se habilitó la comprobación de colisiones dentro de los cruces. Hubo 7.430 muestras de vehículos por corrida. El último viaje terminó a los 419,5 s. La mayor detención continua muestreada fue de 43,5 s y el máximo de espera acumulada por viaje fue de 54 s. Las trazas mantuvieron el orden de las aristas planificadas. Para enlaces muy cortos que caen entre muestras, se verificaron los extremos con los carriles de partida y llegada de `tripinfo`. Coincidieron trayectorias, viajes, estados de los 23 controladores, reporte de colisiones y resumen, excluyendo del resumen sólo el tiempo de cómputo de cada paso. [Resultado por vehículo](../results/etapa1c-sector01-validacion/01c20261113000000000000000000001/simulation-result.json) · [Comparación dinámica](../results/etapa1c-sector01-validacion/simulation-comparison.json)

El diagnóstico geométrico marca **cinco conexiones rectas con retroceso local de 1,02 a 2,33 m**, dos en Williman en `2535807404`, una en servicio y dos en Bulevar Artigas. Las sondas pasaron por las dos de Williman y por la de servicio. Se conservó esa evidencia para verificar si el desplazamiento resulta visible en el reproductor. Las advertencias de radios reducidos y retornos ambiguos en dos nodos de estacionamiento permanecen en el log. Son observaciones del candidato. Esta demanda pequeña no mide capacidad ni valida tiempos o colas reales. [Advertencias de compilación](../results/etapa1c-sector01-validacion/01c20261113000000000000000000001/netconvert.log)

## Cómo probarlo

Desde PowerShell, en la raíz de UrbanFlow, ejecutá este comando. Abre el reproductor existente en el navegador con una instancia local que apunta al directorio aislado del sector.

```powershell
python -B results/etapa1c-sector01-validacion/abrir_replay.py
```

En **Mapa 2D**, reproducí la corrida desde el inicio. Mirá ambos sentidos de Williman, la salida a Emilio Sader, las incorporaciones en Miami y El Pinar y los movimientos de Pirineos. Revisá en particular si los autos parecen retroceder en el nodo `2535807404`, cerca de `[-54.9400194, -34.9510786]`. Los colores del mapa reproducen los estados estimados de SUMO. Se verificaron las respuestas del servidor existente para la página, el estudio, los datos de reproducción y los datos de escena mediante el manejador HTTP en memoria. La conexión de prueba por el puerto local recibió `WinError 10013` desde este entorno. Queda pendiente verificar el renderizado en el navegador del usuario.

También podés abrir [la vista GeoJSON del sector](../results/etapa1c-sector01-validacion/sector01.geojson). La propiedad `kind` diferencia carriles, conexiones, señales, cruces auditados y límite. Para correr directamente en SUMO GUI con el portátil del proyecto, prepará una copia nueva y presioná **Play**. Las salidas de tu prueba se escribirán en esa copia.

```powershell
$src = 'results/etapa1c-sector01-validacion/01c20261113000000000000000000001'
$guiRun = (New-Item -ItemType Directory ('results/etapa1c-sector01-gui-' + [guid]::NewGuid().ToString('N'))).FullName
foreach ($name in 'network.net.xml','routes.rou.xml','signals.add.xml','sector01.sumocfg') {
    Copy-Item -LiteralPath "$src/$name" -Destination $guiRun
}
& '.\results\baseline-v001-tools\portable\sumo-1.26.0\bin\sumo-gui.exe' -c "$guiRun/sector01.sumocfg"
```

Para repetir ambas compilaciones y simulaciones en otra carpeta exclusiva:

```powershell
$out = 'results/etapa1c-sector01-local-' + [guid]::NewGuid().ToString('N')
python -B results/etapa1c-sector01-20261113/reproducir.py $out
```

## Regresiones y estado de entrega

Pasaron **11 pruebas del compilador 1A, 9 de baseline histórica estricta y 9 de inventario regional**, sin omisiones. Coincidieron los nombres y SHA-256 de los **93 archivos históricos** de los cuatro estudios. Se cotejaron además las dos redes finales de 1A y los cuatro archivos de inventario v001/v002. H03 y H06 conservan sus pruebas de caracterización. Los scripts de ensayo y reproducción están en directorios de evidencia bajo `results/`. [Integridad](../results/etapa1c-sector01-validacion/integridad-referencias.json) · [Contrato 1A](../results/etapa1c-sector01-validacion/regresion-1a.log) · [Baseline estricta](../results/etapa1c-sector01-validacion/baseline-estricta.log) · [Inventario](../results/etapa1c-sector01-validacion/regresion-inventario.log)
