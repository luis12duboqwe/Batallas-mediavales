# G5 — ensayo de transición entre releases

**NO-GO para staging y producción.** Este ensayo está limitado a un runner
GitHub Actions desechable. Se integra en Validation, no despliega a un VPS, no
publica puertos, no usa datos reales ni configura SMTP externo. No certifica
ni cambia el estado de #174.

## Releases y procedencia

- Release previa: `eafc5bbd5fdc9caad698db48cbb8ad80df942f0e`. El árbol de ese
  commit contiene la revisión Alembic `0019_privacy_active_unique` y no contiene
  `0020_wonder_funding_rules.py`.
- Candidata: el SHA completo de `HEAD` del checkout de CI; se exige que ese
  árbol contenga `0020_wonder_funding` y que sea distinto de la release previa.
- El ensayo construye ambas imágenes backend desde worktrees detenidos en esos
  SHAs. Compara el `Dockerfile` de cada worktree byte a byte con el blob de su
  SHA, registra su hash original y sustituye solo el `FROM python:3.11-slim`
  por el digest inmutable obtenido de la imagen base descargada. La construcción
  usa `--pull=false`; después valida labels, referencia base y prefijo de capas
  de la imagen inspeccionada. Registra los image IDs inmutables y exige que sean
  distintos. Una etiqueta Docker no se toma como identidad ni como prueba de
  qué base se usó.

La verificación del commit anterior a 0020 se obtuvo de su árbol GitHub y del
cambio que añadió 0020 (`264237860ef08348f082e37d1ea1579b6ab58e68`). Si el SHA
histórico no puede resolverse o no satisface las comprobaciones de migración,
el ensayo falla; no sustituye el SHA por una etiqueta mutable.

## Ejecución exacta

Validation exige todos los escenarios. Desde un job GitHub Actions
con Docker local disponible, dependencias backend instaladas e historial Git
suficiente (o acceso para buscar el SHA histórico), ejecutar:

```sh
install -d -m 700 "$RUNNER_TEMP/g5-transition"
export CI=true GITHUB_ACTIONS=true RUNNER_ENVIRONMENT=github-hosted
python -m ops.ci_g5_release_transition success "$RUNNER_TEMP/g5-transition"
python -m ops.ci_g5_release_transition pull "$RUNNER_TEMP/g5-transition"
python -m ops.ci_g5_release_transition backup "$RUNNER_TEMP/g5-transition" \
  --approve-previous-recovery
python -m ops.ci_g5_release_transition create "$RUNNER_TEMP/g5-transition" \
  --approve-previous-recovery
python -m ops.ci_g5_release_transition wrong-image "$RUNNER_TEMP/g5-transition" \
  --approve-previous-recovery
python -m ops.ci_g5_release_transition retry "$RUNNER_TEMP/g5-transition" \
  --approve-previous-recovery
python -m ops.ci_g5_release_transition replace "$RUNNER_TEMP/g5-transition"
```

Los casos de fallo son puntos de inyección deterministas, no cortes de red
externos. Cada punto registra un recibo duradero y lanza un tipo de excepción
propio con escenario y punto exactos. Solo ese tipo y su recibo permiten tratar
el fallo como inyectado; cualquier excepción no relacionada preserva el fixture
y no se convierte en un resultado esperado. `pull` inyecta un fallo de adquisición antes de cerrar el servicio
previo; `backup` falla después de calcular una huella de solo lectura y antes
de guardar el snapshot; esa huella normaliza únicamente los tokens aleatorios
de integridad del dump SQL y el archivo de respaldo conserva su hash propio.
`create` deja un contenedor candidato creado y detenido
antes de fallar la creación del worker; `wrong-image` intenta usar la imagen
previa como candidata; `retry` repite una operación cuyo marcador ya existe;
`replace` falla después de COMMITTED y exige mantener las barreras cerradas.

El caso `success` usa una sola base PostgreSQL 15 con volumen nombrado y una
red interna invariables. Ejecuta la migración/seed de forma explícita con
contenedores one-shot (seed dos veces para idempotencia); los contenedores
runtime candidatos se crean detenidos y no ejecutan migración ni seed por
`depends_on`. Solo se inician después de COMMITTED. Se verifica que los
contenedores previos siguen detenidos con el mismo `StartedAt`, Nginx enruta a
la candidata (incluso si Docker reasigna a la candidata la IP privada previa),
la versión anterior responde 404 en el endpoint introducido con 0020 y la
candidata responde 401 antes de autenticación. También se comprueban health
HTTP, Socket.IO autenticado, una escritura real del jugador y su
persistencia/consumo por el worker candidato.

