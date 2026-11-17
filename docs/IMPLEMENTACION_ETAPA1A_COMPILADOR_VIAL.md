# UrbanFlow · Primera entrega de Etapa 1A

Base `ee500585b44fe1433dc43170acdd50477d635f83`. [Plan aprobado](PLAN_ETAPA1A_COMPILADOR_VIAL.md)

**Veredicto final: Etapa 1A completada (PASS).** La regresión dinámica se ejecutó con las redes devueltas por `compile_package` y con el portátil oficial SUMO 1.26.0. El cierre cubre las sondas descritas y conserva las verificaciones físicas y visuales pendientes.

## Cierre funcional y revisión del comprobante

| Comprobación | Resultado observado |
|---|---|
| Honduras, demanda de referencia | Los 54 viajes finalizaron y cubrieron los 12 pares exteriores. Cero colisiones registradas y cero muestras de detención interna. Las 840 muestras TLS a intervalos de 0,5 s coincidieron con la secuencia esperada de 81 s durante los 420 s de corrida. |
| Honduras, salida ocupada | La sonda existente pasó con una copia byte por byte de la red devuelta. El ómnibus estaba detenido en el acceso antes de liberarse los bloqueadores a los 16 s. Ingresó al primer carril interno a los 17,5 s. Cero colisiones registradas. |
| Camacho ampliada | La conexión recta corregida quedó presente y sin alerta de retroceso. Joaquín de Viana conservó los nueve tramos en un único ciclo dirigido. Las dos conexiones del anillo mantuvieron `M` y las de incorporación desde Roosevelt mantuvieron `m` con visibilidad de 9 m. |
| Camacho, dos sondas idénticas | En cada ejecución completaron 24 vehículos, cero colisiones registradas. En los 12 pares el vehículo del anillo ingresó antes que el de Roosevelt. Los XML de trayectorias y `tripinfo` coincidieron al normalizar sus cabeceras. |
| Regresiones e integridad | 11 pruebas de contrato y 9 de baseline estricta aprobadas, sin fallos ni omisiones. H03 y H06 siguen caracterizados. Coincidieron las huellas y nombres de los 93 archivos históricos con el inventario de Etapa 0. |

Los comandos de simulación archivados apuntan a las salidas nuevas `compilada-honduras/network.net.xml` y `compilada-camacho/network.net.xml`. La sonda de salida ocupada usa una copia verificada de la primera. SHA-256 de las redes ejecutadas: Honduras `e413e58fbc2e5077287796aedde7f1227758f407519d45053ad564803921d862`, Camacho `a955256c43cbdb37c298cd4b2d82ca9173f56f81880f9f9396e0df7243b84742`. Se verificaron las huellas de los binarios portátiles antes de ejecutar. [Resultados dinámicos y huellas](../results/etapa1a-cierre-b4ac0b57/resultados.json) · [Comando de Honduras](../results/etapa1a-cierre-b4ac0b57/sonda-honduras/comando.json) · [Comando de Camacho](../results/etapa1a-cierre-b4ac0b57/sonda-viana-1/comando.json) · [Suite de contrato](../results/etapa1a-cierre-b4ac0b57/test_network_compiler.log) · [Baseline estricta](../results/etapa1a-cierre-b4ac0b57/test_baseline_v001.log)

**Defecto reproducido y corregido.** Con el manifiesto de la intermedia real de Camacho, una declaración `final` con listas consistentes y SHA-256 correcto producía una copia y un comprobante. El módulo ahora verifica la presencia de los cruces pendientes usando la misma configuración de nodos de la reconstrucción. Rechaza la etapa contradictoria antes de crear la salida, y comprueba al terminar que los cruces esperados quedaron unidos y se generó el programa. La reproducción real volvió a ejecutarse y fue rechazada. Se conservaron las evidencias iniciales en una carpeta de diagnóstico, sin promover esa red. [Reproducción previa a la corrección](../results/etapa1a-cierre-b4ac0b57/reproduccion-defecto/) · [Módulo corregido](../sumo_scenario/network_compiler.py)

