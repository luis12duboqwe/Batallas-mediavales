# BM-0062 — Auditoría de impacto para mundos históricos (PD-009)

**Estado:** instrumento de diagnóstico implementado en GitHub. **No autoriza conversión, migración de reglas, despliegue, G5 ni G10.**

## Justificación

El contrato `legacy-v1` se fijó al crear los mundos existentes y no cambia durante la migración SQL `0020`. Con el almacén máximo en nivel 20, la Maravilla no puede pagar de una vez el coste del nivel 10, pero el nivel 100 es necesario para la victoria. `alliance-v2` permite financiar niveles entre miembros y ya tiene pruebas backend/E2E; convertir un mundo histórico sin acuerdo explícito rompería **PD-009**.

El bloqueo P1 [#149](https://github.com/luis12duboqwe/Batallas-mediavales/issues/149) no debe darse por resuelto simplemente porque los mundos nuevos son viables.

## Herramienta de lectura

Desde un entorno de operador autorizado que tenga acceso **de solo lectura** a la base:

```bash
python scripts/audit_legacy_wonder.py --world-id 123
```

**Requisito de esquema:** necesita Alembic `0020_wonder_funding` o posterior: el esquema anterior `0019` aún no contiene `wonder_rules_version` ni las tablas de aportaciones. Para evaluar un preview histórico que continúe en `0019`, se debe ensayar la migración **exclusivamente en una copia aislada**; no ejecutar el informe contra el entorno instalado ni aplicarle migraciones por conveniencia.

Se usa la configuración normal `DATABASE_URL` del backend; **no poner contraseñas en argumentos, URLs ni repositorio**. La herramienta exige un ID de mundo positivo, abre una sesión SQLAlchemy, solo hace consultas agregadas sin autoflush ni commit y la cierra. No cuenta con opción `--apply`, no llama a la API administrativa y no ejecuta migraciones. La salida JSON no incluye nombres de usuario, email, coordenadas ni otros datos de identificación.

El reporte incluye: versión de reglas, estado del mundo, membresías de jugadores, enlaces históricos `users.world_id` (incluidas las filas sin membresía normalizada), ciudades con dueño sin membresía de ese mismo mundo, alianzas y miembros, nivel máximo de Maravilla existente, colas pendientes, proyectos y aportaciones, costes legacy del nivel 10, techo de almacén, y códigos deterministas de bloqueo. Incluso si la lista de obstáculos está vacía, **`can_auto_convert=false` y `requires_product_approval=true`**.

La auditoría consulta directamente las columnas persistidas para no mezclar cambios sin guardar en la sesión con los conteos SQL; no refresca ni muta las entidades existentes del llamador. La lectura es un **snapshot informativo**, no una barrera transaccional frente a escritores concurrentes. Para decidir cualquier operación, debe repetirse tras pausar el mundo y comprobarse otra vez bajo controles de concurrencia y copia recuperable.

## Política no implementada

Antes de escribir un procedimiento de conversión, hace falta decisión explícita y documentada de producto sobre:

- Continuidad del mundo y aceptación de cada jugador o conservación como histórico sin cambios; alternativa de abrir una nueva temporada `alliance-v2`.
- Tratamiento de las colas legacy en curso, recursos ya gastados, niveles de Maravilla construidos y clasificación. No reembolsar, duplicar fondos ni restablecer niveles silenciosamente.
- Selección y aceptación de alianza patrocinadora y pérdida/traspaso de ciudades. La migración debe conservar otras reglas de mundo y el contrato de combate.
- Pausa transaccional, autorización de operadores, auditoría, snapshot, rollback completo y confirmación `HEAD == release desplegada` antes de habilitar a usuarios.

**No usar** el script para afirmar que el mundo es convertible, alterar `wonder_rules_version` manualmente ni cerrar el P1. La herramienta se puede validar sin cuentas reales en los tests `tests/test_bm0062_legacy_transition_audit.py`.

## Criterios de cierre de la fase de preparación en GitHub

1. Informe determinista, sin PII y no destructivo; mundo inexistente, reglas desconocidas, activo, cerrado/ganador y entrada inválida rechazados/reportados.
2. Colas, niveles y fondos preexistentes detectados; no mezclar datos de otros mundos.
3. Casos sin miembros, con alianza y permisos, y sesión con operaciones pendientes: cero escrituras y aprobación siempre externa.
4. CI sobre HEAD exacto, revisión adversarial y fusión antes de declarar que la **herramienta** está terminada. Este paso no resuelve P1/G5/G10.
