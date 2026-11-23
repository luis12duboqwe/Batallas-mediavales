# BM-0093/G5 — Identidad separada de migraciones y aplicación

**Estado: overlay opt-in de laboratorio, NO-GO para staging y producción.**
No se agregó a `ops/deploy_remote.sh` ni a workflows de despliegue.
Esta etapa no crea roles, no cambia credenciales y no activa un corte real.

## Problema

La configuración `docker-compose.deploy.yml` conecta `backend`, `worker`,
`migrate` y `seed` con la misma variable `DB_URL`. Un futuro G5 que
deshabilita `LOGIN` para la cuenta de juego bloquearía también la ejecución
controlada de migraciones. Peor aún, la configuración de referencia reutiliza
la cuenta elevada `POSTGRES_USER` para todos los procesos.

## Diseño opt-in

`docker-compose.g5-migration.yml` cambia `DATABASE_URL` **exclusivamente**
en los servicios de una ejecución `migrate` y `seed` para usar
`G5_MIGRATION_DB_URL`. `backend` y `worker` retienen la cuenta de juego
en `DB_URL`. El overlay no se instala automáticamente.

`ops/g5_migration_role_identity.py` proporciona `validate_split(values)`
para revisar datos sin ejecutar Docker ni SQL. Exige que ambas URL:

- utilicen PostgreSQL y el mismo destino `database:5432/POSTGRES_DB`;
- tengan usuarios y contraseñas explícitos y distintos;
- asignen `DB_URL` a una cuenta de aplicación distinta del administrador;
- asignen `G5_MIGRATION_DB_URL` al usuario `POSTGRES_USER` y a su secreto;
- no contengan destino alternativo, parámetros que cambien conexión, fragmentos,
  interpolación `# BM-0093/G5 — Identidad separada de migraciones y aplicación

**Estado: overlay opt-in de laboratorio, NO-GO para staging y producción.**
No se agregó a `ops/deploy_remote.sh` ni a workflows de despliegue.
Esta etapa no crea roles, no cambia credenciales y no activa un corte real.

## Problema

La configuración `docker-compose.deploy.yml` conecta `backend`, `worker`,
`migrate` y `seed` con la misma variable `DB_URL`. Un futuro G5 que
deshabilita `LOGIN` para la cuenta de juego bloquearía también la ejecución
controlada de migraciones. Peor aún, la configuración de referencia reutiliza
la cuenta elevada `POSTGRES_USER` para todos los procesos.

## Diseño opt-in

`docker-compose.g5-migration.yml` cambia `DATABASE_URL` **exclusivamente**
en los servicios de una ejecución `migrate` y `seed` para usar
`G5_MIGRATION_DB_URL`. `backend` y `worker` retienen la cuenta de juego
en `DB_URL`. El overlay no se instala automáticamente.

`ops/g5_migration_role_identity.py` proporciona `validate_split(values)`
para revisar datos sin ejecutar Docker ni SQL. Exige que ambas URL:

- utilicen PostgreSQL y el mismo destino `database:5432/POSTGRES_DB`;
- tengan usuarios y contraseñas explícitos y distintos;
- asignen `DB_URL` a una cuenta de aplicación distinta del administrador;
- asignen `G5_MIGRATION_DB_URL` al usuario `POSTGRES_USER` y a su secreto;
 ni caracteres de control;
- no contengan un `@` crudo adicional en el user-info. Las contraseñas con `@`
  deben codificarse como `%40`, pues `urlsplit` y SQLAlchemy pueden elegir
  distintos separadores de host ante delimitadores sin escape;
- usen el **nombre de base sin codificación porcentual** en la ruta. SQLAlchemy
  2.0 mantiene el path de database codificado aunque `urllib.unquote` lo
  convierta a otro texto; no puede certificarse como el mismo destino.

La validación evita imprimir contraseñas o URL completas.

**Importante:** esta es una comprobación de identidad declarada, NO una
certificación de permisos: otro proceso puede tener credenciales privilegiadas,
una cuenta puede ser miembro de roles peligrosos y servicios manuales pueden
escribir fuera del control de Compose. El inspector real de privilegios y la
barrera SQL del PR #197 deben certificarlo. No use el overlay con las
credenciales de ejemplo; nunca coloque secretos reales en Git.

## Pruebas

`tests/test_g5_migration_role_identity.py` verifica casos positivos,
contraseñas compartidas, usuarios privilegiados, URLs maliciosas,
interpolación, puertos y bases alternativos, credenciales ausentes y
separación de los servicios afectados.

`ops/ci_verify.sh` ahora ejercita la interpolación real de Compose con
valores **sintéticos**: el overlay debe fallar cuando falta
`G5_MIGRATION_DB_URL`, y con ella debe comprobar que `backend/worker`
conservan `game_app` y `migrate/seed` usan `batalla`. Solo ejecuta
`docker compose config`, sin arrancar contenedores ni tocar datos.

## Trabajo restante de #174

La cuenta `game_app` todavía debe aprovisionarse de forma controlada con
privilegios mínimos y ser compatible con el ORM y los trabajos existentes.
El coordinador G5 debe:

1. Bloquear a todos los escritores externos, cerrar admisión HTTP y sockets;
2. Retener el lock y el estado duradero durante todo el cambio;
3. Ejecutar migraciones únicamente a través de la identidad de mantenimiento
   después del respaldo protegido, con pruebas de rollback y esquemas;
4. Validar al final la release antes de permitir conexiones de `game_app`
   otra vez, con un protocolo de reactivación independiente y certificado.

**No se desplegó ni se autorizó el VPS. #174 sigue P1 y G5 sigue NO-GO.**
