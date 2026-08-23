# G5 — Evidencia de preparación para beta cerrada

Estado: **AUTOMATIZACIÓN PREPARADA / NO-GO PARA USUARIOS EXTERNOS**

Fecha de evidencia automatizada más reciente: 2026-08-23 (America/Tegucigalpa).

Este documento registra qué parte de la puerta G5 ya tiene evidencia reproducible dentro del repositorio y qué parte continúa bloqueada hasta disponer de infraestructura real de staging y aprobación explícita del propietario.

## 1. Checkpoint automatizado más reciente

PR de hardening operativo: `#90 feat(G5): operación reproducible de beta cerrada`.

Checkpoint validado antes de actualizar únicamente esta evidencia:

- HEAD: `ec5a01ddf3d74f55450cfed343d87355482a7464`
- Validation: `#262`
- run id: `32662872850`

Resultado:

- Backend: **SUCCESS**
- PostgreSQL concurrency: **SUCCESS**
- Frontend lint + build: **SUCCESS**
- Browser E2E G2 + G4: **SUCCESS**
- G5 operations recovery: **SUCCESS**
- Dependency and security audit: **SUCCESS**
  - auditoría Python: SUCCESS
  - análisis estático de seguridad de severidad/confianza altas: SUCCESS
  - auditoría npm de severidad alta: SUCCESS
- Container image backend: **SUCCESS**
- Container image frontend: **SUCCESS**

La actualización de este archivo mueve el HEAD y, por política del proyecto, requiere una Validation final completa sobre el nuevo SHA antes de fusionar el hardening.

El checkpoint anterior de preparación G5 (`#256`, run `32445522172`) ya había demostrado la cadena inicial de recuperación. El checkpoint #262 vuelve a ejecutar esa evidencia después del hardening TLS y añade las validaciones de hostname/puertos del entorno protegido.

## 2. Recuperación probada automáticamente

El gate `G5 operations recovery` ejecuta un ciclo real sobre PostgreSQL y Compose:

1. valida un entorno protegido correcto;
2. demuestra que preflight rechaza una imagen `:latest`;
3. demuestra que preflight rechaza `PUBLIC_HOST` que no coincide con la URL pública HTTPS;
4. valida sintaxis de scripts y configuración Compose, incluida la capa Caddy;
5. inicia PostgreSQL real;
6. crea un dato marcador;
7. genera un `pg_dump` custom;
8. comprueba que el dump y su SHA-256 existen y son válidos;
9. modifica el dato después del backup;
10. restaura el dump con `pg_restore`;
11. comprueba que reaparece exactamente el valor previo al backup;
12. ejecuta smoke HTTP local controlado;
13. ejecuta carga concurrente corta sin errores y dentro del presupuesto.

Esto demuestra que la herramienta de backup/restore es funcional. **No sustituye el drill obligatorio sobre el staging real**.

## 3. Despliegue reproducible preparado

La preparación G5 incluye:

- `docker-compose.deploy.yml` sin builds locales;
- imágenes de aplicación inmutables por SHA de commit;
- Caddy `2.10.2-alpine` como único edge público del stack protegido;
- Nginx interno conservando rate-limit, API y WebSocket;
- certificados TLS automáticos y persistentes mediante volúmenes de Caddy;
- `.github/workflows/deploy.yml` con bundle remoto versionado que incluye `Caddyfile`;
- rechazo de producción fuera de `main`;
- `ops/preflight.py` antes de mutar servicios;
- snapshot PostgreSQL previo a migración cuando ya existe esquema;
- migraciones y seed como jobs de una ejecución;
- espera activa de HTTPS/certificado antes de aceptar la release;
- smoke HTTPS posterior al deploy;
- carga acotada posterior al deploy;
- rollback automático de aplicación, base y edge si el checkpoint posterior falla;
- manifests de releases para rollback manual.

## 4. Configuración protegida exigida

`ops/preflight.py` exige para staging/producción:

