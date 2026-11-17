# UrbanFlow v0.01 · Cierre de Etapa 0 y plan de Etapa 1A

**Fecha:** 13/11/2026 · **Base:** `ee500585b44fe1433dc43170acdd50477d635f83`

## 1. Veredicto y alcance del cierre

**Etapa 0: PASS CON OBSERVACIONES, cierre técnico condicionado.** La referencia certificada de Honduras conserva su alcance. La red ampliada de Camacho–Joaquín de Viana es apta para **aceptación técnica provisional**. Su perímetro conserva el anillo completo. Las 40 conversiones ampliadas dieron la misma firma en el ensayo de Etapa 0C, y cinco ejecuciones desde el XML intermedio congelado conservaron la firma final, el ajuste de Camacho y el control por carril de Honduras. El `BLOCKED` anterior sigue describiendo la reconstrucción con el perímetro histórico de Camacho. La referencia de trabajo para la futura extracción es la ampliada, identificada por huella. Este resultado queda limitado al recorte, binario y configuración ensayados. [Baseline histórica](BASELINE_TECNICA_V001.md) · [Diagnóstico 0B](DIAGNOSTICO_REPRODUCIBILIDAD_CAMACHO.md) · [Evidencia 0C](ESTABILIZACION_RED_VIAL_V001.md)

**Conocimiento local aportado el 13/11/2026.** El usuario, con aproximadamente 30 años de conocimiento de la zona, confirmó que en Roosevelt–Joaquín de Viana tienen prioridad los vehículos que ya circulan en la rotonda y que quienes ingresan desde avenida Roosevelt deben ceder. El modelo ampliado representa esa regla en la incorporación `212544014 → 121504388#5`, frente a la continuidad del anillo `121504388#4 → #5`. La fuente es el testimonio local del usuario. Quedan sin verificar por inspección fechada u organismo oficial los dispositivos de señalización, la demarcación y su ubicación por carril. Los 9 m de visibilidad siguen siendo un supuesto de SUMO. La observación se registra sin modificar los archivos de red.

Quedan pendientes la revisión visual histórica en 2D/3D, la validación física del ciclo semafórico de Honduras y la cobertura dinámica individual de sus 16 conexiones, incluida la cesión con verde permisivo ante un conflicto. La prueba dinámica ejecutada cubrió 12 pares exteriores y una salida ocupada. El cierre técnico condicionado permite someter el plan a revisión. El inicio de 1A requiere autorización separada. [Alcance y comprobaciones pendientes](BASELINE_TECNICA_V001.md) · [Sondas de 0C](../results/camacho-0c-d0025f9d/circulacion-local/comparacion.json)

### Manifiesto documental de aceptación provisional

Este registro complementa el manifiesto de ensayo de 0C. El estado de ese archivo y sus evidencias se conservan tal como se generaron. Las rutas de los artefactos apuntan a evidencia local bajo `results/`, excluida de Git. [Manifiesto de ensayo](../results/camacho-0c-d0025f9d/manifiesto-candidato.json)

