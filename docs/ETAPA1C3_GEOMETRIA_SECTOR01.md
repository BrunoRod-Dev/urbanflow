# UrbanFlow · Etapa 1C.3 · Geometría del Sector 01

**PASS parcial de la candidata geométrica.** Cuatro de las cinco conexiones quedaron corregidas en una copia reproducible del Sector 01. El acceso de servicio en `2480679873` conserva 2,33 m de retroceso y sigue pendiente. La candidata queda aislada para revisión y la certificación integral sigue bloqueada. [Red candidata](../results/etapa1c3-sector01/candidato-local/a/network.net.xml) · [Comparación completa](../results/etapa1c3-sector01/candidato-local/comparacion.json)

## Causa y alcance

Con el snapshot y netconvert 1.26.0 portátiles fijados en 1C, la compilación de control reprodujo el árbol XML de la red original. En las cinco alertas, la conexión interna une exactamente el fin del carril entrante con el inicio del saliente. La proyección sobre el rumbo medio de ambos accesos muestra que esos extremos quedaron en orden inverso después de recortar las formas de los carriles.

En Williman y Bulevar Artigas, el carril exterior de salida queda reducido a **0,20 m**, con el siguiente nodo a **4,95 m** y **2,21 m**, respectivamente. Los polígonos vecinos invaden el tramo corto. En servicio, el tramo de **0,20 m** está del lado entrante. Su extremo lo comparte el enlace interno del cruce precedente. El código de netconvert contempla el solapamiento de polígonos y tiene un caso de recorte y reversión de tramos cortos. El efecto local está demostrado por la compilación controlada. La decisión interna exacta del algoritmo para cada nodo queda como inferencia. [Código de SUMO 1.26.0](https://github.com/eclipse-sumo/sumo/blob/v1_26_0/src/netbuild/NBEdge.cpp#L772-L858)

## Corrección ensayada

La candidata usa un generador aislado. Detecta conexiones rectas invertidas con tramo saliente reducido a 0,20 m. Recorta los polígonos existentes de los dos nodos con un plano transversal en el punto medio y un margen de 0,10 m por lado. Rechaza polígonos partidos o vacíos. Genera un archivo PlainXML y recompila con los mismos insumos. Restaura en una segunda pasada las cinco velocidades efectivas de enlaces internos que netconvert había recalculado al cambiar su curvatura. Los IDs se obtienen de la red y aparecen en los datos generados. No hay excepciones por nombre de calle ni de vehículo. [Generador](../results/etapa1c3-sector01/candidato.py) · [Polígonos](../results/etapa1c3-sector01/candidato-local/a/geometry.nod.xml) · [Velocidades](../results/etapa1c3-sector01/candidato-local/a/speeds.con.xml) · [Referencia PlainXML](https://eclipse.dev/sumo/docs/Networks/PlainXML.html)

Las dos compilaciones independientes de la candidata coinciden como árbol XML. Mantienen topología, permisos, índices semafóricos, programas, prioridades, matrices de conflictos, visibilidad y rotondas. Cinco conexiones pasan a declarar explícitamente una velocidad que coincide con la velocidad previa del carril interno. Se verificó esa igualdad antes de aceptar la diferencia de representación. Cambian la geometría de cuatro polígonos y la forma o longitud de 26 carriles, incluidos movimientos vecinos. Las cinco uniones auditadas conservan continuidad entre extremos con separación de 0 m al nivel de precisión del XML.

Las variantes globales de forma mínima llegaron a quitar las cinco alertas, pero cambiaron de 1.734 a 1.727 aristas totales, de 2.512 a 2.505 conexiones y de 23 a 26 programas. La forma basada en extremos, el radio pequeño y el corte rectangular dejaron los cinco casos. Los rectángulos locales llegaron a resolver los cuatro casos de las avenidas, con giros vecinos que pasaron de 5,93 y 6,93 a 25 m/s. Los rectángulos locales del acceso de servicio conservaron el problema o añadieron otro retroceso en sentido contrario. [Variantes y reglas comparadas](../results/etapa1c3-sector01/alternativas.json) · [Rectángulos y sondas](../results/etapa1c3-sector01/dinamica/comparacion.json)

## Pruebas dinámicas

Se repitió la demanda original, con la misma huella, configuración, semilla 42 y paso de 0,5 s. El control reprodujo trayectorias, viajes, estados semafóricos y colisiones guardados. Las dos candidatas reprodujeron entre sí sus trayectorias, viajes, colisiones y estados. En cada candidata llegaron **36 de 36**, con cero colisiones, teletransportes, pendientes o avisos de ruta. Hubo 7.430 muestras, como en el control. Dos llegadas se desplazaron 0,5 s, en sentidos opuestos. La espera total pasó de 536 a 537 s. Las trazas y los estados semafóricos actuados difieren respecto del control, aunque los programas compilados coinciden. El control negativo también se repitió. Ambas redes rechazaron el giro `482520536#15 → 230776458` con código 1. [Rechazo en la candidata](../results/etapa1c3-sector01/candidato-local/control-negativo/candidato.log)

Una segunda prueba aplicó la misma sonda a cada red, con un auto por conexión, carril de entrada explícito, paso de 0,05 s y velocidad máxima de 2 m/s. La velocidad baja permite muestrear los enlaces cortos. Las sondas amplían cobertura sin cambiar la demanda original. **5/5 viajes completados** en el control y en ambas candidatas, con cero colisiones y teletransportes.

| Carril interno | Retroceso estático antes → después | Muestras internas antes → después | Menor paso longitudinal antes → después |
|---|---:|---:|---:|
| Servicio `:2480679873_1_0` | 2,33 → 2,33 m | 26 → 26 | −0,089 → −0,089 m |
| Bulevar Artigas `:4462688320_0_0` | 1,51 → 0 m | 16 → 2 | −0,096 → +0,123 m |
| Bulevar Artigas `:4462688320_0_1` | 1,65 → 0 m | 16 → 3 | −0,104 → +0,071 m |
| Williman `:2535807404_0_0` | 1,02 → 0 m | 10 → 3 | −0,099 → +0,101 m |
| Williman `:2535807404_0_1` | 1,05 → 0 m | 10 → 3 | −0,102 → +0,096 m |

Cada paso de la tabla se proyecta sobre el mismo rumbo de referencia antes y después e incluye la transición de entrada y salida. Las cuatro conexiones corregidas avanzan en cada par observado. Las dos conexiones de Bulevar Artigas tienen ahora evidencia dinámica en ambos carriles. El movimiento de servicio sigue siendo reproducible y el recorte ensayado no ofrece una corrección segura para ese patrón. [Sondas](../results/etapa1c3-sector01/dinamica/probes.rou.xml) · [Trayectorias candidatas](../results/etapa1c3-sector01/candidato-local/a/probes/trajectories.xml)

## Repetir

```powershell
$evidence = 'results/etapa1c3-sector01'
$suffix = [guid]::NewGuid().ToString('N')
python -B "$evidence/probar.py" "$evidence/controles-$suffix"
python -B "$evidence/candidato.py" "$evidence/candidato-$suffix" "$evidence/controles-$suffix/probes.rou.xml"
```

La revisión debe mantener como candidata la copia con cuatro correcciones. Para el acceso de servicio falta un ajuste local que coordine los tres extremos afectados y preserve los movimientos de ambos sentidos. La aceptación de ese ajuste requiere una comprobación de formas y conflictos vecinos y repetir las cinco sondas, además de la demanda original. Se aprobaron 32 regresiones de reproductor, QA, compilador y baseline estricta y se verificaron las huellas de 93 archivos históricos y 54 artefactos originales del Sector 01. [Integridad](../results/etapa1c3-sector01/integridad.json) · [Reproductor](../results/etapa1c3-sector01/reproductor.log) · [QA](../results/etapa1c3-sector01/auditoria-qa.log) · [Compilador](../results/etapa1c3-sector01/contrato-1a.log) · [Baseline estricta](../results/etapa1c3-sector01/baseline-estricta.log) · [Criterios para el cierre visual](AUDITORIA_REPRODUCTOR_3D.md)
