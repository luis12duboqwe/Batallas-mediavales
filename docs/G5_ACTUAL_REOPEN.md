# G5 — reapertura real: implementación incompleta

**NO-GO.** El fixture es exclusivo de GitHub CI, no autoriza staging ni
producción y todavía no demuestra una reapertura completa. No se ha
integrado en workflows.

El adaptador parcial usa `G5Lifecycle`, las barreras existentes de Nginx,
PostgreSQL y Docker, PostgreSQL 15 y la imagen backend construida. Crea una
red interna desechable con direcciones fijadas y verifica sus identidades;
no publica puertos ni usa datos reales. Guarda un recibo durable de identidad,
parámetros SQL y políticas de reinicio completas. La configuración Docker se
representa mediante hashes, sin guardar variables de entorno ni credenciales.
El recibo no permite reanudar automáticamente tras un crash.
Si falla la limpieza de Docker por etiqueta, el directorio del fixture se
conserva y se informa su proyecto para conciliación manual.

El fixture incluye casos individuales `precommit`, `midreopen` y
`lost-response`. Los fallos posteriores comprueban una escritura
SQL confirmada como rol app después de `COMMITTED` y vuelven a restringir
los escritores sin restaurar el snapshot. La pérdida de respuesta es una
excepción inyectada después de iniciar el backend, no una desconexión real
del transporte. El caso `incomplete` se detiene deliberadamente sin abrir
el edge; **ningún caso demuestra todavía una reapertura exitosa**.
Para ejecutar un caso en GitHub CI se pasa su nombre y una ruta absoluta a un
directorio privado existente (modo 0700) fuera del checkout, por ejemplo
`python -m ops.ci_g5_actual_reopen precommit "$WORKSPACE_PRIVADO"`. Requiere
las imágenes `medievol-g5-backend:ci`, `postgres:15-alpine` y
`nginx:1.28-alpine`. El fixture crea y elimina recursos etiquetados propios;
la integración en CI y la ejecución del código final siguen pendientes.

## Evidencia de esta sesión

- HEAD de partida: `1717969d745b3206422bbe4ae012e62304e7821e`.
- Las pruebas unitarias de controles, recibo y revisión dieron **61 passed,
  4 warnings** sobre el
  código de `ops/ci_g5_actual_reopen.py` con SHA-256
  `48eb48f20a29a77a193b5f9c0d626ed47883a02e6fd84775ea336a438f226b35`:

  ```sh
  docker run --rm --network none --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$PWD/ops:/app/ops:ro" --volume "$PWD/tests:/app/tests:ro" \
    --entrypoint python medievol-g5-backend:ci -m pytest -q -p no:cacheprovider \
    --basetemp=.fixture-test tests/test_g5_actual_reopen_guards.py \
    tests/test_g5_actual_reopen_receipt.py tests/test_g5_actual_reopen_review.py
  ```
- Las pruebas existentes de ciclo y barreras dieron **111 passed, 4 warnings**
  en la imagen backend, con `umask 022`.
- Los cuatro casos de fallo se ejecutaron con éxito en versiones anteriores
  del fixture. **No se han ejecutado sobre el código final**; por tanto, no
  son evidencia de que esos casos pasen en este HEAD.
- Las imágenes backend, PostgreSQL 15 y Nginx se prepararon en el runner.
  La inspección posterior no encontró contenedores ni redes con la etiqueta
  del fixture. No se usaron puertos publicados, VPS ni credenciales reales.

## Pendiente

Faltan una reapertura exitosa con edge al final, HTTP y Socket.IO autenticados,
una escritura de jugador y una escritura real del worker, verificar la versión
de release frente a la imagen construida y pruebas de salud y de deriva de
identidad/configuración. También falta volver a ejecutar y revisar todos los
casos adversarios en el HEAD definitivo, incluida la preservación de escrituras
confirmadas tras COMMITTED. No se trata el rechazo de migración como permiso
para restaurar en este fixture; la restauración de #206 sigue independiente.
La rama actual no incorpora el cambio de #208.

No se afirma recuperación automática tras un crash, exclusión de administradores
privilegiados fuera del fixture ni RPO=0. No se cierra #174.
