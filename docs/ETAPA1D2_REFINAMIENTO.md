# UrbanFlow · Etapa 1D.2 · Refinamiento del piloto Williman

Se ajustó la lectura visual del piloto de 241,2 m. La red, los vehículos y las trayectorias no se tocaron. El mar, la arena, el césped y la costa conservan la geometría ya validada. No se amplió el área ni se bajaron datos nuevos.

Se sigue abriendo con:

```text
python probar_sector01.py
```

## Qué cambió

El aviso de la cámara dice ahora «fuera de la cámara» y aclara que el vehículo sigue en la simulación. A los 301,5 s, siguiendo a `salida-miami-3`, la vista elevada informa 11 y la de calle informa 3. Son las mismas cantidades de antes; el texto ya no se puede leer como si hubieran salido de la corrida.

Las 16 huellas usan el anillo completo de su vía OSM. Las 16 vías estaban cerradas y con todos sus nodos en el extracto, así que no hubo que reconstruir ni inventar ningún tramo. Tres cruzan el borde de la ventana y antes quedaban cortadas: Enjoy `70499221`, la vía `457991702` y la vía `1526508180`. El identificador `osmId` es el de la vía; si la misma vía volviera a entrar en otro sector, el dibujo la toma una sola vez. No había relaciones de edificio en el extracto: ninguna huella quedó incompleta por un hueco sin datos.

Los 11 edificios con `building:levels` siguen en plantas × 3,1 m, marcados como estimación. Los 5 sin plantas ni `height` ya no se extruyen a 2,8 m. Se dibujan como huella rayada y un contorno sobre el suelo. El contorno está a 18 cm solo para no quedar tapado por la vereda; no es una altura del edificio.

Los arbustos siguen siendo 101, en las mismas posiciones, con la semilla 41 y la grilla de 7 m. Cada uno tiene dos conos superpuestos y un radio que sale de esa misma altura sorteada y de su posición.

## Fuentes

| Archivo | SHA-256 |
| --- | --- |
| `urbanflow-web/assets/sector01-williman-osm.xml` | `b33e3fa74b56859f1df9822fe6baba9e3498f01e662bfdfe1d4e6a60e8e74f50` |
| `urbanflow-web/assets/sector01-williman-geography.json` | `f1017d58aa9b63ff15d5707893b5b9c64c88716f405a431301f2261537071124` |

El hash del extracto no cambió. La fecha de la consulta sigue siendo 2026-11-14T18:52:56Z. El JSON cambió porque las tres huellas recuperaron los vértices que estaban fuera de la ventana.

## Capturas

Mismo instante, 05:01, mismo vehículo, mismas dos cámaras. Chrome en 1440 × 900.

| | Calle | Elevada |
| --- | --- | --- |
| Antes | [antes-calle.png](../results/etapa1d2-piloto/antes-calle.png) | [antes-elevada.png](../results/etapa1d2-piloto/antes-elevada.png) |
| Después | [despues-calle.png](../results/etapa1d2-piloto/despues-calle.png) | [despues-elevada.png](../results/etapa1d2-piloto/despues-elevada.png) |

En la vista elevada, Enjoy y las otras huellas sin altura quedan en el suelo, con el borde oscuro, y las torres con plantas siguen en pie. En la de calle desaparece el muro rayado del horizonte; el auto sigue sobre el asfalto certificado. El mar, la arena y el césped se ven como en la captura anterior.

## Rendimiento

Noventa cuadros, con la reproducción en marcha y la cámara de calle, el mismo método en las dos pasadas.

| | p50 | p95 | máximo |
| --- | ---: | ---: | ---: |
| Antes | 6,9 ms | 7,1 ms | 7,9 ms |
| Después | 7,0 ms | 7,9 ms | 13,9 ms |

El percentil 95 sube menos de 1 ms. El máximo es un cuadro. No hubo excepciones. La escena sigue cargando este tramo como un grupo aparte del tráfico.
