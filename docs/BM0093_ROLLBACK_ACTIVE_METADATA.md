# BM-0093 — Rollback sin cambiar anticipadamente la versión activa

Este cambio afecta exclusivamente al procedimiento **manual** `ops/rollback_remote.sh`.
No ejecuta un rollback real, no cambia servicios externos y no publica producción.

## Protecciones

- Antes de actuar, comprueba que el SHA solicitado coincide con `.release-sha`.
- Rechaza manifiestos incompletos, configuración anterior inválida y backups inexistentes antes de cambiar servicios.
- Prepara la configuración y el SHA de la versión anterior en archivos temporales privados.
- Ejecuta la restauración (o retorno de imágenes) con la configuración candidata.
- Solo después de pasar el smoke HTTP publica `.release.env` y `.release-sha`.
- Antes de restaurar o cambiar servicios, publica `.ops-state/recovery-required` para impedir nuevos despliegues mientras el estado es incierto.
- Si el restore, el smoke o la publicación de metadatos falla, conserva el marcador y los punteros originales que no se hayan publicado.
- Solo elimina el marcador tras completar restore, smoke y publicación de ambos punteros. Un fallo de restore **puede haber modificado servicios o datos** antes de fallar; requiere diagnóstico y recuperación controlada.

## Pruebas automáticas

`tests/test_bm0093_rollback_atomic.py` reproduce en un directorio temporal:
SHA obsoleto, snapshot ausente, fallo de restore, fallo de smoke,
fallo de Docker, bloqueo de despliegue tras fallo y rollback satisfactorio.
Reemplaza Docker y los scripts de recuperación y smoke por dobles locales,
sin conexiones a producción.

## Pendiente para cerrar BM-0093

Ensayo real aislado en staging con copia externa verificable, pérdida
simulada de un servicio, restauración end-to-end y medición de RPO/RTO.
El CI no acredita por sí solo recuperación ante pérdida del servidor.