| Campo | Valor fijado |
|---|---|
| Identidad y estado | `v0.01 / Etapa 0C / Camacho ampliada`. Apta para aceptación técnica provisional. |
| Fuente y recorte | OSM regional `2026-11-10T21:21:39Z`. SHA-256 del snapshot `868b473a814999649af1d03ba164be232320c9dd82a229d5514315c0afc3a272`. SHA-256 del recorte ampliado `54038d4bdc80ef8a9e43c24992292dd23f8ae0a8d4cc316ca03f859e60807148`. |
| Compilador y perfil | `netconvert` oficial portátil 1.26.0, SHA-256 `4174c17db813d413c85cdf7ad99a5f59b537ddf80f8caac9e1dfe87a35cb6b51`. Perímetro oeste, sur, este, norte `[-54.963595, -34.918823, -54.955989, -34.912334]`. El manifiesto de ensayo conserva argumentos efectivos y archivos de corrección. |
| Red intermedia | XML completo después del ajuste geométrico de Camacho y antes de unir Honduras. SHA-256 `5ed4d896133cf45191b268cd7582dd83f1ca5c745ff64ebd63a20e190b8a976d`. Firma serializada SHA-256 `e32cc0def69b9f05cc5fd8243234745a752dbd039a5ffd12ca1028010d90ec9d`. |
| Red final | Tras la unión física, reconstrucción de conexiones y programa de Honduras. SHA-256 `fc6c6271b3b229a393d2f968071585a182bb6751476c4d4be1579ca5e6c63ba7`. Firma serializada SHA-256 `efd4ebf66981f107c8c9e88c901490eecd8a8f9ab2ac06c6fee3f342e95c7ad4`. |
| Reproducibilidad técnica | Una firma estricta para las 40 conversiones ampliadas y una firma final para las cinco ejecuciones desde la intermedia. Evidencia acotada a este caso. |
| Geometría y conectividad | Anillo dirigido completo `121504388#1–#9`. Conexión recta corregida de Camacho `-178119926#0_0 → 121506103#0_0`, sin alerta de retroceso. Las 16 conexiones semaforizadas de Honduras conservan los permisos por carril y las duraciones de la referencia. |
| Regla corroborada localmente | Prioridad de quienes circulan en el anillo de Joaquín de Viana y cesión al ingresar desde Roosevelt. Testimonio del usuario, 13/11/2026. Vigencia anterior y cambios horarios sin documentar. |
| Inferencias y estimaciones | Visibilidad de 9 m en las dos conexiones menores de esa incorporación. Programa y tiempos de Honduras como referencia simulada. La demanda de sonda es sintética. |
| Validación pendiente | Dispositivos y demarcación por carril en Viana, ciclo físico de Honduras, cobertura dinámica de las 16 conexiones y revisión visual 2D/3D. |

[Huellas y firmas de Camacho](../results/camacho-0c-d0025f9d/congelacion/camacho-ampliada/huellas.json) · [Huellas de Honduras certificada](../results/camacho-0c-d0025f9d/congelacion/honduras-certificada/huellas.json) · [Inventario de los 93 archivos históricos](../results/camacho-0c-d0025f9d/integridad-historicos.json)

## 2. Contratos y responsabilidades

| Componente | Entrada mínima | Salida y responsabilidad |
|---|---|---|
| Planificador de perímetro | Zona de interés, snapshot, margen inicial, clases de vehículo y límites de expansión. | `CompilationExtent`: zona de interés, perímetro compilable, recorte fuente, entidades añadidas y conflictos de borde. Trabaja con referencias OSM y evidencia de completitud. |
| Compilador vial | `CompilationSpec`: snapshot y recorte por huella, perímetro, binario y argumentos efectivos, y conjunto de correcciones aplicable. | `CompilationResult`: referencia intermedia completa, red final, exportaciones auxiliares, correspondencia OSM–SUMO y diagnósticos. No genera demanda, corridas ni respuestas de API. |
| Aplicador de correcciones | Red en etapa conocida, `CorrectionSet` versionado y correspondencias de entidades. | Plan de cambios ordenado, operaciones aplicadas o descartadas con motivo y verificaciones antes y después. La coincidencia ambigua exige resolución explícita. |
| Lector de redes congeladas | Manifiesto, directorio de artefactos y revisión solicitada. | Verifica esquema, etapa, SHA-256, disponibilidad y compatibilidad. Devuelve la red y sus auxiliares sin recompilar ni seleccionar otra versión en silencio. |
| Validador | Redes, firma versionada, pruebas de referencia y evidencias fechadas. | Diagnósticos por atributo y resultado por alcance. La equivalencia técnica y la corroboración vial tienen estados independientes. |
| Generador de estudios | Red final, metadatos del objetivo y demanda. | Conserva el contrato web y los formatos de corrida existentes. Guarda qué revisión exacta consumió. |

