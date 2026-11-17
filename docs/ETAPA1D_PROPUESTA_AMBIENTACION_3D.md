# UrbanFlow · Etapa 1D · Propuesta de ambientación 3D

Análisis del 14/11/2026. No implementa terreno, edificios ni cambios de cámara. No modifica SUMO, los reproductores ni las geometrías certificadas del Sector 01. La simulación no se extiende hacia Solanas ni hacia el Sector 02.

El verde uniforme de la vista 3D es la malla `street-ground`: un plano del color `0x8d9e73`, con textura de césped, que sobresale 320 m del recuadro de la escena. Las calzadas, las veredas generadas, los cordones, los canteros y las marcas van encima. El Sector 01 entra a esa escena sin huellas de edificios, porque el interruptor que carga huellas está reservado al piloto Roosevelt–Camacho. Todo lo que no es calzada, vereda o cantero queda pintado como césped.

## 1. Inventario de datos disponibles y faltantes

### Lo que ya usa el Sector 01

El snapshot regional es `sumo_scenario/regional/maldonado.osm.gz`, del 10/11/2026 21:21:39 UTC, SHA-256 `868b473a814999649af1d03ba164be232320c9dd82a229d5514315c0afc3a272`. Al construirlo solo se conservan vías con `highway` o con una superficie que el código reconoce como cantero o vereda. El archivo resultante tiene 34.935 nodos, 6.031 vías y 51 relaciones. De esas vías, 6.027 tienen `highway` y 4 son `area:highway=footway`. No hay ninguna etiqueta `building`, `natural`, `landuse`, `leisure`, `height` ni `building:levels`.

El recorte certificado del Sector 01 sale de ese snapshot. Tiene 1.521 nodos, 280 vías y 5 relaciones, SHA-256 `33d5750cd247cac4301558ad7e7d5eef51a3efac7a0c79d9ca3f3335636736df`. Las 280 vías tienen `highway`. El rectángulo de extracción, en orden oeste, sur, este, norte, es `[-54.945, -34.9618, -54.9358, -34.9429]`.

En ese recorte hay calles, dos calzadas de Rambla Doctor Claudio Williman, veredas y senderos ya importados como vías, y catorce vías con la etiqueta `sidewalk`. Williman mismo no trae `sidewalk`. La vista 3D igual dibuja una vereda: la genera como una franja de ancho fijo alrededor de la calzada certificada, y la omite solo donde OSM dice `sidewalk=no`. Esa franja es una convención de dibujo. No es un relevamiento de la vereda.

Los canteros salen de `area:highway=traffic_island`, de cordones cerrados o de rotondas. El clasificador no conoce agua, arena, playa, parque ni césped. Por eso el plano verde no distingue el mar de un jardín.

### Edificios, costa y suelo en OSM actual

Esos datos no están en el snapshot. Se consultaron el 14/11/2026 en la API pública de OpenStreetMap, cuatro días después del snapshot. El conteo del sector corresponde a vías que intersectan el rectángulo, leídas en dos bandas y unidas por identificador. No es el archivo certificado y no debe entrar a `netconvert`.

| Dato en el rectángulo del Sector 01 | Vías |
| --- | ---: |
| `building` | 284 |
| con `building:levels` | 90 |
| sin `building:levels` | 194 |
| con `height` | 0 |
| `landuse=grass` | 77 |
| `landuse=residential` | 8 |
| `landuse=meadow` | 1 |
| `landuse=recreation_ground` | 1 |
| `natural=wood` | 6 |
| `natural=coastline` | 5 |
| `natural=scrub` | 3 |
| `leisure` (piscina, cancha, estación de ejercicio) | 5 |

Los tipos de edificio más frecuentes son `yes` (157), `apartments` (67), `commercial` (14), `house` (13), `roof` (8), `hotel` (8) y `retail` (8). El conteo es de vías. No se contaron relaciones multipolígono de edificios, así que un edificio dibujado solo como relación no está en las 284.

No aparece `leisure=park` ni `leisure=garden`. No aparece `natural=beach` ni `natural=sand` como vía. La arena de este tramo está en una relación, no en una vía suelta. No hay una altura medida: los 90 pisos etiquetados son un número de plantas, no metros.

### Qué falta para cerrar el territorio

