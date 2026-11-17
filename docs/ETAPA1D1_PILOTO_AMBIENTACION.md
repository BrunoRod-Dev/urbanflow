# UrbanFlow · Etapa 1D.1 · Piloto de ambientación en Rambla Williman

Pilotó 241,2 m de Rambla Doctor Claudio Williman, entre los nodos OSM `840834845` y `2480679874`. La red, la demanda, los semáforos y las trayectorias certificadas no se tocaron. La ambientación es un archivo aparte y no entra a `netconvert`.

Se prueba con el mismo comando de siempre:

```text
python probar_sector01.py
```

La demostración abre la vista elevada sobre el tramo, en el segundo 301,5 de la corrida (05:01), siguiendo a `salida-miami-3` sobre el carril `482520536#8_0`. El botón Nivel de calle conserva el seguimiento cercano. El reproductor habitual, sin `?probar=1`, sigue abriendo el estudio; si es el Sector 01, la misma capa se dibuja al entrar a la vista 3D.

## Fuentes

La geometría sale de una consulta a la API de OpenStreetMap el 14/11/2026, 18:52:56 UTC:

`https://api.openstreetmap.org/api/0.6/map?bbox=-54.94225,-34.95265,-54.93815,-34.94975`

Licencia ODbL, [openstreetmap.org/copyright](https://www.openstreetmap.org/copyright). Hay que atribuir a los colaboradores de OpenStreetMap. La leyenda de la escena lo dice.

| Archivo | Papel | SHA-256 |
| --- | --- | --- |
| `urbanflow-web/assets/sector01-williman-osm.xml` | Vías y nodos usados, con sus identificadores. No reemplaza `maldonado.osm.gz` ni el recorte vial. | `b33e3fa74b56859f1df9822fe6baba9e3498f01e662bfdfe1d4e6a60e8e74f50` |
| `urbanflow-web/assets/sector01-williman-geography.json` | Capa que dibuja el visor. Incluye fecha, licencia, regla de altura y regla de arbustos. | `03240568e75a0a4caf3b0f8933b5b85db388a272edb7d3eac040e121fbc2acd3` |

La ventana geográfica es más ancha que los 241,2 m de calzada, para que entren la costa al oeste y los edificios de al lado. En orden oeste, sur, este, norte: `[-54.94225, -34.95265, -54.93815, -34.94975]`. Fuera de esa ventana sigue el plano verde anterior. No se ambientó el resto del Sector 01.

`tools/build_sector01_williman_geography.py` vuelve a armar esos dos archivos. No compila SUMO.

## Qué se dibujó

Las coordenadas usan la misma proyección que los vehículos (`fromGeo`). Las calzadas y las veredas siguen siendo las mallas certificadas, dibujadas encima del suelo nuevo.

| Clase | Elementos | Origen |
| --- | ---: | --- |
| Tierra | 1 rectángulo | Generado con el borde de la ventana. No es césped. |
| Mar | 1 polígono | Lado oeste de la vía `184791636` (`natural=coastline`), cerrado contra el borde de la ventana. Es una superficie derivada, no un polígono de agua relevado. |
| Arena | 1 polígono | Franja entre esa costa y el borde terrestre de la relación Playa Mansa `2503824` (`natural=beach`, `surface=sand`). |
| Césped | 15 polígonos | `landuse=grass`, recortados a la ventana y contra el mar y la arena. |
| Matorral | 3 polígonos | `natural=scrub`. |
| Arbustos | 101 | Regla declarada, no un relevamiento. Grilla de 7 m dentro del matorral, semilla 41, altura entre 0,7 y 1,4 m, con un desplazamiento aleatorio de hasta el 35 % del paso. |
| Edificios | 16 huellas | Solo las que intersectan la ventana. Ninguna de las 284 del rectángulo completo. |
| Línea de costa | 1 | La misma vía `184791636`, dibujada como borde. |

Los 16 edificios quedan así. No hay ninguna etiqueta `height` en el recorte: cero alturas medidas. Donde hay `building:levels`, la altura visual es plantas × 3,1 m y queda marcada como estimación. Sin plantas ni altura, el volumen es 2,8 m, con rayado, y queda marcado como provisional. Esas dos constantes están en `meta.heightRule` del JSON.

| Edificio | Vía OSM | Plantas | Altura visual |
| --- | --- | ---: | --- |
| Torre Alexander | `230052245` | 16 | 49,6 m, estimada |
| El Malecón IV | `275829938` | 19 | 58,9 m, estimada |
| Le Chat | `1526508174` | 9 | 27,9 m, estimada |
| Sin nombre, apartments | `1526508176` | 7 | 21,7 m, estimada |
| Hotel sin nombre | `458311823` | 6 | 18,6 m, estimada |
| Azteca | `1526508167` | 5 | 15,5 m, estimada |
| Edificio Los Arcos | `275829937` | 3 | 9,3 m, estimada |
| Casa | `1526508179` | 2 | 6,2 m, estimada |
| Casa | `1526508165` | 1 | 3,1 m, estimada |
| Casa | `1526508178` | 1 | 3,1 m, estimada |
| Sin nombre | `1526508175` | 1 | 3,1 m, estimada |
| Enjoy Punta del Este Resort & Casino | `70499221` | sin dato | 2,8 m, provisional |
| Club de Pesca de Punta del Este | `230776459` | sin dato | 2,8 m, provisional |
| Nuestra Señora de Fátima | `457991701` | sin dato | 2,8 m, provisional |
| Hotel sin nombre | `457991702` | sin dato | 2,8 m, provisional |
| Sin nombre | `1526508180` | sin dato | 2,8 m, provisional |

Once estimados, cinco provisionales, cero medidos. El rayado distingue a los provisionales desde la vista elevada.

## Capturas

Mismo instante, 05:01, mismo vehículo. Chrome en una ventana de 1440 × 900.

| | Calle | Elevada |
| --- | --- | --- |
| Antes | [antes-calle.png](../results/etapa1d1-piloto/antes-calle.png) | [antes-elevada.png](../results/etapa1d1-piloto/antes-elevada.png) |
| Después | [despues-calle.png](../results/etapa1d1-piloto/despues-calle.png) | [despues-elevada.png](../results/etapa1d1-piloto/despues-elevada.png) |

En la vista elevada el mar queda al oeste de la costa, la arena entre la costa y la rambla, el césped en los canteros mapeados y los edificios al este de la calzada. El auto sigue sobre el asfalto certificado. En la vista de calle se ve el vehículo, el césped del cantero y la tierra; el mar queda fuera del encuadre porque la cámara mira a lo largo de la rambla y la costa está a unos 125 m al costado.

## Rendimiento

Noventa cuadros con la corrida en marcha, después de cargar la escena. El percentil 95 no se movió. El máximo posterior es un solo cuadro.

| | p50 | p95 | máximo |
| --- | ---: | ---: | ---: |
| Antes, plano verde | 6,9 ms | 7,1 ms | 7,2 ms |
| Después, con el piloto | 6,9 ms | 7,2 ms | 41,7 ms |

No hubo excepciones de página. La geometría va en unas pocas mallas fusionadas, más una malla instanciada para los 101 arbustos. No se agregó ninguna dependencia nueva: Three.js y Clipper ya estaban en el visor.

## Límites

- La altura de 3,1 m por planta y el volumen de 2,8 m son reglas de dibujo. No son mediciones de Punta del Este.
- El agua es el lado del mar de la costa recortada. No se cargó la relación del Río de la Plata.
- Enjoy, el Club de Pesca, la capilla y otros dos edificios no tienen plantas. Su techo bajo y rayado no es la altura real.
- Los arbustos existen solo donde OSM marca matorral, y la posición de cada uno sale de la grilla declarada.
- No hay parque etiquetado, ni árboles relevados, ni LiDAR, ni modelo de elevación. El suelo del piloto es plano. Los carriles no se desplazan en altura.
- Fuera de la ventana el terreno sigue siendo el plano verde. El resto del Sector 01 y Solanas quedan como estaban.
- La vereda ancha sigue siendo la franja generada a partir de la calzada, no un relevamiento nuevo.

La ambientación del resto del Sector 01 no se hizo. El piloto queda acá.
