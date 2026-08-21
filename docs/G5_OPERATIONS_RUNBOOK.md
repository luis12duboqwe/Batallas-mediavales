# G5 — Runbook de operación de beta cerrada

Estado: **PREPARADO EN REPOSITORIO / PENDIENTE DE STAGING REAL**

Este documento define el procedimiento operativo mínimo para desplegar, verificar, respaldar, restaurar y revertir Batalla Medieval durante la beta cerrada. La puerta G5 no se considera aprobada hasta que estas acciones se ejecuten contra un staging real y exista aprobación explícita del propietario del producto.

## 1. Arquitectura operativa

La topología esperada es:

1. dominio público con TLS gestionado por un edge, load balancer o reverse proxy administrado;
2. `nginx` del stack como entrada HTTP interna;
3. frontend estático y API/Socket.IO detrás de `nginx`;
4. API y worker separados;
5. PostgreSQL persistente;
6. migraciones y seed ejecutados como trabajos de una sola ejecución;
7. imágenes de backend/frontend identificadas por el SHA exacto del commit desplegado.

No se utiliza `:latest` para una release protegida. `ops/preflight.py` rechaza imágenes mutables y configuraciones protegidas sin HTTPS público, PostgreSQL, SMTP, CORS explícito, secreto fuerte o política de backup.

## 2. Variables y secretos de GitHub

Crear ambientes de GitHub llamados `staging` y `production`.

Secretos requeridos por ambiente:

- `SSH_HOST`: host del servidor;
- `SSH_USER`: usuario de despliegue con acceso a Docker;
- `SSH_PORT`: puerto SSH, normalmente 22;
- `SSH_PRIVATE_KEY`: llave privada de despliegue;
- `REMOTE_APP_DIR`: directorio remoto, por ejemplo `/opt/batalla-medieval`;
- `ENV_FILE_BASE64`: contenido base64 del archivo de entorno protegido;
- `REGISTRY_USERNAME`: opcional si `github.actor` puede acceder a GHCR;
- `REGISTRY_PASSWORD`: opcional si `github.token` puede acceder a GHCR;
- `ALERT_WEBHOOK_URL`: opcional para alertas externas de staging.

Variable de GitHub del ambiente `staging`:

- `STAGING_BASE_URL`: URL HTTPS pública usada por `.github/workflows/staging-health.yml`.

El archivo de entorno puede prepararse tomando `ops/staging.env.example`, reemplazando todos los placeholders y codificándolo en base64. El texto plano no se debe almacenar en el repositorio.

## 3. Requisitos del host

- Linux actualizado;
- Docker Engine y Docker Compose v2;
- Python 3.11+ disponible para los probes sin dependencias;
- usuario de despliegue autorizado para Docker;
- almacenamiento persistente suficiente para PostgreSQL y backups;
- edge/TLS operativo antes del primer smoke protegido;
- DNS del dominio apuntando al edge correcto;
- SMTP funcional para verificación/recuperación de cuenta.

## 4. Despliegue normal

El workflow `.github/workflows/deploy.yml` se ejecuta manualmente.

### Staging

1. seleccionar la rama/commit a verificar;
2. elegir `staging`;
3. el workflow construye y publica imágenes con `${github.sha}`;
4. sube `docker-compose.deploy.yml`, `nginx.conf` y `ops/` al host;
5. reconstruye `.env.base` desde `ENV_FILE_BASE64`;
6. `ops/deploy_remote.sh` añade las referencias inmutables de imagen;
7. se ejecuta preflight antes de mutar servicios;
8. si ya existe esquema, se crea backup verificado;
9. se aplican migraciones y seed;
10. se levantan API, worker, frontend y proxy;
11. se ejecuta smoke HTTP;
12. se ejecuta carga acotada;
13. solo si todo pasa se registra la release en `.ops-state/` y `.release-sha`.

### Producción

El workflow rechaza producción si el dispatch no parte de `main`. Antes de habilitar la beta pública/cerrada debe existir aprobación explícita del propietario y, preferiblemente, protección de aprobación en el ambiente `production` de GitHub.

## 5. Rollback automático

`ops/deploy_remote.sh` mantiene un trap de error durante migración, arranque, smoke y carga.

Si una release falla después de haber tomado snapshot:

- restaura el `.env` de la release anterior;
- restaura el snapshot de PostgreSQL previo al deploy;
- vuelve a levantar las imágenes anteriores;
- conserva `.release-sha` apuntando a la última release válida.

Si es el primer despliegue y no existe release anterior, no se inventa rollback: los servicios quedan disponibles para diagnóstico y el deploy termina con error.

## 6. Rollback manual

Identificar el SHA actual desde `.release-sha` y ejecutar:

```bash
bash ops/rollback_remote.sh <SHA_ACTUAL> ROLLBACK:<SHA_ACTUAL>
```

El script exige:

