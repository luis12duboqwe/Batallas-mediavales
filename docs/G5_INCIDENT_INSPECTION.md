# G5 — Inspección no autorizante de incidentes (#174)

**NO-GO.** Módulo de lectura exclusivamente; no es un recuperador ni una CLI.

`inspect_incident(host_root)` observa el marcador de activación y el manifiesto
bajo los locks compartidos de despliegue y manifiesto. Requiere evidencia
existente; no crea locks ni escribe, elimina o corrige recibos. Verifica modo,
tipo, propietario, inode y formato del marcador, checksum del manifiesto e
igualdad del identificador de operación. Rechaza locks activos, deriva,
marcadores ausentes/irregulares, evidencia legacy y temporales de publicación.

| Evidencia observada | Clasificación, no autorización |
|---|---|
| Marcador sin manifiesto | PREPARATION_UNCERTAIN: se desconoce el estado de barreras |
| PREPARED / MIGRATING / VERIFIED_READONLY | PRECOMMIT_RECONCILIATION: comprobar ejecutor y barreras, no reintentar ni restaurar automáticamente |
| RECOVERY_REQUIRED | INCIDENT_RECONCILIATION: preservar evidencia |
| COMMITTED_WRITERS_ALLOWED | POSTCOMMIT_RECONCILIATION: nunca usar el snapshot anterior; comprobar estado real de escritores |

El resultado es una observación, no una prueba de durabilidad ante pérdida de
energía, exclusión continua, identidad externa, integridad del backup ni permiso
para actuar. No admite resume automático, no toca SQL/Docker y no cambia
scripts legacy. Los locks solo excluyen escritores cooperantes durante la
lectura. El futuro adaptador necesita inspección real de DB, contenedores,
edge, ejecutores, metadata de release y barreras antes de decidir cualquier
recuperación. Mantener #174 abierto.

Pruebas: `pytest -q -o addopts= tests/test_g5_incident_inspect.py`.
