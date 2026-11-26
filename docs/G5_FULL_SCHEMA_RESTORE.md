# G5 — rollback íntegro de esquema real PG15 (#205)

Ensayo autónomo **solo GitHub CI**, asociado a #174 (continúa abierto y NO-GO).
No modifica el coordinador/restore sintético de #203, los tres archivos de
#204, `validation.yml` ni scripts legacy. La integración obligatoria en CI
y su aceptación se coordinarán con la responsable técnica después de #204.
La PR debe permanecer draft; este ensayo no autoriza merge ni despliegue.

## Ejecutar

Desde la raíz del checkout del runner GitHub Actions:

```sh
python -m ops.ci_g5_full_schema_restore --scenario all
```

Requiere `CI=true`, `GITHUB_ACTIONS=true`, Docker local en
`unix:///var/run/docker.sock`, PostgreSQL `postgres:15-alpine` y acceso al
registro para descargar/build inicial. Rechaza ejecución sin ambas variables.
No recibe URL de DB, host, credenciales, imagen de producción ni destino
configurable. Si falta `bm-g5-full-schema-head:<HEAD>`, construye el Dockerfile
del backend del checkout actual. No cambia dependencias.

Pruebas rápidas (sin servicios ni fixtures FastAPI):

```sh
python -m pytest --noconftest -o addopts='' \
  tests/test_g5_full_schema_restore_safety.py \
  tests/test_g5_full_schema_restore_runtime.py \
  tests/test_g5_pg15_writer_fence.py
```

La prueba real opt-in puede ejecutarse con la infraestructura pytest existente:

```sh
BM_G5_FULL_SCHEMA_RESTORE=1 python -m pytest --noconftest -o addopts='' -s \
  tests/test_g5_full_schema_restore_runtime.py
```

También exige las dos variables de GitHub CI. `--scenario` permite aislar
`rollback`, `restore-failure`, `tampered`, `drift` o `dependency`.
Cada caso crea su propia DB, contenedores y red interna con nombre aleatorio.
El ejecutor Alembic comparte únicamente el namespace de red del contenedor
PG15 y conecta a su loopback; no depende de DNS entre contenedores.
No hay puertos publicados, bind mounts, VPS ni datos reales.

## Protocolo y evidencia

1. Crear DB desechable y roles sintéticos. Ejecutar **toda la cadena Alembic
   real hasta `0019_privacy_active_unique`**, sin `stamp` ni metadata sintética.
   Sembrar mundo/alianza con `world_id`; confirmar un UPDATE con rol app
   restringido desde otra conexión. Mantener una sesión app previa al corte.
   Variar propietario de una tabla y grants para evitar controles vacíos.
2. Aplicar `Pg15PersistentFence`: límite de conexión 0, NOLOGIN, terminación
   de sesiones y ausencia de transacciones preparadas. Reconstruir el
   observador para comprobar estado persistente y rechazo FATAL de login.
3. Capturar `pg_dump --format=custom` después del fence/drain en archivo 0600,
   fsync de archivo/directorio, registrar dispositivo/inodo/tamaño/SHA256.
   Abrir sin seguir symlinks, verificar el FD y validar TOC con `pg_restore`.
   Verificar de nuevo barrera y equivalencia con el inventario anterior.
   Restaurar el FD en `g5_catalog_reference`, DB testigo nueva del mismo
   contenedor desechable, para obtener el catálogo esperado tras el parser PG15.
   La DB de juego no se reemplaza ni cambia de identidad.
4. Ejecutar **0020 real**, comprobar ledger, tablas de financiación y nueva
   columna del mundo; confirmar mutación del mundo desde otra sesión admin.
   Registrar inventario candidato y forzar rechazo conocido `division by zero`.
   El contenedor Alembic ya terminó y se eliminó; la sesión SQL también salió.
   Timeout/transport failure no se clasifica como rechazo recuperable.
5. Antes de restore: misma identidad DB (OID/nombre/propietario), barrera,
   ejecutor ausente, rechazo conocido, FD nuevamente verificado, ámbito de
   objetos y catálogo/filas/secuencias candidato sin drift.