Pruebas unitarias de las guardas:

```sh
pytest -q -o addopts= tests/test_g5_release_transition_guards.py
```

## Resultados de esta revisión

En el sandbox aislado con Docker local se ejecutó el harness del commit
`c66e0517a51e7a9294ee2a9d9f23c119b9ec08ab`; se configuraron las variables de
guard requeridas por el harness. No fue una ejecución de GitHub Actions ni una
integración de workflow. Los siete comandos terminaron con código 0:

| Caso | Resultado |
| --- | --- |
| `success` | Transición 0019→0020; HTTP, Socket.IO autenticado, versión, escritura y persistencia del worker candidatos verificados. |
| `pull` | Release previa seguía disponible; sin marcador, migración ni restauración. |
| `backup` | Recuperación supervisada previa, sin restaurar snapshot. |
| `create` | Recuperación supervisada previa tras creación parcial, sin restaurar snapshot. |
| `wrong-image` | Imagen candidata incorrecta rechazada; recuperación supervisada previa. |
| `retry` | Reintento inseguro rechazado; recuperación supervisada previa. |
| `replace` | Fallo tras COMMITTED; cierre verificado de escritores y edge. |

Las ejecuciones finales exportaron sus recibos y limpiaron sus fixtures Docker.
En los cuatro casos de recuperación previa, el backend anterior y su ruta HTTP
se comprobaron, pero el worker histórico que ya estaba detenido permaneció
detenido: no se intentó iniciarlo ni se afirma procesamiento de tareas con la
release histórica. Su fallo de arranque existente por importación circular
queda fuera de este cambio; `success` sí verifica la escritura persistente del
worker candidato.

## Recuperación y límites

Los fallos pre-migración `backup`, `create`, `wrong-image` y `retry` solo
reactivan el contenedor previo mediante la opción explícita
`--approve-previous-recovery`. Se exigen marcador y operación coincidentes,
ausencia verificable del inicio de migración, huella de DB idéntica, revisión
0019 y el mismo image ID/configuración del contenedor previo. La recuperación
mantiene el `deploy.lock`, descriptor y contenido del marcador, identidad de
directorio/manifest y tip del log de evidencia fijados durante todo el
procedimiento; vuelve a comprobarlos y la ausencia de mutaciones antes de cada
apertura. Primero intenta de forma independiente volver a cerrar Nginx,
PostgreSQL y todos los escritores, y verifica esas barreras antes de abrirlas.
Verifica el backend anterior de forma interna, resuelve su IP Docker actual,
recarga Nginx hacia esa IP y comprueba HTTP y Socket.IO antes de admitir tráfico.
Una excepción tras abrir una barrera vuelve a intentar el cierre completo. Si
cualquier inspección, cierre o identidad queda incierta, el fixture se conserva
para conciliación manual. No se restaura el snapshot; el marcador permanece y
no se autoriza el entrypoint legacy.

El lease protege una recuperación que se ejecuta en el mismo proceso; no hay
reanudación automática después de SIGKILL, caída del runner o pérdida del host.
El proceso siguiente debe conciliar manualmente el estado y la evidencia. La
integridad del recibo se fija al descriptor abierto: vacío, truncamiento,
registro parcial, edición final o reemplazo del archivo son errores.

Si la migración ya empezó, o hay fallo tras COMMITTED, no hay recuperación
automática al release previo ni restauración de snapshot. `replace` verifica
que el estado continúe COMMITTED, pero PostgreSQL, Nginx y los candidatos quedan
fenced para revisión.

El RPO/RTO de producción no está establecido por este ensayo: la huella
idéntica cubre únicamente los fallos CI demostrados antes de migrar; no prueba
RPO=0 frente a fallos durante/después de migración, ni mide o garantiza RTO.
La restauración integral de #206 sigue siendo una operación separada. No se
prueba exclusión de administradores privilegiados fuera del runner ni una
recuperación tras SIGKILL/pérdida del host.