**Integridad, etapa y aceptación.** Las rutas de entrada se resuelven dentro del paquete, la salida exige un directorio inexistente fuera de él y los nombres de artefactos están acotados. Se rechazan referencias externas y ausentes. Una declaración de etapa compatible y una huella correcta permiten operar sobre el paquete. La aceptación como referencia exige además la comparación semántica independiente con el original fijado. `compilation-result.json` registra operaciones y huellas, sin declarar equivalencia ni aprobación. El chequeo de etapa se limita a la operación de cruces que este módulo sabe reproducir. La geometría y la procedencia se comprueban contra la referencia independiente.

**Fallo parcial.** La prueba inyectó tanto un error como una interrupción una vez copiada la red. En ambos casos quedó el XML de trabajo y no se publicó `compilation-result.json`. El comprobante se escribe al final mediante reemplazo. Cualquier salida parcial se trata como evidencia de diagnóstico. El recorrido normal desde OSM carece de dependencias nuevas y ningún consumidor de producción lee estos comprobantes.

El cierre no mide la circulación individual por las 16 conexiones de Honduras ni valida el ciclo físico, la revisión visual 2D/3D o los 9 m de visibilidad en campo. El modelo y las correcciones existentes se mantuvieron. Solo se ajustaron el módulo optativo, su suite y este informe.

## Entrada optativa y contrato

`sumo_scenario.network_compiler.compile_package(manifest_path, output)` devuelve la ruta de la red final. También se puede invocar con `python -B -m sumo_scenario.network_compiler MANIFIESTO SALIDA_NUEVA`. La salida debe tener un padre existente y debe quedar fuera de la carpeta del manifiesto. El módulo no se conecta al generador normal ni a la web. [Implementación](../sumo_scenario/network_compiler.py)

El manifiesto JSON requiere `schemaVersion: 1`, `packageId` y `revision` como cadenas no vacías, `stage`, `applied`, `pending` y `artifacts`. Cada artefacto declara `path` relativo al paquete y `sha256` en hexadecimal minúsculo. Se rechazan referencias que escapen del paquete y claves JSON duplicadas. `network.net.xml` es obligatorio. Un paquete final puede incluir auxiliares XML conocidos, que se verifican y se copian si se declaran. El paquete intermedio requiere solo el XML completo. Las pasadas pendientes generan sus propios auxiliares.

| `stage` | `applied` | `pending` | Acción |
|---|---|---|---|
| `final` | `geometry-adjustment`, `compound-crossings` | Lista vacía | Verificar y copiar byte por byte, sin resolver binarios. |
| `intermediate` | `geometry-adjustment` | `compound-crossings` | Exigir `netconvertSha256` y ejecutar la reconstrucción existente sobre una copia. |

Los nombres representan etapas completadas del flujo acotado, incluidas las etapas sin cambios en una zona. Las listas tienen orden fijo. El esquema 1 no admite operaciones arbitrarias ni retomar una subpasada parcialmente completada. `compound-crossings` encapsula las tres pasadas existentes de unión, conexiones y programa. El ajuste geométrico de Camacho ya viene en el XML intermedio.

Se comprueban manifiesto, archivos, huellas y estructura mínima de red antes de crear la salida. La carpeta se crea de forma exclusiva. La fuente nunca se usa como destino. Un fallo después de crear la carpeta puede dejar XML o logs de diagnóstico. La ausencia de `compilation-result.json` identifica una salida incompleta. El comprobante se publica al final por reemplazo y registra identidad, revisión, etapa de origen, hash de la red de entrada, operaciones ejecutadas y hashes de salida. Para una intermedia registra también la huella de `netconvert`. Un comprobante final se puede usar como manifiesto de entrada para copiar esa red a otro directorio nuevo.

## Validación realizada

