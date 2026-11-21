# BM-0092 / BM-0093 — Checkpoint G5 y seguimiento de fases (20-11-2026)

**Autoridad:** [Plan Maestro v2.0](PLAN_MAESTRO_DESARROLLO.md), sección 7 (G0–G10), sección 11 (Definition of Done) y sección 14 (gobierno del plan).  
**Fase activa de certificación:** **Fase 5 — G5, NO-GO para usuarios externos.**  
**Tipo de inspección:** lectura y pruebas HTTP GET no destructivas; **sin despliegue, migración, restauración, cambio de configuración ni activación pública**.  
**Corte:** 2026-11-20, aproximadamente 20:04 America/Tegucigalpa.

> El avance del código no sustituye las puertas de salida. Las fases 6–8 tienen cambios integrados, pero no deben presentarse como aprobadas mientras G5 y sus gates posteriores carezcan de evidencia formal.

## 1. Versiones y evidencia comprobada

| Comprobación | Resultado y fuente |
|---|---|
| HEAD de `main` | `264237860ef08348f082e37d1ea1579b6ab58e68` |
| CI de `main` | **PASS**: [Validation run 44843795772](https://github.com/luis12duboqwe/Batallas-mediavales/actions/runs/44843795772) y [Independent player journeys run 44843795781](https://github.com/luis12duboqwe/Batallas-mediavales/actions/runs/44843795781), ambas sobre el HEAD indicado |
| Checkout del VPS | `/opt/medievol-preview` en `d8a37e17ba6629ba06481c38e39b015ed448c69f`, **13 commits detrás de main**, no equivale a la release certificada |
| Servicio | Siete contenedores `medievol-preview-*` iniciados y con **0 reinicios**; backend, frontend, PostgreSQL y Mailpit saludables según Docker. Worker corriendo **sin healthcheck definido**, no se presupone su salud funcional |
| Salud API | `GET /health` directo al backend **200**; `GET /health` por HTTPS externo **200** y verificación TLS correcta |
| Certificado HTTPS de preview | Let's Encrypt, válido desde 2026-11-20 hasta **2027-02-18**. Prueba solo HTTPS del *preview*, no la cadena de release y monitoreo G5 |
| Accesos anónimos | Home **401**, inbox Mailpit **401**, `/api/auth/me` **401**. Solo se verificaron estas rutas por GET |
| Esquema de PostgreSQL desplegado | `alembic_version = 0019_privacy_active_unique`; `main` integra migración **0020** en PR #155. Requiere ensayo aislado antes de actualizar el preview |
| Monitor programado G5 | `Staging Health` se omite en runs [44849408551](https://github.com/luis12duboqwe/Batallas-mediavales/actions/runs/44849408551) y [44845029996](https://github.com/luis12duboqwe/Batallas-mediavales/actions/runs/44845029996). El workflow exige `vars.STAGING_BASE_URL != ''`; **no existe una ejecución verde reciente de este monitor** |
| Correo | El preview utiliza **Mailpit**, útil para pruebas; **no demuestra SMTP real** para usuarios externos |
| Checkout limpio | **No**: dos archivos locales modificados (`app/routers/__init__.py` y `tests/test_scheduler_worker.py`). Frente a main, el primero coincide exactamente y el segundo solo difiere por una línea vacía final. Aun así, no hacer reset ni desplegar sobre el worktree sucio |

No se accedió a contraseñas, tokens, bases de datos de usuarios ni buzones. No se realizaron modificaciones en el VPS.

## 2. Seguimiento canónico por puertas

| Puerta | Estado verificable en este corte | Siguiente acción |
|---|---|---|
| G0–G4 | Trabajo histórico y pruebas integradas; este checkpoint **no reabre ni recertifica** sus actas | Conservar evidencia vinculada al commit correspondiente |
| **G5** | **ACTIVA — NO-GO**. Hay preview funcional, pero no staging completo con todos los simulacros y aprobación | Resolver la matriz de la sección 3 |
| G6 | Mecánicas implementadas en gran parte; **no certificadas como paquete** | Certificar catálogo, migraciones, economía, combate, héroe y Maravilla después de G5 |
| G7 | Sistemas de comunidad/mundos presentes; **sin gate G7 final aquí** | Matriz de permisos, abuso, ciclos de mundo y runbooks |
| G8 | Cambios de UX, accesibilidad, localización y rendimiento integrados; **sin gate G8 final aquí** | Pruebas con dispositivos, presupuesto visual y aceptación de usuarios |
| G9 | **No aprobado** | Seguridad, legalidad, cargas, restore, soporte y sostenibilidad productiva |
| G10 | **No aprobado** | Lanzamiento por oleadas, observación, resolución P0/P1, acta y tag exactos |
| G11 | Fuera del cierre v1.0 | Solo después de G10 |

**Regla operativa:** una fase activa de **certificación: G5**. El código futuro no se considera avance cerrado sin la evidencia de su gate. No añadir funciones fuera de v1.0 para sustituir trabajo de estabilización.

## 3. Requisitos de salida G5 — matriz de comprobación

| Requisito del Plan Maestro / runbook | Situación |
|---|---|
| Validation verde en HEAD exacto | **Comprobado** en main `26423786`; no equivale a validar el commit instalado en el VPS |
| Staging real desde workflow con release inmutable | **Pendiente**. Vista previa desplegada a commit anterior; no se verificó despliegue mediante workflow de staging |
| DNS, TLS y HTTPS de staging | **Parcial**: preview válido; el entorno final aprobado aún no está certificado |
| Migración real y rollback de datos de staging | **Pendiente**: preview en Alembic 0019; PR #155 añade 0020 |
| Backup íntegro y restore drill sobre staging | **Sin evidencia real en esta inspección**; gate CI con fixtures no reemplaza staging |
| Smoke HTTP y carga/soak de larga duración | **Parcial**: solo GET de salud comprobados; no se ejecutó carga ni soak |
| Monitor horario, métricas y alertas | **Pendiente**: últimas ejecuciones programadas omitidas; falta prueba real de alerta |
| Cero P0/P1 conocidos | **NO CUMPLIDO**: [P1 #149](https://github.com/luis12duboqwe/Batallas-mediavales/issues/149) sigue abierto (Maravilla de mundos históricos). También está [P2 #156](https://github.com/luis12duboqwe/Batallas-mediavales/issues/156) para E2E de Maravilla v2 |
| SMTP real y contacto de soporte | **Pendiente de certificar**: solo se encontró Mailpit en el preview |
| Privacidad, términos, retención y datos reales del operador | **Pendiente de verificación/cierre** (ver baseline en `BETA_PRIVACY_RETENTION_TERMS.md`) |
| Simulacro de rollback de aplicación y BD | **No ejecutado sobre staging en esta inspección** |
| Aprobación expresa para abrir beta externa | **No concedida**; sigue NO-GO |

La documentación G5 de agosto es **histórica**: su referencia a cero incidencias P0/P1 no representa el estado del 20 de noviembre.

## 4. Orden de ejecución sin saltar de fase

1. **BM-0092 — Preparación segura del staging:** preservar checkout actual, comparar modificaciones locales, construir una release limpia y ensayar la migración 0019→0020 sobre una **copia aislada**. No tocar datos vivos ni desplegar a público en esta tarea.
2. **BM-0092 / BM-0050 / BM-0052 — Certificación del entorno:** registrar versión/despliegue verificado, configurar y ejecutar monitor G5, TLS, SMTP de prueba controlada, smoke y carga/soak con presupuesto. Configuraciones externas y apertura pública tienen su propia autorización.
3. **BM-0093 / BM-0051 — Recuperación:** ensayo documentado de backup→restore, rollback y fallo de dependencia en un staging recuperable, con hashes, RPO/RTO y pruebas después de restaurar.
4. **BM-0090 — Soporte y legal:** sustituir placeholders, validar contacto y políticas aplicables.
5. **BM-0101 — Bloqueos P1/P2:** cerrar técnicamente #149 y certificar #156 (sin mezclarlo con la puesta en marcha del staging); revalidar cero P0/P1.
6. **G5 — Decisión final:** anexar evidencia con commit y release **idénticos**, obtener aprobación del propietario **solo cuando todo lo anterior cumpla**. Después iniciar cierre formal de G6, G7, G8, G9 y G10, en ese orden.

**Cierre de esta auditoría:** verificación **parcial de funcionamiento del preview**, no aprobación G5, no lanzamiento ni operación productiva.