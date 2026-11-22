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
- Solo elimina el marcador creado por este rollback tras completar restore, smoke y publicación de ambos punteros. Un marcador preexistente nunca se borra con el rollback, incluso si solo cambian imágenes y el smoke pasa; requiere certificación explícita independiente.
- Una restauración directa crea el mismo marcador tras validar el snapshot y la identidad de la base, antes de detener escritores. Persiste incluso si el comando termina correctamente; la recuperación aún necesita verificación y certificación del operador.
- Antes de crear un marcador nuevo, el rollback valida checksum e identidad del snapshot y congela sus bytes en una copia privada. Si esa validación read-only falla, no se detienen servicios ni aparece un marcador nuevo.
- Un fallo de restore **puede haber modificado servicios o datos** antes de fallar; requiere diagnóstico y recuperación controlada.

## Pruebas automáticas

`tests/test_bm0093_rollback_atomic.py` reproduce en un directorio temporal:
SHA obsoleto, snapshot ausente, fallo de restore, fallo de smoke,
fallo de Docker, bloqueo de despliegue tras fallo, rechazo preflight sin
marcador, preservación de marcador preexistente en rollback app-only y rollback
satisfactorio.
Reemplaza Docker y los scripts de recuperación y smoke por dobles locales,
sin conexiones a producción.

## Pendiente para cerrar BM-0093

Ensayo real aislado en staging con copia externa verificable, pérdida
simulada de un servicio, restauración end-to-end y medición de RPO/RTO.
El CI no acredita por sí solo recuperación ante pérdida del servidor.