- Agua local. La relación «Río de la Plata» (`natural=water`) cruza la zona, pero es el estuario entero. No hay un polígono de agua recortado al sector. El agua de una vista tendría que construirse del lado del mar de la línea de costa, y esa superficie sería una derivación, no un polígono relevado de la manzana.
- Arena. Existe la relación «Playa Mansa» (`natural=beach`, `surface=sand`). Está verificada en el tramo piloto. No está verificada como cobertura de todo el rectángulo del sector: el extremo sur, hacia la península, puede ser otra costa.
- Parques con nombre o contorno propio. En el rectángulo hay césped, matorral y una estación de ejercicio. No hay un parque etiquetado.
- Alturas de edificio. Cero vías del rectángulo traen `height`. Ciento noventa y cuatro no traen plantas. La fórmula ya escrita para Roosevelt —plantas por 3,1 m, o 6 m si faltan las plantas— es una convención de código. No es una medición de Punta del Este.
- Modelo de elevación de esta celda. La IDE publica un MDT nacional de 2,5 m y, para más de ochenta centros poblados, un MDS de 10 cm. No se identificó ni se descargó la hoja que cubre este tramo. No hay un LiDAR abierto verificado para esta costa.
- Árboles. En la ventana del piloto no había nodos con etiquetas de árbol.
- Vereda medida. La franja actual es un desplazamiento de la calzada. Los senderos de la rambla que ya están en el recorte siguen siendo vías de SUMO; su superficie `grass_paver` no cambia el material 3D.

## 2. Fuentes geográficas y licencias