| Verificación | Resultado |
|---|---|
| Pruebas de contrato | 9 aprobadas. Incluyen huella incorrecta, paquete incompleto, versión y etapa desconocidas, duplicación e incoherencia, referencias ausentes o externas y pasadas que no se aplican. Verifican además que el caso final no resuelve herramientas, y que una salida existente no se sobrescribe. |
| Honduras congelada | Mismos bytes que el paquete final y misma firma semántica estricta que la referencia histórica certificada. Operaciones ejecutadas `[]`. |
| Camacho ampliada | Dos ejecuciones con el `netconvert` portátil verificado produjeron la misma firma final esperada en todas las secciones. Los SHA-256 de XML difieren por datos de exportación, y las firmas coincidieron sin cambiar el comparador. Solo se ejecutó `compound-crossings`. |
| Camino original desde OSM | Se regeneró el recorte de Honduras, coincidió su SHA-256 y `study.build_network` produjo la firma de referencia sin leer ningún manifiesto. Se probó la compilación vial del camino original. |
| Suite de baseline en modo estricto | 9 aprobadas, 0 omitidas. Honduras y Camacho compararon contra redes independientes de las salidas. H03 y H06 permanecen como pruebas de caracterización. |
| Integridad histórica | Coincidieron los nombres y SHA-256 de los 93 archivos de las cuatro corridas con el inventario de Etapa 0. |

[Pruebas del módulo](../tests/test_network_compiler.py) · [Resumen de las comparaciones](../results/etapa1a-6efcccfe/comparacion.json) · [Log estricto](../results/etapa1a-6efcccfe/baseline-estricta.log) · [Comprobante Honduras](../results/etapa1a-6efcccfe/honduras-1/compilation-result.json) · [Comprobante Camacho](../results/etapa1a-6efcccfe/camacho-1/compilation-result.json)

## Comandos de validación local

Desde la raíz del proyecto. Las rutas bajo `results/` apuntan a evidencia local. El ejemplo usa los paquetes verificados de esta entrega y crea una carpeta nueva en cada ejecución.

```powershell
python -B -m unittest discover -s tests -p test_network_compiler.py -v
$source = 'results/etapa1a-6efcccfe'
$run = (New-Item -ItemType Directory ('results/etapa1a-local-' + [guid]::NewGuid().ToString('N'))).FullName
$env:SUMO_HOME = (Resolve-Path 'results/baseline-v001-tools/portable/sumo-1.26.0').Path
$env:PATH = "$env:SUMO_HOME\bin;$env:PATH"
python -B -m sumo_scenario.network_compiler "$source/paquete-honduras/manifest.json" "$run/honduras"
if ($LASTEXITCODE -ne 0) { throw 'Falló Honduras' }
python -B -m sumo_scenario.network_compiler "$source/paquete-camacho/manifest.json" "$run/camacho"
if ($LASTEXITCODE -ne 0) { throw 'Falló Camacho' }
$env:URBANFLOW_BASELINE_STRICT = '1'
$env:URBANFLOW_BASELINE_HONDURAS = "$run/honduras/network.net.xml"
$env:URBANFLOW_BASELINE_CAMACHO = "$run/camacho/network.net.xml"
$env:URBANFLOW_BASELINE_BASE_CAMACHO = 'results/camacho-0c-d0025f9d/congelacion/camacho-ampliada/repeticion-1/network.net.xml'
python -B -m unittest discover -s tests -p test_baseline_v001.py -v
```

Para repetir la regresión de circulación del camino original desde OSM, ejecutar `python -B -m unittest discover -s tests -p test_honduras_control.py -v`. Para repetir el cierre funcional de la entrada optativa, tomar los comandos archivados en el acta, sustituir `--net-file` por cada salida nueva del ejemplo y ejecutar en directorios exclusivos. Conservar la demanda, semilla, horizonte, paso y captura de estados indicados. La revisión visual 2D/3D, el ciclo físico y la cobertura dinámica individual por carril quedan pendientes.

## Límites y reversión

Un manifiesto con hashes correctos acredita integridad frente al manifiesto elegido. La aceptación técnica de una red requiere cotejar su firma con la referencia y revisar la procedencia de ese manifiesto. El módulo valida estructura mínima y etapa. La firma estricta se verifica en la suite de baseline y sigue separada de la publicación del comprobante de compilación. La red congelada y los artefactos se cargan en memoria para copiar los bytes verificados. Los límites de memoria y el almacenamiento regional quedan para otro alcance. El binario se selecciona con el mecanismo existente y el hash evita usar inadvertidamente otra variante instalada.

Archivos nuevos de la entrega: este documento, el módulo optativo y su suite de pruebas. Los cambios se revierten dejando de invocar la entrada nueva o retirando esos archivos. No hay migraciones de estudios, cambios de API, configuración permanente, instalaciones, commits ni pushes. La construcción regional y una segunda implementación quedan fuera de esta entrega.
