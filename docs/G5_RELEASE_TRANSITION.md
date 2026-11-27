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
  SHAs. Verifica los labels de revisión SHA, registra los image IDs inmutables,
  distingue ambas imágenes y recoge el digest de la imagen base. Una etiqueta
  Docker no se toma como identidad.

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
CI=true GITHUB_ACTIONS=true python -m ops.ci_g5_release_transition \
  success "$RUNNER_TEMP/g5-transition"
CI=true GITHUB_ACTIONS=true python -m ops.ci_g5_release_transition \
  pull "$RUNNER_TEMP/g5-transition"
CI=true GITHUB_ACTIONS=true python -m ops.ci_g5_release_transition \
  backup "$RUNNER_TEMP/g5-transition" --approve-previous-recovery
CI=true GITHUB_ACTIONS=true python -m ops.ci_g5_release_transition \
  create "$RUNNER_TEMP/g5-transition" --approve-previous-recovery
CI=true GITHUB_ACTIONS=true python -m ops.ci_g5_release_transition \
  wrong-image "$RUNNER_TEMP/g5-transition" --approve-previous-recovery
CI=true GITHUB_ACTIONS=true python -m ops.ci_g5_release_transition \
  retry "$RUNNER_TEMP/g5-transition" --approve-previous-recovery
CI=true GITHUB_ACTIONS=true python -m ops.ci_g5_release_transition \
  replace "$RUNNER_TEMP/g5-transition"
```

Los casos de fallo son puntos de inyección deterministas, no cortes de red
externos. `pull` inyecta un fallo de adquisición antes de cerrar el servicio
previo; `backup` falla después de calcular una huella de solo lectura y antes
de guardar el snapshot; `create` deja un contenedor candidato creado y detenido
antes de fallar la creación del worker; `wrong-image` intenta usar la imagen
previa como candidata; `retry` repite una operación cuyo marcador ya existe;
`replace` falla después de COMMITTED y exige mantener las barreras cerradas.

El caso `success` usa una sola base PostgreSQL 15 con volumen nombrado y una
red interna invariables. Ejecuta la migración/seed de forma explícita con
contenedores one-shot (seed dos veces para idempotencia); los contenedores
runtime candidatos se crean detenidos y no ejecutan migración ni seed por
`depends_on`. Solo se inician después de COMMITTED. Se verifica que los
contenedores previos siguen detenidos con el mismo `StartedAt`, Nginx enruta a
la candidata, la versión anterior responde 404 en el endpoint introducido con
0020 y la candidata responde 401 antes de autenticación. También se comprueban
health HTTP, Socket.IO autenticado, una escritura real del jugador y su
persistencia/consumo por el worker candidato.

Pruebas unitarias de las guardas:

```sh
pytest -q -o addopts= tests/test_g5_release_transition_guards.py
```

## Recuperación y límites

Los fallos pre-migración `backup`, `create`, `wrong-image` y `retry` solo
reactivan el contenedor previo mediante la opción explícita
`--approve-previous-recovery`. Se exigen marcador y operación coincidentes,
ausencia verificable del inicio de migración, huella de DB idéntica, revisión
0019 y el mismo image ID/configuración del contenedor previo. No se restaura el
snapshot; el marcador de activación permanece y no se autoriza el entrypoint
legacy. Si alguna evidencia falta, cambia o resulta incierta, se conserva la
admisión cerrada y el directorio/evidencia para conciliación manual.

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