| Fuente | Qué se verificó | Licencia y uso |
| --- | --- | --- |
| Snapshot Geofabrik del 10/11/2026, ya filtrado a vías | Calles del Sector 01. Sin edificios, costa ni usos del suelo. | ODbL, la misma que declara `coverage.json`: [openstreetmap.org/copyright](https://www.openstreetmap.org/copyright). |
| API de OSM, consulta del 14/11/2026 | 284 edificios del rectángulo, costa, Playa Mansa, césped y matorral del piloto. | ODbL. Hay que atribuir a los colaboradores de OpenStreetMap. Un extracto nuevo es una base derivada y tiene que quedar fechado, separado del recorte vial certificado. |
| IDE Uruguay, catálogo de datos abiertos, ficha actualizada el 26/08/2026 | Ortofotos y MDT nacional de 2,5 m, vuelo aerofotogramétrico 2017–2018, cámara UltraCam, hojas de unos 5 km. El MDT publicado en LAS es esa grilla, no un LiDAR. | Licencia de Datos Abiertos de Uruguay. AGESIC es la titular indicada en la ficha del MDT. No se descargó la hoja de este punto. |
| IDE, proyecto cerrado en octubre de 2019 | Cobertura nacional a 32 cm y, en más de ochenta centros poblados, imagen de 10 cm, MDT y MDS. El MDS describe terreno más construcciones. | Misma política de datos abiertos del geoportal. No se comprobó que la hoja de 10 cm de Punta del Este esté publicada para esta coordenada. |
| Intendencia de Maldonado, `Padrones_Urbanos` | 18 polígonos de padrón en el sobre `-54.9412, -34.9532, -54.9388, -34.9490`. Tienen número de padrón y área. No tienen altura ni cota (`HasZ: false`). | El visualizador advierte que la base se actualiza y que el usuario debe verificarla. No se encontró una licencia de reutilización. Un padrón es una parcela, no la planta de un edificio. |
| `Info_Playa` de la misma intendencia | El servicio de entidades respondió error 500 al leer la capa. | Queda sin verificar. No se usa en esta propuesta. |
| Google Street View | No se consultó. | Queda fuera. No aporta el contorno ni la altura que ya pueden venir de OSM y de la IDE. |

No hay, en lo consultado, un LiDAR abierto de esta costa. El producto de 0,1 m que aparece en el catálogo de la IDE es fotogrametría urbana; el ejemplo revisado es una hoja de Montevideo. Eso no acredita cobertura sobre Rambla Williman.

## 3. Arquitectura mínima

Cinco capas, y un solo sentido de dependencia: la geografía y los edificios se dibujan alrededor de la red ya certificada. Ninguna escribe en la red, en la demanda ni en las trayectorias.

| Capa | Responsabilidad | Dónde vive |
| --- | --- | --- |
| SUMO | Carriles, conexiones, velocidades y vehículos. | Red y replay certificados. No se recompilan. |
| Geografía | Costa recortada, agua derivada de esa costa, arena de Playa Mansa, césped y matorral. | Un archivo estático nuevo, solo del piloto, cargado al dibujar. No pasa por `netconvert`. |
| Arquitectura | Huellas de edificio. Extrusión solo donde hay plantas o `height`, marcada como estimación cuando la altura sale de las plantas. | El mismo archivo, dibujado con las mallas fusionadas que ya arman muros y techos. |
| Ambientación | Árboles, faroles, mobiliario, cuando exista una posición de origen. | Más adelante. En este tramo OSM no trae árboles. No se inventan posiciones. |
| Visualización | Cámaras, vehículos y reproducción. | El reproductor actual. La cámara de calle y la elevada ya siguen al vehículo. |

El plano `street-ground` deja de representar el territorio. Adentro de la ventana del piloto queda un suelo neutro, y encima solo los polígonos que tienen clase: agua, arena, césped, matorral. La calzada certificada se dibuja después y tapa lo que se superponga. El césped de OSM que cruce la calzada se recorta contra el asfalto, igual que hoy se recorta una huella que pisa la vereda.

Los edificios del Sector 01 no deben activarse con el interruptor de Roosevelt. Ese interruptor también cambia cámaras y leyendas de otro cruce. El piloto necesita su propio archivo de huellas.

La altura, si más adelante se usa el MDT, es solo visual. Los carriles siguen en la cota en la que están certificados. Un MDS trae techos además de suelo: usarlo a la vez que las extrusiones de OSM contaría dos veces el edificio. Para el piloto alcanza el suelo plano, porque no hay una diferencia de cota verificada y la red no se puede deformar.

No hace falta un motor GIS ni un globo. Las mallas de la calle ya fusionan polígonos en unos pocos objetos. La geografía entra por el mismo camino: un objeto por clase de superficie y, para los edificios, las tres mallas que ya existen (zócalo, muro, techo).

Escala. El piloto no necesita nivel de detalle. El Sector 01, con 284 huellas, sigue siendo una malla estática fusionada; el costo está en recortar al cargar, no en cada cuadro. Hacia Maldonado–Punta del Este–La Barra se carga el archivo geográfico del sector que se está viendo, se fusiona y se sueltan las extrusiones al salir del sector. La región vial ya está partida por sectores. La ambientación acompaña ese corte. Un MDT de 2,5 m cubre unos cuatro millones de muestras por hoja de 5 km: queda fuera del piloto y, en la región, se muestrearía grueso y solo en el sector activo.

## 4. Sector piloto recomendado

Tramo de Rambla Doctor Claudio Williman sobre la vía certificada `482520536`, entre dos nodos del recorte:

| | Nodo | Longitud, latitud | Distancia sobre la vía |
| --- | --- | --- | ---: |
| Inicio | `840834845` | `-54.940021, -34.952177` | 509,9 m |
| Fin | `2480679874` | `-54.940156, -34.950015` | 751,1 m |

Son **241,2 m**. El nodo anterior está 136 m más al sur, y usarlo alargaría el tramo a 377 m. Por eso el corte queda entre estos dos nodos.

Entra en el tramo, sin tocar su geometría:

- Las dos calzadas. El replay certificado contiene carriles de `482520536` y de `164559876`.
- Los nodos ya corregidos `2535807404` (632,1 m) y `1957626407` (637,1 m). El piloto los muestra y no los vuelve a editar.
- El cruce de servicio `1957626365` queda 16 m al norte del fin. No hace falta incluirlo para ver costa y edificios.

La costa está al oeste de la rambla. En las muestras medidas, la línea de costa pasa a unos **121–129 m** del eje. El borde de tierra de la relación Playa Mansa, en los nodos de la vía `186169893` a esta latitud, queda a unos **60–80 m** al oeste del eje y a unos **45–65 m** al este de la línea de costa. Entre el agua y ese borde está la arena etiquetada. Entre ese borde y la rambla, la ventana consultada trae césped (`landuse=grass`), matorral (`natural=scrub`) y el Club de Pesca. Esos polígonos no están en el recorte vial: se buscaron la costa, el borde de la playa, un césped y un matorral, y ninguno está entre las 280 vías.

Edificios de la consulta del 14/11/2026 cuyo centro cae en la latitud del tramo. La planta es la etiqueta OSM, no una altura medida. Ninguno tiene `height`.

| Edificio | Vía | Tipo | Plantas |
| --- | --- | --- | --- |
| Torre Alexander | `230052245` | `yes` | 16 |
| Le Chat | `1526508174` | `apartments` | 9 |
| Sin nombre | `1526508176` | `apartments` | 7 |
| Hotel sin nombre | `458311823` | `hotel` | 6 |
| Azteca | `1526508167` | `apartments` | 5 |
| Edificio Los Arcos | `275829937` | `apartments` | 3 |
| Casa | `1526508165` | `house` | 1 |
| Sin nombre | `1526508175` | `yes` | 1 |
| Enjoy Punta del Este Resort & Casino | `70499221` | `yes` | sin dato |
| Club de Pesca de Punta del Este | `230776459` | `yes` | sin dato |
| Nuestra Señora de Fátima | `457991701` | `chapel` | sin dato |

El Malecón IV (`275829938`, `apartments`, 19 plantas etiquetadas) está unos 32 m al sur del nodo de inicio. Se puede incluir en el recorte geográfico de contexto. No alarga los 241,2 m de rambla.

Las cámaras actuales miran a lo largo del vehículo, con un campo vertical de 47°. El mar queda al costado, no adelante. La cámara elevada lo alcanza con más facilidad que la de calle. Si al implementar el mar quedara fuera del encuadre, el ajuste es de la cámara, no de la red.

## 5. Etapas de implementación

De menor a mayor dificultad. Cada etapa se autoriza aparte. Ninguna recompila SUMO.

1. **Suelo clasificado del tramo de 241 m.** Extraer y fijar, con fecha, la costa recortada, el polígono recortado de Playa Mansa, el césped y el matorral. Dibujarlos por clase. Sustituir el césped infinito dentro de la ventana por un suelo neutro. La calzada certificada queda encima. El agua es el lado del mar de la costa recortada y se etiqueta como superficie derivada.
2. **Huellas del mismo recorte.** Extruir solo las vías que tienen `building:levels` o `height`, y rotular la altura como estimación cuando sale de las plantas. Enjoy, el Club de Pesca y la capilla se dibujan como planta, sin metros inventados. No se usa el valor de 6 m.
3. **Veredas y senderos, sin rehacerlos.** Se mantiene la franja generada como convención de la calzada. Los senderos que ya están en la red siguen en la red. No se importa de nuevo `257042691` ni `257042705`.
4. **Revisión visual con las dos cámaras**, sobre un vehículo que ya recorre este tramo en el replay certificado. Si el mar no entra en cuadro, recién ahí se propone un desplazamiento lateral de la cámara.
5. **Identificar la hoja IDE** de este punto, MDT de 2,5 m, y leer su licencia de descarga. Solo después, y solo como malla visual que no mueva carriles. El MDS de 10 cm espera a comprobar que la hoja existe; no se suma a las extrusiones de OSM.
6. **Repetir el archivo geográfico por sector**, hasta la región ya cubierta por el snapshot vial. Sin nueva simulación hacia Solanas. Sin LiDAR mientras no haya una hoja verificada. Sin Street View.

## 6. Riesgos técnicos y rendimiento esperado

El extracto geográfico que entre a `netconvert` cambiaría la red certificada. El archivo del piloto se carga solo en el dibujo y conserva los identificadores de las vías OSM para poder auditarlo.

Recortar mal Playa Mansa o el Río de la Plata cargaría kilómetros de costa. La relación del estuario tiene cientos de miembros. El archivo del piloto guarda el recorte ya cerrado sobre la ventana, no la relación completa.

El césped etiquetado pisa la rambla en varios polígonos. Si no se recorta contra el asfalto, tapa carriles y vehículos. El orden de dibujo es suelo, clases, calzada.

Las plantas de Torre Alexander (16) y, si entra en el contexto, El Malecón IV (19) dominan la escena y son una etiqueta, no un certificado. Mostrarlas como medición sería inventar la altura. Lo mismo vale para los 194 edificios del sector que no tienen plantas: un valor por defecto fabricaría un perfil urbano.

La consulta en vivo es cuatro días posterior al snapshot. Al implementar se fija un extracto con fecha y hash. No se asume que siga igual que esta tabla.

Los 18 padrones de la intendencia no reemplazan huellas. Usarlos como edificios desplazaría las construcciones al contorno de la parcela.

Rendimiento esperado, con la fusión de mallas que el visor ya usa:

| Alcance | Qué se dibuja | Cuadro |
| --- | --- | --- |
| Piloto, 241 m | Unas 11 huellas, el césped y el matorral de la ventana, una playa recortada y una costa recortada. Un objeto por clase. | El costo nuevo es al cargar. El movimiento de los vehículos no cambia. No hace falta nivel de detalle. |
| Sector 01 | 284 huellas como una malla de muros y una de techos. | Sigue siendo estático. Hay que medir el recorte al cargar, no el cuadro. |
| Región | Un sector geográfico a la vez, el que ya corresponde a la simulación abierta. | Sin esto, una relación de costa o una hoja de MDT de 5 km se llevan el presupuesto. El MDT no entra en el piloto. |

La cantidad de edificios de toda la franja Maldonado–La Barra no se contó. El snapshot vial de esa franja tiene 6.031 vías de circulación y cero edificios, porque el filtro los dejó afuera. Extrapoliar las 284 del Sector 01 al resto sería inventar el censo.

## Cierre

Hay datos reales para un primer tramo reconocible: 241,2 m de Rambla Williman, con vehículos ya simulados, edificios con planta etiquetada, césped, matorral, arena de Playa Mansa y la línea de costa a unos 125 m al oeste. No hay alturas medidas, no hay parque etiquetado, no hay LiDAR verificado y el mar local hay que derivarlo de la costa.

La implementación del piloto queda a la espera de autorización.