6. Convertir **los bytes del FD verificado**, no reabrir la ruta, con
   `pg_restore` a SQL. En una sola transacción: `DROP SCHEMA public CASCADE`,
   recrear `public` inicial si PG15 omite su definición, restaurar todo
   desde el snapshot y COMMIT. Nunca `DROP DATABASE`, `--create`,
   cambio de rol LOGIN ni reapertura del límite. `--clean` del dump antiguo
   por sí solo deja objetos de 0020; vaciar el esquema evita ese residuo.
   El bootstrap conserva propietario `pg_database_owner`, USAGE a PUBLIC y
   comentario `standard public schema`; el dump aplica las diferencias.
7. Pausar la transacción después del DROP para observar rechazo FATAL de app
   durante un restore realmente activo. Antes/después comprobar también
   ausencia de sesiones y transacciones preparadas. Comparar todo el
   inventario previo y exigir desaparición de las tablas exclusivas de 0020.

El catálogo compara todos los bloques TOC de `pg_dump --schema-only` contra
la restauración independiente del snapshot en la DB testigo, sin
eliminar DDL, ACL, propiedad, restricciones, índices, defaults o tipos.
Normaliza solo banners externos, tokens aleatorios `psql \restrict` y
orden entre bloques (no orden dentro de cada bloque). Compara todas las
filas de todas las tablas `public`, incluido `alembic_version`, ordenadas
como JSONB, y `last_value/is_called` de todas las secuencias. Los OIDs de
objetos reconstruidos cambian por diseño; el de la DB debe conservarse.
También compara ACL/propietario de la DB y namespace `public`, encoding,
collation y estado de admisión. Conserva contenido SQL multilínea.
PG15 cambia la representación textual de los casts ARRAY del índice parcial
real de 0019 al releer su DDL. El testigo normaliza mediante el propio parser
PostgreSQL, no regex de predicados ni exclusión de índices. Filas y secuencias
siguen comparándose directamente con el inventario de la DB original.

## Adversarios

| Caso | Resultado exigido |
| --- | --- |
| `rollback` | Catálogo, filas, secuencias, ACL, propietarios y ledger idénticos a 0019; sin objetos exclusivos de 0020. |
| `restore-failure` | Error conocido **después de reconstruir/cargar** pero antes de COMMIT; rollback transaccional conserva íntegro el candidato, barrera cerrada, sin reintento automático. |
| `tampered` | Alterar bytes después de abrir el FD; checksum rechaza antes de DDL y conserva el candidato. |
| `drift` | UPDATE y tabla nueva administrativos después del inventario candidato; rechazar sin borrar ni restaurar. |
| `dependency` | Vista en esquema ajeno dependiente de `worlds`; rechazar antes del CASCADE, preservar vista y datos. |

Pruebas unitarias adicionales cubren sustitución de ruta/inodo, truncado,
symlinks, permisos, comparación de ACL/owner/constraints, precondiciones,
socket Docker local y limpieza de volúmenes.

## Límites y limpieza

El CASCADE solo es elegible en este fixture recién creado, con `public`
como único namespace de juego autorizado. Cualquier namespace desconocido
o dependencia externa en `pg_depend` impide el borrado. No sirve como
algoritmo genérico para extensiones, esquemas compartidos u objetos externos.
Los roles/globales y configuración de cluster no se restauran; se conservan
en el cluster aislado y el fence se verifica independientemente.

No es backup físico ni equivalencia byte a byte. La semilla es pequeña,
no el seed canónico de #204 ni una carga de producción. El control app es
SQL autenticado con el rol runtime, no HTTP/Socket.IO. No prueba reapertura,
publicación, exclusión de administradores reales, failover, crash del
postmaster, recuperación del coordinador ni certificación de staging #161.
La exclusividad privilegiada deriva de la propiedad del fixture; observar
sesiones no la demuestra en producción. **No afirma RPO=0.**

En `finally` elimina contenedores, volúmenes anónimos de PG15, ambas DB
desaparecen con el cluster desechable, red interna
y snapshot temporal, también tras fallos. La imagen local de HEAD queda
como cache de build del runner. Un fallo de limpieza hace fallar el ensayo.
Registra nombres antes de crear y reconcilia recursos parcialmente creados
por etiqueta exclusiva; no borra recursos ajenos que colisionen en nombre.
Cada resultado JSON se imprime solo después de limpiar; incluye escenario,
HEAD, hash del snapshot, tamaño del inventario, identidad y barrera.
No imprime passwords, URLs ni stderr de procesos DB.

## Ejecución verificada

La evidencia de los cinco casos reales se incorporará tras completar el
ensayo en el runner de esta PR. La futura ejecución obligatoria en
`validation.yml` queda expresamente fuera del alcance de #205.
