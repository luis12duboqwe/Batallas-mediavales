# BM-0093 — Rollback automático verificable durante despliegue

Un fallo durante `ops/deploy_remote.sh` no equivale a un rollback correcto.

## Cambio de comportamiento

- Cuando existe una release anterior, se exige su SHA válido antes de empezar a mutar la configuración activa.
- El rollback de emergencia usa la configuración anterior en un archivo privado temporal y solo publica dicha configuración al terminar la recuperación **y** aprobar el smoke.
- Si falla la restauración, la recuperación de imágenes o el smoke, queda `.ops-state/recovery-required` (modo incidente). Se bloquean nuevos despliegues hasta que el estado real de servicios y base de datos sea reconciliado.
- Se preserva el código original de error del despliegue; no se ocultan fallos de restore con `|| true`.
- Si la recuperación se verifica, se mantiene la versión previa y no se crea marcador de incidente.

La presencia del marcador exige intervención manual; **no** significa que los datos hayan sido recuperados. No borrar el marcador antes de verificar base de datos, servicios, integridad y smoke desde la URL real.

## Validación

`tests/test_bm0093_deploy_recovery.py` inyecta fallos de deploy,
recuperación de imágenes y smoke usando únicamente dobles locales.
Verifica punteros, ausencia de éxito falso, creación del marcador y bloqueo
de un segundo deploy.

## Límites

Sin restauración real en staging ni medición de RPO/RTO. `ops/rollback_remote.sh`
permite recuperación manual explícita; para limpiar un incidente, primero
verificar la coherencia del estado restaurado antes de habilitar despliegues.