En un caso verificado se eliminan por etiqueta únicamente los recursos del
fixture, el volumen y las etiquetas de imagen creadas para esa ejecución. Si
una identidad/fase o una barrera queda incierta, el script conserva el proyecto
Docker, el marcador y el recibo hash-encadenado e informa la ruta para
conciliación; no elimina datos para forzar éxito.

La revisión sigue **NO-GO**. No se afirma certificación de producción, no se
cierra #174 y no se debe mergear como autorización de despliegue.

## Revisión de responsable técnica

Se reemplaza el SHA histórico por el padre exacto de 0020, `eafc5bbd5fdc9caad698db48cbb8ad80df942f0e`, que conserva 0019 e incorpora la corrección de importación del worker #140 (`46aa895936ed2f42bd42062c4c44b4089fbadfa4`). Se exige ejecución real de una cola en la release anterior antes del cutover y otra tras recuperar esa misma release; ambos escritores deben estar activos. Los resultados previos del sandbox no certifican este cambio. Se integra la compuerta oficial CI, sin eliminar las anteriores. El fallo de arranque del worker del SHA anterior no se oculta con un wrapper ni se cambia su código histórico.

## CI oficial y cierre de evidencias

Validation 46022219240 y journeys 46022219284 aprobaron en HEAD 42a9b196: los siete escenarios se ejecutaron, incluido procesamiento de colas histórico y candidato. La revisión posterior detectó una última ventana de error entre reapertura y salida del lease/recibo final. Se amplía la protección a toda la fase de cierre de evidencia, incluyendo verificación final de candidata tras COMMITTED; los fallos preservan el fixture y reintentan restricciones. En replace se preserva antes de inspeccionar el estado y solo se limpia tras prueba positiva. Nuevas regresiones de recibo, salida del lease, prueba postcommit y contención previa a autorización. Nueva CI/revisión obligatorias.

Revisión de cierre: CI 46032818254 y journeys 46032818206 aprobaron, siete escenarios verificados. Se cubre la salida del lifecycle después del callback de reapertura con restricción independiente, preservación por defecto antes de cualquier clasificación y exportación solo de registros canónicos verificados desde el descriptor fijado. Solo resultados positivos y fallos esperados verificados habilitan limpieza; un fallo de exportación tras reapertura intenta cerrar escritores. Los mensajes de incertidumbre ya no aseguran que las barreras estén cerradas si no se ha verificado. Nuevas pruebas de salida del lifecycle y evidencia exportada. Pendiente CI/revisión.

## Integración del inventario privilegiado (#215)

El ensayo CI de transición comprueba la topología dedicada PG15 antes de iniciar el corte, con el fence activo antes/después del snapshot y en verificaciones de continuidad, después de migrar, antes de reabrir admisión y al terminar las pruebas de aplicación/worker. También se verifica durante recuperación supervisada cuando ambos componentes de la barrera SQL están cerrados o ambos abiertos. Se usan conexiones frescas de solo lectura y se registran nombres de bloqueadores sin secretos. El fixture revoca CONNECT público a postgres/template1. El octavo escenario inyecta un grant de parámetro después del snapshot, exige el bloqueador real no_parameter_grants y ausencia de PREPARED/migración, verifica incidente y huella original, conserva barrera de aplicación; no restaura. La inyección es exclusivamente sintética. Una observación no certifica exclusión de administradores externos ni continuidad por sí sola. Pendientes nueva CI y revisión. No se modifica el VPS.

Revisión P2: CI 46057398593 y journeys 46057398562 PASS sobre a0eefed9. Se añade observación mixta explícita: límite de conexiones restaurado al valor exacto anterior, NOLOGIN y cero sesiones cliente, auditoría completa de ACL. Ambas rutas de reapertura verifican este estado antes de LOGIN, no lo omiten. Ensayo PG15 de límite incorrecto, LOGIN prematuro y ACL durante estado mixto. Noveno escenario de transición inyecta ACL después de COMMITTED y restaurar límite, exige detección anterior a LOGIN, versión candidata intacta y cierre de escritores/edge, sin restore. Sincronizado con #217; nueva CI y revisión pendientes. La política sigue requiriendo exclusividad externa continua.
