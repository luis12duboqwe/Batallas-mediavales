# BM-0068 — Validación final: héroe, objetos y aventuras

Fecha de corte funcional: 2026-08-26

PR: #101  
Rama: `feature/BM-0068-hero-items-adventures-final`  
Base validada: `00ba1de88e8d095cd56fc8f7435157cddde61b0b`  
HEAD funcional validado: `2aa3e0dcf062b235617fb04767b679dcc9ecbfad`  
Workflow de evidencia funcional: Validation #506 (`run_id=32915913055`)

## Alcance validado

BM-0068 entrega el corte vertical de héroe, objetos y aventuras integrado con los sistemas vivos del juego y aislado por mundo.

El paquete validado incluye:

- héroe único por `(user_id, world_id)` con creación perezosa segura ante concurrencia;
- migraciones `0010` y `0011` para aislamiento por mundo, resultados persistidos y asignación de héroe a movimientos;
- reglas autoritativas versionadas `2026.08.25-bm0068-v1`;
- progresión de nivel, XP, salud, revive y puntos de atributos;
- catálogo canónico de objetos, slots, rarezas y equipamiento transaccional;
- bonos de ataque/defensa específicos por categoría de tropa y límites autoritativos;
- bonos conectados al combate real, producción y velocidad de marcha;
- progresión de XP de héroe atacante y defensor con normalización de niveles;
- aventuras con seed SHA-256 persistido, resultado persistido y claim retry-safe/exactly-once;
- recompensas de recursos limitadas por capacidad de almacén;
- API y UI de `/hero` y `/adventures` como superficie aceptada del juego;
- journey de navegador G13 para héroe, equipamiento, aventura, claim y retry;
- aislamiento multi-world y validaciones de concurrencia PostgreSQL.

## Correcciones realizadas durante el cierre

Durante la validación final se detectaron y corrigieron defectos reales antes de considerar BM-0068 listo:

1. **Carrera de creación del héroe en Browser E2E.**
   `/hero/` y `/hero/items` podían solicitar simultáneamente la creación perezosa del mismo héroe. PostgreSQL serializa mediante `FOR UPDATE`, pero SQLite usado por Browser E2E no lo hacía. La creación ahora conserva el lock cuando aplica y además recupera de forma segura el registro canónico tras un `IntegrityError` por la restricción única.

2. **Contrato G2 obsoleto.**
   `/hero` y `/adventures` seguían marcados como rutas pospuestas pese a formar parte del alcance BM-0068. El smoke de navegador fue actualizado para tratarlas como rutas aceptadas.

3. **Bonos de equipamiento aplicados a categorías incorrectas.**
   Bonos como `attack_infantry` y `defense_infantry` afectaban anteriormente a todo el ejército. El adaptador de combate ahora calcula el multiplicador por categoría (`infantry`, `cavalry`, `siege`) y deja los puntos generales como bono transversal.

4. **XP defensiva sin progresión de nivel.**
   El motor BM-0064 acreditaba XP al héroe defensor, pero podía dejarlo por encima del umbral sin subir de nivel. BM-0068 ahora normaliza esa XP con la tabla autoritativa antes de persistir el combate.

5. **Resultado de aventura persistido pero no observable por el API de lectura.**
   `AdventureRead` ahora expone `result`, permitiendo auditar que el retry devuelve exactamente el resultado persistido.

6. **Falso positivo de doble recompensa en G13.**
   Dos snapshots consecutivos de ciudad podían diferir unos milésimos por producción pasiva normal. G13 ahora compara de forma exacta héroe, inventario y aventura, y separa la deriva pasiva subunidad de un payout duplicado de aventura.

## Evidencia automatizada — Validation #506

Validation #506 se ejecutó sobre el HEAD funcional exacto `2aa3e0dcf062b235617fb04767b679dcc9ecbfad`.

| Gate | Resultado | Evidencia |
| --- | --- | --- |
| Frontend | ✅ PASS | lint y build completados |
| Backend | ✅ PASS | 257 recolectadas; 232 passed; 25 skipped intencionales para PostgreSQL; cobertura total 76% |
| PostgreSQL concurrency | ✅ PASS | 25 pruebas concurrentes/locks pasadas |
| Dependency and security audit | ✅ PASS | auditoría Python, análisis estático y auditoría frontend |
| G5 operations recovery | ✅ PASS | despliegue, backup, restore y probes de carga |
| Browser E2E | ✅ PASS | journeys aceptados G2–G13 completos |
| Container images | ✅ PASS | imágenes backend y frontend construidas con Docker Buildx |

## Base de datos y seed

El gate Backend de este mismo corte verificó:

- compilación del backend;
- migraciones desde base hasta `0011`;
- downgrade nuevamente hasta base;
- seed canónico;
- ejecución idempotente repetida del seed.

El gate PostgreSQL valida además los caminos que dependen de locks reales y que se omiten intencionalmente en la suite SQLite.

## Contratos de BM-0068 verificados

### Héroe

- un héroe por usuario y mundo;
- asociación a ciudad del mismo mundo;
- creación perezosa idempotente ante requests concurrentes;
- distribución de puntos protegida transaccionalmente;
- revive con costo autoritativo de 250 oro;
- héroe muerto o ausente no aporta bonos;
- equipamiento solo modificable en estado permitido;
- héroe asignado a una marcha queda ocupado hasta su retorno.

### Bonos vivos

- ataque y defensa por puntos respetan caps;
- objetos específicos afectan únicamente la categoría correspondiente;
- producción aplica únicamente mientras el héroe está vivo y en casa;
- velocidad se congela dentro del movimiento creado y se conserva en el retorno;
- informes de combate incluyen versión de reglas y modificadores usados.

### Aventuras

- generación y resultado auditables mediante seed SHA-256 persistido;
- resultado terminal persistido y visible en API;
- claim repetido devuelve el mismo resultado;
- retry no vuelve a entregar XP, objetos ni recursos;
- claim terminal libera al héroe del estado `adventure`;
- las recompensas respetan almacenamiento y reglas del mundo.

### Aislamiento por mundo

- consultas de héroe y aventuras requieren el mundo activo/autorizado;
- un héroe de otro mundo no puede ser asignado a la marcha de una ciudad local;
- selección del héroe defensor se resuelve por el mundo del combate y no por una preferencia global del usuario.

## Estado de cierre

El corte funcional `2aa3e0dcf062b235617fb04767b679dcc9ecbfad` está completamente verde en Validation #506.

Este documento crea un nuevo HEAD exclusivamente documental. Antes de pasar el PR #101 a **Ready for review** y fusionar, se requiere una Validation completa adicional sobre el commit que contiene este documento, para demostrar que el HEAD exacto a fusionar mantiene todos los gates verdes.
