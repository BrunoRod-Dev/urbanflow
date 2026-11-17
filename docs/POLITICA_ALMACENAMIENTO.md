# UrbanFlow · Política de almacenamiento

Cada etapa nueva informa el espacio que agrega y no vuelve a guardar una copia completa de lo que ya existe.

## Dónde va cada cosa

- El SUMO 1.26.0 de trabajo queda en `results/baseline-v001-tools/portable/sumo-1.26.0`. No se descomprime otra vez. El ZIP oficial, si hace falta recuperarlo, está publicado por DLR y su SHA-256 es `17709c062ba420b3ce6a9e8e2fa1925a8f3a6f9ce87b49dd232a21898c660d71`.
- El snapshot OSM de referencia es `sumo_scenario/regional/maldonado.osm.gz`. Las etapas lo citan; no guardan otro recorte igual.
- Los inventarios v001 y v002 consolidados siguen en sus carpetas citadas. Una etapa que no los cambie anota el hash en lugar de copiar el GeoJSON.
- Los 93 históricos están listados en `tests/fixtures/historicos_93.json`. No se mueven ni se sobrescriben.
- La candidata que abre `probar_sector01.py` es `results/etapa1c5-sector01`.

## Temporales

Los ensayos de una etapa van a `results/_tmp/<etapa>`. El nombre de la etapa no lleva barras ni puntos. `cleanup_temporary` solo borra dentro de `results/_tmp`. Si la ruta está en la lista protegida de `tools/storage_policy.py`, la limpieza se detiene.

Un archivo certificado o citado por un manifiesto, un test o un documento no entra en `_tmp` y no lo alcanza la limpieza automática.

## Copias idénticas

Si un XML, un GeoJSON, una captura o un ZIP ya está guardado, la etapa escribe una referencia con `write_hash_reference`: ruta, SHA-256 y tamaño. No copia el archivo otra vez.

Al cerrar la etapa se miden los bytes de `results/` antes y después con `stage_growth` y ese dato queda en el informe.

## Cuarentena

Lo retirado en la higiene de noviembre de 2026 está fuera del proyecto, en el escritorio, carpeta `urbanflow-cuarentena`. El inventario es `docs/cuarentena-almacenamiento.json`. No se borra esa cuarentena sin una autorización aparte.
