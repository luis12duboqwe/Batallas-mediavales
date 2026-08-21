# G5 — Evidencia de preparación para beta cerrada

Estado: **AUTOMATIZACIÓN PREPARADA / NO-GO PARA USUARIOS EXTERNOS**

Fecha de evidencia automatizada: 2026-08-20 (America/Tegucigalpa) / 2026-08-21 UTC.

Este documento registra qué parte de la puerta G5 ya tiene evidencia reproducible dentro del repositorio y qué parte continúa bloqueada hasta disponer de infraestructura real de staging y aprobación explícita del propietario.

## 1. Checkpoint automatizado verde

PR de preparación: `#89 feat(G5): preparar operación de beta cerrada`.

Checkpoint validado antes de añadir únicamente este documento:

- HEAD: `5d015cf9c93bb55acf8eea5f93c4349ebd15f1b1`
- Validation: `#256`
- run id: `32445522172`

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

La adición de este archivo mueve el HEAD y, por política del proyecto, requiere una Validation final completa sobre el nuevo SHA antes de fusionar la preparación.

## 2. Recuperación probada automáticamente

El gate `G5 operations recovery` ejecuta un ciclo real sobre PostgreSQL y Compose:

1. valida un entorno protegido correcto;
2. demuestra que preflight rechaza una imagen `:latest`;
3. valida sintaxis de scripts y configuración Compose;
4. inicia PostgreSQL real;
5. crea un dato marcador;
6. genera un `pg_dump` custom;
7. comprueba que el dump y su SHA-256 existen y son válidos;
8. modifica el dato después del backup;
9. restaura el dump con `pg_restore`;
10. comprueba que reaparece exactamente el valor previo al backup;
11. ejecuta smoke HTTP;
12. ejecuta carga concurrente corta sin errores y dentro del presupuesto.

Esto demuestra que la herramienta de backup/restore es funcional. **No sustituye el drill obligatorio sobre el staging real**.

## 3. Despliegue reproducible preparado

La preparación G5 incluye:

- `docker-compose.deploy.yml` sin builds locales;
- imágenes de aplicación inmutables por SHA de commit;
- `.github/workflows/deploy.yml` con bundle remoto versionado;
- rechazo de producción fuera de `main`;
- `ops/preflight.py` antes de mutar servicios;
- snapshot PostgreSQL previo a migración cuando ya existe esquema;
- migraciones y seed como jobs de una ejecución;
- smoke posterior al deploy;
- carga acotada posterior al deploy;
- rollback automático de aplicación y base si el checkpoint posterior falla;
- manifests de releases para rollback manual.

## 4. Configuración protegida exigida

`ops/preflight.py` exige para staging/producción:

- `APP_ENV=staging|production`;
- `SECRET_KEY` fuerte;
- PostgreSQL;
- URLs públicas HTTPS;
- CORS explícito y HTTPS;
- SMTP y remitente válido;
- `SUPPORT_CONTACT` válido;
- imágenes inmutables y nunca `:latest`;
- directorio/retención de backup;
- presupuestos válidos de duración, concurrencia, p95 y tasa de error.

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
- credenciales del registro transmitidas por stdin;
- configuración sensible suministrada como secretos del ambiente, no versionada.

## 7. P0/P1

Búsqueda de issues abiertos del repositorio realizada durante esta preparación:

- issues abiertos: **0**

Por tanto no existen P0/P1 **registrados en GitHub** pendientes en este checkpoint. Esto debe volver a comprobarse inmediatamente antes de autorizar una oleada de beta.

## 8. Operación, privacidad y soporte versionados

Documentos incorporados:

- `docs/G5_OPERATIONS_RUNBOOK.md`
- `docs/BETA_PRIVACY_RETENTION_TERMS.md`
- `docs/G5_SUPPORT_AND_BETA_POLICY.md`
- `SECURITY.md`

Cubren despliegue, rollback, restore, backups, SLO inicial, monitorización, rotación de secretos, respuesta a incidentes, clasificación P0–P3, soporte, retención y baseline de términos/privacidad.

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
- [ ] dominio y TLS reales verificados;
- [ ] SMTP real verificado;
- [ ] canal `SUPPORT_CONTACT` real;
- [ ] migración de staging exitosa;
- [ ] backup de staging real y copia recuperable;
- [ ] restore drill de staging real;
- [ ] smoke real dentro de presupuesto;
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