- `APP_ENV=staging|production`;
- `SECRET_KEY` fuerte;
- PostgreSQL;
- `PUBLIC_HOST` DNS válido y coincidente con `PUBLIC_BASE_URL`;
- `TLS_EMAIL` válido;
- puertos HTTP/HTTPS válidos y distintos;
- URLs públicas HTTPS;
- CORS explícito y HTTPS;
- SMTP y remitente válido;
- `SUPPORT_CONTACT` válido;
- imágenes inmutables y nunca `:latest`;
- directorio/retención de backup;
- presupuestos válidos de duración, concurrencia, p95 y tasa de error.

Por tanto una configuración que únicamente declare una URL HTTPS pero no tenga un contrato de dominio/certificado coherente es rechazada antes del despliegue.

## 5. Observabilidad y duración preparadas

Se incorporaron:

- `staging-health.yml`: smoke + carga corta cada hora;
- webhook opcional para fallo de staging;
- `staging-soak.yml`: prueba sostenida diaria de 15 minutos;
- opciones manuales de soak de 30 o 60 minutos;
- smoke posterior al soak;
- `install_backup_cron.sh`: instalación idempotente del backup diario en un host que use cron.

Estas tareas solo producen evidencia real cuando `STAGING_BASE_URL` y el host de staging están configurados.

## 6. Seguridad

Evidencia automatizada actual:

- dependencias Python auditadas;
- dependencias frontend auditadas a severidad alta;
- análisis estático del backend con puerta de alta severidad y alta confianza;
- `SECURITY.md` para reporte responsable;
- secretos y estado operativo excluidos por `.gitignore`;
- despliegues protegidos sin `latest`;
- Nginx no se expone directamente en el stack protegido;
- Caddy añade HSTS, `nosniff`, `DENY` para framing y política de referrer;
- credenciales del registro transmitidas por stdin;
- configuración sensible suministrada como secretos del ambiente, no versionada.

## 7. P0/P1

Comprobación más reciente durante el checkpoint #262:

- issues abiertos del repositorio: **0**

Por tanto no existen P0/P1 **registrados en GitHub** pendientes en este checkpoint. Esto debe volver a comprobarse inmediatamente antes de autorizar una oleada de beta.

## 8. Operación, privacidad y soporte versionados

Documentos incorporados:

- `docs/G5_OPERATIONS_RUNBOOK.md`
- `docs/BETA_PRIVACY_RETENTION_TERMS.md`
- `docs/G5_SUPPORT_AND_BETA_POLICY.md`
- `SECURITY.md`

Cubren despliegue, TLS, rollback, restore, backups, SLO inicial, monitorización, rotación de secretos, respuesta a incidentes, clasificación P0–P3, soporte, retención y baseline de términos/privacidad.

Los textos legales siguen marcados como baseline de beta y requieren completar operador, jurisdicción, contacto e infraestructura reales antes de publicación externa.

## 9. Presupuesto operativo inicial

Para los probes acordados de beta cerrada:

- HTTP 5xx aceptados: **0**;
- tasa total de error máxima: **0.5%**;
- p95 máximo en lectura estable: **750 ms**;
- una configuración más laxa requiere decisión explícita y documentada.

## 10. Lo que falta para aprobar G5

La puerta G5 **no está aprobada todavía**. Falta evidencia externa de:

- [ ] staging real desplegado desde el workflow versionado;
- [ ] DNS real de `PUBLIC_HOST` apuntando al servidor;
- [ ] TLS real emitido/renovable y verificado de extremo a extremo;
- [ ] SMTP real verificado;
- [ ] canal `SUPPORT_CONTACT` real;
- [ ] migración de staging exitosa;
- [ ] backup de staging real y copia recuperable;
- [ ] restore drill de staging real;
- [ ] smoke HTTPS real dentro de presupuesto;
- [ ] carga real dentro de presupuesto;
- [ ] soak real dentro de presupuesto;
- [ ] monitor horario activo y al menos una ejecución verde reciente;
- [ ] alertas verificadas;
- [ ] placeholders de privacidad/términos completados con datos reales;
- [ ] comprobación final de cero P0/P1;
- [ ] rollback real de aplicación y base ensayado en staging;
- [ ] **aprobación explícita del propietario para abrir la beta**.

Hasta completar todos los puntos anteriores, el estado correcto del producto es:

> **G5 AUTOMATION READY — CLOSED BETA NO-GO**
