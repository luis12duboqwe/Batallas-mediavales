# G5 — ensayo de transición entre releases

**NO-GO para staging y producción.** Este ensayo está limitado a un runner
GitHub Actions desechable. No modifica workflows, no despliega a un VPS, no
publica puertos, no usa datos reales ni configura SMTP externo. No certifica
ni cambia el estado de #174.

## Releases y procedencia

- Release previa: `6ec2f118d4423359707176538d7f835bdb43c0e9`. El árbol de ese
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

No se agregó integración al workflow por alcance. Desde un job GitHub Actions
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
