# G5 — Readiness del monitor programado de staging

Estado: **NOT READY mientras falte `STAGING_BASE_URL`; no implica aprobación de G5 ni habilitación de beta.**

Este documento registra únicamente el contrato operativo de los workflows programados. No configura secretos o variables, no despliega, no realiza solicitudes a staging externo y no convierte una omisión en evidencia verde.

## Diagnóstico de estado

- `STAGING_BASE_URL` debe ser una **variable de repositorio** para que `jobs.smoke.if` o `jobs.soak.if` se habiliten antes de entrar al environment `staging`.
- Una variable configurada solo en el environment puede dejar el job de probes en `skipped`.
- Si la variable está ausente, el workflow ejecuta un job explícito de readiness y deja el job real de health o soak en `skipped`.
- Ese resultado **no es éxito de health ni éxito de soak**. Solo demuestra que el workflow pudo informar una configuración incompleta de forma segura.
- Si la variable está configurada, el job correspondiente debe ejecutar los probes; un fallo del probe permanece como fallo del workflow aunque no exista webhook externo.

## Checklist seguro del operador

1. Confirmar que existe staging real con HTTPS y release identificable.
2. Crear `STAGING_BASE_URL` como **Variable de repositorio**; no insertar una URL real en GitHub, archivos, logs o documentación.
3. Confirmar el `environment: staging` y sus aprobaciones de acceso sin cambiar políticas desde este repositorio.
4. Si staging usa Basic auth, configurar por separado:
   - variable `STAGING_BASIC_AUTH_USERNAME`;
   - secreto `STAGING_BASIC_AUTH_PASSWORD`;
   - mantener ambos ausentes en pares en un staging sin Basic auth.
5. Si se desea notificar fuera de Actions, configurar `ALERT_WEBHOOK_URL`; la ausencia del webhook no elimina el fallo visible en Actions.
6. Ejecutar primero un dispatch manual y revisar el link del run, el summary de readiness y el resultado del probe.
7. Solo una ejecución manual y su schedule posterior con todos los pasos verdes cuentan como evidence de monitoring real.
8. Revisar el log sin exigir secretos ni imprimir el valor de `STAGING_BASE_URL` o credenciales.
9. Ante fallo configurado, conservar el run URL, el release SHA, el timestamp y la categoría de fallo; ejecutar el runbook de rollback si el fallo coincide con un deploy.
10. Cerrar incidentes P0/P1 y obtener aprobación expresa antes de hablar de G5 aprobado o beta habilitada.

## Contrato de autenticación protegida

El health y el soak deben pasar ambas credenciales a los probes. Una configuración parcial debe fallar cerradamente en el probe sin revelar el password. El probe rechaza HTTP, credenciales embebidas y redirecciones a otro origen. `STAGING_BASIC_AUTH_PASSWORD` debe existir solo como secreto del environment `staging`; nunca como variable, argumento visible o texto escrito en el repositorio.

## Evidencia aceptable

Evidencia real requiere:

- variable de repositorio configurada;
- job de probe ejecutado, no skipped;
- `smoke_http.py` y `load_smoke.py` dentro del presupuesto;
- soak ejecutado para la duración seleccionada;
- failure visible si un probe falla;
- release y commit identificables;
- revisión posterior de logs y alertas.

No usar este documento ni ejecuciones verdes anteriores como sustituto de staging real, migración, backup/restore, rollback, cero P0/P1 o aprobación del propietario.
