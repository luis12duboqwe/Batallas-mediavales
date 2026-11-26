# G5 — Migración real del juego con identidad de mantenimiento (#174)

**Ensayo GitHub CI, no producción.**

Usa la imagen backend recién construida por Validation, una instancia
PostgreSQL 15 desechable y una red interna Docker sin puertos públicos.
No consume variables/secretos de ningún ambiente de despliegue ni inicia
backend o worker del juego. El fixture se limpia por etiqueta y no reutiliza
volúmenes existentes.

- Aplica Alembic real hasta 0019_privacy_active_unique.
- Crea un mundo histórico mediante un commit real de la identidad app,
  usando permisos DML y secuencia, sin permisos DDL ni de modificar
  alembic_version. Exige rechazo explícito de esas operaciones.
- Activa Pg15PersistentFence y verifica NOLOGIN y límite de conexiones.
- Ejecuta Alembic real a 0020_wonder_funding y el seed canónico dos veces
  como identidad de mantenimiento, con verificaciones de cierre entre pasos.
- Conserva ID/nombre del mundo histórico y sus reglas legacy-v1.
  Comprueba que Mundo 1 nuevo usa alliance-v2 y que el recuento de
  ciudades permanece estable tras repetir seed.
- Reaplica permisos del fixture a tablas/secuencias nuevas; verifica
  wonder_funding, wonder_contributions y exclusión de metadatos Alembic
  y DDL. La identidad app permanece bloqueada hasta terminar el ensayo.

La concesión de permisos usada es exclusiva del fixture; **no** es un
provisionador operativo ni un inventario definitivo de privilegios mínimos.
El ensayo está fijado al último salto real de esquema para que futuras
revisiones obliguen a actualizar explícitamente el caso. Todavía debe
integrarse el ejecutor real con el coordinador de ciclo de vida y comprobarse
el rollback completo, incluida eliminación de objetos nuevos y preservación
de roles, permisos y metadata. No se autoriza reapertura ni staging.