- manifest de despliegue de la release actual;
- referencia válida a release anterior;
- `.env` archivado de la release anterior;
- snapshot asociado cuando corresponde;
- preflight de la release de destino;
- smoke posterior al rollback.

Nunca editar manualmente `.release-sha` para simular un rollback.

## 7. Backups

Backup manual:

```bash
COMPOSE_FILE=docker-compose.deploy.yml bash ops/backup_postgres.sh .release.env
```

Cada backup:

- usa `pg_dump --format=custom`;
- se escribe primero a archivo temporal;
- no se publica si queda vacío;
- genera `.sha256`;
- verifica inmediatamente el checksum;
- aplica permisos restrictivos;
- elimina backups más antiguos que `BACKUP_RETENTION_DAYS`.

Para G5, staging debe demostrar al menos un ciclo backup→mutación→restore. CI ya reproduce ese ciclo sobre PostgreSQL real mediante `G5 operations recovery`; falta repetirlo en el staging real.

Se recomienda copiar backups fuera del mismo disco/host. La beta no debe depender de un único volumen como única copia recuperable.

## 8. Restauración

Restaurar es destructivo y requiere confirmación explícita:

```bash
bash ops/restore_postgres.sh .release.env /ruta/backup.dump RESTORE:<POSTGRES_DB>
```

El script:

1. valida entorno;
2. exige checksum;
3. detiene API y worker;
4. termina conexiones a la base;
5. usa `pg_restore --clean --if-exists --create --exit-on-error`;
6. vuelve a levantar la release seleccionada;
7. exige que el operador ejecute smoke antes de cerrar mantenimiento.

`RESTORE_START_SERVICES=0` existe únicamente para el drill automatizado de CI.

## 9. Smoke, carga y SLO iniciales

Smoke protegido:

```bash
python3 ops/smoke_http.py --base-url https://staging.example.com --requests 20 --max-p95-ms 750
```

Carga acotada:

```bash
python3 ops/load_smoke.py \
  --base-url https://staging.example.com \
  --duration-seconds 15 \
  --concurrency 8 \
  --max-p95-ms 750 \
  --max-error-rate 0.005
```

Presupuesto inicial G5:

- cero HTTP 5xx durante probes aceptados;
- error total <= 0.5%;
- p95 <= 750 ms para el endpoint de balance usado como lectura estable;
- cualquier presupuesto más laxo requiere una decisión explícita y documentada.

Estos límites son de beta cerrada, no una promesa de capacidad final.

## 10. Monitorización y alertas

`.github/workflows/staging-health.yml` ejecuta cada hora:

- smoke completo;
- carga corta;
- fallo visible en GitHub Actions;
- webhook opcional mediante `ALERT_WEBHOOK_URL`.

Antes de abrir beta, `STAGING_BASE_URL` debe estar configurada y debe existir evidencia de al menos una ejecución verde reciente.

## 11. Rotación de secretos

Rotar inmediatamente cuando:

- una llave pudo quedar expuesta;
- cambia el personal autorizado;
- se reemplaza proveedor SMTP/infra;
- se sospecha acceso no autorizado.

Procedimiento:

1. crear secreto nuevo;
2. actualizar el ambiente GitHub o `.env.base` protegido;
3. desplegar release/configuración;
4. comprobar login, Socket.IO, correo y smoke;
5. revocar el secreto anterior;
6. documentar fecha, alcance y responsable sin registrar el valor secreto.

Para `SECRET_KEY`, considerar que la rotación invalida tokens existentes; debe ejecutarse en ventana controlada.

## 12. Incidentes

Clasificación mínima:

- **P0**: pérdida/corrupción de datos, compromiso de credenciales/seguridad, indisponibilidad general sin workaround, rollback/restore imposible;
- **P1**: función crítica del ciclo de juego o autenticación inutilizable para un grupo relevante, errores 5xx sostenidos o latencia muy fuera del presupuesto;
- **P2/P3**: degradaciones no críticas, UX o defectos con workaround.

Ante P0/P1:

1. congelar nuevos despliegues;
2. registrar SHA activo y hora;
3. revisar salud de contenedores y logs;
4. si el incidente coincide con un deploy, rollback inmediato;
5. si hay sospecha de datos, preservar evidencia antes de limpiar;
6. rotar secretos si aplica;
7. validar recuperación con smoke;
8. abrir issue con causa, impacto, corrección y prevención;
9. no ampliar la beta hasta cerrar P0/P1.

## 13. Criterio de salida G5

G5 solo puede marcarse APROBADO cuando exista evidencia reciente de:

- Validation completa verde;
- staging real desplegado desde el workflow;
- migración real exitosa;
- backup real y restore drill real;
- smoke/carga dentro de presupuesto;
- monitor de staging funcionando;
- cero P0/P1 abiertos;
- privacidad, términos, retención y soporte definidos;
- rollback de aplicación y base probado;
- aprobación explícita del propietario para abrir la beta.