El límite propuesto se apoya en `study.build_network` y `compound_crossings.rebuild_crossings`. La geometría, la topología y el control pertenecen al compilador. Las rutas, los volúmenes, las métricas, la persistencia de corridas y los visores permanecen en sus etapas actuales. Los consumidores que hoy conocen `CROSSINGS` pueden seguir usando un adaptador de compatibilidad durante 1A. [Compilación actual](../sumo_scenario/study.py#L525) · [Reconstrucción actual](../sumo_scenario/compound_crossings.py#L107) · [Auditoría rectora](AUDITORIA_ARQUITECTURA_URBANFLOW.md)

## 3. Perímetros que conservan estructuras completas

1. Definir **tres ámbitos** por revisión. La zona de interés selecciona el corredor y sus métricas. El perímetro de compilación incluye las estructuras necesarias para circular. El recorte fuente agrega contexto y referencias para importar. Registrar el CRS y aplicar el margen en unidades métricas.
2. Partir de una envolvente inicial y calcular cierre por referencias sobre el snapshot. Incluir ciclos de rotonda etiquetados que toca el área, todos los nodos y conexiones de un cruce compuesto documentado, accesos requeridos y miembros `from/via/to` de restricciones relevantes, incluidas vías intermedias. Mantener separados los niveles de paso. Usar agrupación declarada o evidencia topológica. La proximidad por sí sola no autoriza unir nodos físicos.
3. Recalcular el perímetro que contiene las entidades incorporadas y repetir hasta que el conjunto se estabilice. Acotar por cobertura del snapshot y un presupuesto configurable de expansión. Si se agota, informar qué estructura sigue cortada y excluirla de la aceptación para ese uso. Conservar candidatos ambiguos de anillos que comparten nodos para revisión. El margen de Camacho no es una constante regional.
4. Verificar antes y después de `netconvert`. Contrastar ciclo cerrado y dirigido, miembros de restricciones, continuidad de accesos, conexiones por clase y correspondencias OSM–SUMO. Un archivo OSM completo puede quedar cortado por el filtro de compilación. Por eso una comprobación de completitud del recorte por sí sola no basta. Guardar un diagnóstico de borde con entidades, etapa y fuentes. [Ensayos de perímetro en Camacho](ESTABILIZACION_RED_VIAL_V001.md#2-efecto-del-margen-de-compilación)

En 1A, la entrada usa perímetros ya fijados y comprueba integridad de los artefactos. El cálculo automático de cierre se especifica aquí para una etapa posterior y se ensaya primero con fixtures pequeños. Así se puede comprobar la extracción del compilador sin cambiar simultáneamente la cobertura de los estudios.

## 4. Correcciones declarativas

Cada conjunto contiene `schemaVersion`, `id`, `revision`, aplicabilidad por snapshot y etapa, y una lista ordenada de operaciones. Cada operación declara un ID estable, tipo, objetivo, precondiciones, valores, procedencia, vigencia, estado de evidencia y comprobaciones posteriores. Referenciar vías dirigidas, nodos OSM y carriles por sentido y orden, y traducir a aristas e índices SUMO al aplicar. Una revisión fijada puede conservar los IDs SUMO como correspondencias verificadas. Una nueva revisión exige comprobar que siguen resolviendo la misma entidad física.

Tipos previstos para las correcciones existentes:

- `setJunctionShape` declara geometría, CRS, unión objetivo y postcondición. Camacho aporta el XML actual, los extremos del movimiento recto y la comprobación de retroceso.
- `mergeJunctions` declara nodos físicos, precondiciones y movimientos exteriores esperados. Una operación distinta representa la coordinación de varios cruces bajo un controlador.
- `setLaneConnections` declara altas, bajas o reemplazos por carril de entrada y salida, con restricciones de clase. Verificar que un cambio de número u orientación de carriles impida una aplicación incorrecta.
- `setSignalPlan` declara grupos, enlaces, permisos protegidos o permisivos, fases, tiempos y fuente. Resolver `linkIndex` al compilar y contrastar conflictos antes de aceptar.

Las operaciones son datos declarativos. Evitar scripts arbitrarios en el manifiesto. Distinguir operación fuera de cobertura, operación ya aplicada y objetivo perdido o ambiguo. Las dos primeras se registran con su motivo. Una precondición fallida para un objetivo dentro de cobertura deja la compilación sin aprobar. Superposiciones se resuelven mediante sustitución explícita entre revisiones o diagnóstico, con evidencia por atributo. La observación de Viana se registra como procedencia del atributo. No requiere un parche de prioridad porque la red ampliada ya representa la regla.

## 5. Redes intermedias y finales inmutables

Guardar un paquete local por revisión con recorte OSM, XML intermedio completo, red final, archivos auxiliares requeridos por el generador, firma, manifiesto y evidencias. La red intermedia declara qué operaciones ya recibió. La red final es la entrada de la corrida y conserva el modelo exacto. Los XML planos quedan disponibles para inspección y exportación. La recarga probada en 0B cambió la firma frente a su origen. [Ensayo de recarga](DIAGNOSTICO_REPRODUCIBILIDAD_CAMACHO.md#entradas-congeladas-y-recomendación-mínima)

Publicar el manifiesto después de validar todas las huellas. Guardar el paquete en un directorio nuevo por revisión o identidad de contenido. Resolver rutas relativas al paquete, con una referencia explícita a la fuente archivada. El manifiesto identifica versión del esquema de firma, etapas, correcciones aplicadas, opciones, binario, vigencia y alcance de aceptación. Para comparar, distinguir identidad por bytes y equivalencia por firma. Mantener geometría, sentido, carriles, conflictos, prioridades, visibilidad efectiva y fases en la comprobación.

Cambios de snapshot, recorte, perímetro, binario, argumentos u operaciones invalidan la reutilización como referencia **para estudios nuevos** hasta una aceptación explícita. Un cambio de evidencia puede cambiar el estado de un atributo sin cambiar los bytes. Un cambio del esquema de firma requiere recalcularla. La reproducción histórica sigue apuntando al paquete con el que se ejecutó la corrida. Un archivo faltante o alterado devuelve un diagnóstico, sin reconstrucción implícita.

## 6. Compatibilidad y regresiones

| Caso | Aceptación requerida para 1A |
|---|---|
| Honduras certificada | Comparar la firma completa con la referencia fijada. Conservar 12 pares exteriores, 16 conexiones por carril, `G/g`, transiciones y ciclo de 81 s. Mantener la prueba de circulación de referencia y la espera ante salida ocupada. |
| Camacho ampliada | Comparar cada etapa contra su propio artefacto congelado. Mantener el polígono aplicado, la conexión recta sin retroceso, el anillo cerrado de Viana y la prioridad y visibilidad de su incorporación. Repetir dos veces desde la misma intermedia. |
| Demanda y borde | La ampliada usa sondas locales compatibles. El volumen histórico completo de Honduras incluye tramos ausentes del perímetro ampliado. Conservar esa prueba sobre la red certificada y verificar explícitamente las rutas antes de reutilizar demanda en otro perímetro. |
| Históricos | Comparar los SHA-256 de los 93 archivos antes y después. Mantener la lectura por la API del programa y cuadros históricos. La revisión 2D/3D registra ID, tiempo y transición en ambas vistas cuando se realice. |
| Límites conocidos | Mantener las pruebas de caracterización H03 y H06. Reportar pruebas omitidas como pendientes. La equivalencia de la referencia simulada no certifica el programa de campo ni la circulación por cada conexión. |

[Suite estática](../tests/test_baseline_v001.py) · [Prueba de circulación](../tests/test_honduras_control.py) · [Casos y trazas de 0C](ESTABILIZACION_RED_VIAL_V001.md#3-qué-redes-pueden-reutilizarse)

## 7. Preparación para la base regional

Usar el snapshot compartido de Maldonado, Punta del Este, Solanas y La Barra como raíz de procedencia. Mantener paquetes por corredor en la primera expansión. Registrar los hallazgos de inspección como propuestas de corrección identificadas por entidad de fuente, junto con evidencia, vigencia y una prueba de regresión. La revisión posterior aprueba una nueva versión del conjunto aplicable a todos los estudios nuevos que cubran esa entidad. Las corridas anteriores conservan su revisión.

Para una ciudad completa, compilar una zona conectada con las correcciones aprobadas acumuladas. Usar solapes de corredores para verificar correspondencia de sentidos, conexiones y restricciones y para detectar cambios de borde. El ensamblado opera sobre entidades fuente y operaciones declaradas. Concatenar redes SUMO finales duplicaría aristas, nodos o controladores. Los datos geográficos adicionales y el editor gráfico podrán alimentar los mismos contratos. Su implementación queda fuera de 1A. [Cobertura regional actual](../sumo_scenario/regional/coverage.json) · [Estrategia regional de 0C](ESTABILIZACION_RED_VIAL_V001.md#5-de-un-corredor-a-la-base-regional)

## 8. Primera implementación mínima recomendada

**Una primera entrega pequeña.** Extraer una entrada de compilación que reciba un paquete congelado explícito y pueda reproducir las pasadas posteriores sobre una copia. Mantener la generación desde OSM y sus correcciones actuales por la vía existente. El nuevo recorrido se prueba por llamada directa o herramienta de prueba y no se conecta todavía a la UI ni cambia el comportamiento por defecto. El paquete puede declarar correcciones ya aplicadas y los XML de las siguientes etapas con huellas. Migrar las reglas de detección y generación de parches a un catálogo declarativo en un cambio posterior, una vez verificada esta frontera. La primera entrega no necesita un lenguaje general de parches ni automatizar perímetros.

| Archivos previstos | Alcance del cambio futuro |
|---|---|
| Nuevo `sumo_scenario/network_compiler.py` | Cargar y verificar un paquete explícito, copiar la red de entrada al directorio nuevo, ejecutar las etapas declaradas mediante adaptadores existentes y devolver resultado y diagnósticos. |
| `sumo_scenario/study.py` | Adaptación mínima del límite de compilación solo si hace falta para compartir el punto de entrada. Mantener la firma pública de `build_network` y el recorrido normal. |
| `sumo_scenario/compound_crossings.py` | Reusar la reconstrucción en el camino de prueba. Si hace falta una separación, extraer solo la ejecución de artefactos ya preparados y conservar el comportamiento de la función actual. |
| `tests/` y fixtures de manifiesto | Verificar huellas, etapas y equivalencia estricta. Reutilizar las pruebas de circulación y de históricos. Los originales siguen externos al repositorio de código. |

**Pruebas de aceptación.** La red final congelada de Honduras se carga sin volver a corregirla. La intermedia de Camacho se procesa dos veces desde copias y conserva la firma final fijada, el control de Honduras y el ajuste de Camacho. Probar un paquete con huella incorrecta, referencia faltante, versión de esquema desconocida, etapa incompatible y operación ya aplicada. Los casos inválidos no publican una red utilizable. Comparar visibilidad, prioridades y rotondas sin excepciones. Revisar que cada ejecución se puede asociar a su paquete y que los archivos históricos siguen intactos.

**Riesgos y reversión.** Volver a aplicar una operación puede cambiar índices semafóricos o prioridades. Validar el estado de etapa antes de invocarla. Regenerar auxiliares desde XML plano puede perder semántica. Mantener el XML completo como autoridad y comprobar huellas de auxiliares. Un manifiesto ausente en una instalación existente debe permitir seguir usando la vía actual. Para revertir, dejar de seleccionar el recorrido explícito y retirar o revertir el cambio aislado. Las referencias y corridas existentes permanecen disponibles. La implementación futura no requiere cambios de API, frontend, editor regional, WFS/WMS, IA, motor de demanda ni versión de SUMO.

## 9. Autorización de inicio

1. Aprobar por escrito el cierre técnico condicionado, el manifiesto documental y las huellas de Camacho ampliada y Honduras certificada. Aceptar que la prioridad en Joaquín de Viana se sustenta en conocimiento local y la visibilidad en un supuesto del simulador.
2. Aprobar el alcance acotado de la primera entrega, el punto de entrada optativo, los archivos potencialmente afectados y las regresiones obligatorias. Confirmar la disponibilidad de los paquetes y del portátil SUMO 1.26.0 antes de iniciar pruebas de implementación.
3. Registrar si la revisión visual, el ciclo físico y la cobertura dinámica por carril se exigirán antes de promover la red a uso operativo o se gestionarán como verificaciones posteriores. Permanecen abiertas en este cierre.
4. Dar una autorización explícita para implementar **Etapa 1A**. Este plan se entrega para revisión. No se ejecutaron ensayos nuevos ni se modificaron producción, estudios históricos o referencias certificadas.
