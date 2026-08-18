# Batallas Medievales

Juego de estrategia medieval multijugador para navegador, inspirado en los juegos de construcción de ciudades, gestión de recursos, alianzas y guerra persistente.

> **Estado actual: prototipo en estabilización.** El objetivo aprobado es llevarlo hasta **Batallas Medievales v1.0 completo**, no detenerse en una beta. La rama `main` todavía no representa una versión ejecutable ni apta para producción; la prioridad vigente es recuperar una base verificable antes de añadir funciones.

## Fuente de verdad

El documento rector del proyecto es el [Plan Maestro de Desarrollo](docs/PLAN_MAESTRO_DESARROLLO.md). Define el MVP intermedio, el alcance completo de v1.0, prioridades, fases G0–G10, criterios de aceptación, riesgos y la definición verificable de terminado.

En caso de conflicto, se aplica este orden:

1. `docs/PLAN_MAESTRO_DESARROLLO.md`
2. `.github/copilot-instructions.md`
3. Código y pruebas aprobados en `main`

## Arquitectura prevista

- Backend: FastAPI, SQLAlchemy y PostgreSQL.
- Frontend: React 18, Vite, Tailwind y Zustand.
- Tiempo real: Socket.IO autenticado.
- Infraestructura: Docker Compose y Nginx.
- Pruebas: Pytest para backend y una suite de frontend/E2E que debe incorporarse durante la estabilización.

## Reglas de producto no negociables

- El servidor es la única autoridad sobre recursos, tiempos, movimientos y resultados de combate.
- Todo dato jugable debe pertenecer a un `world_id`; no se permiten operaciones entre mundos.
- Los jugadores pueden atacarse, espiar y saquearse si las reglas de protección lo permiten.
- No se pueden conquistar ciudades de otros jugadores. Solo se pueden conquistar ciudades bárbaras sin propietario.
- Las funciones premium del MVP no pueden otorgar una ventaja directa de combate o economía.

## Estructura

```text
batalla_medieval_backend/   API, modelos, servicios y procesos del juego
batalla_medieval_frontend/  Aplicación web React
tests/                      Pruebas automatizadas de backend
docs/                       Planificación y decisiones del proyecto
.github/                    Instrucciones de agentes y automatización
```

## Arranque reproducible

La vía preferida es Docker Compose. Una vez creado `.env` a partir de `.env.example` con credenciales válidas:

```bash
docker compose up --build
```

El orden de arranque es parte del contrato operativo:

1. PostgreSQL queda saludable.
2. `migrate` ejecuta `alembic upgrade head`.
3. `seed` ejecuta `python -m app.seed` y crea solo los datos canónicos que falten.
4. `backend` sirve HTTP + Socket.IO.
5. `worker` procesa los trabajos periódicos fuera del proceso web.
6. Nginx publica frontend, API y WebSocket.

Para trabajar manualmente con el backend desde `batalla_medieval_backend/` se respeta el mismo orden:

```bash
alembic -c alembic.ini upgrade head
python -m app.seed
uvicorn app.main:socket_app --host 0.0.0.0 --port 8000
```

El worker se inicia en un proceso separado:

```bash
python -m app.worker
```

El seed es idempotente: volver a ejecutarlo no repone recursos, edificios ni tropas de aldeas bárbaras que ya tengan progreso.

## Flujo de trabajo

1. Seleccionar una tarea del backlog del plan maestro.
2. Trabajar en una rama corta y enfocada.
3. Añadir o actualizar pruebas junto con el cambio.
4. Abrir un PR en borrador con evidencia reproducible.
5. Fusionar únicamente cuando todos los controles obligatorios estén en verde.

G5 autoriza únicamente una **beta cerrada**. El juego solo puede anunciarse como terminado al aprobar **G10 — Batallas Medievales v1.0 terminado al 100 %** contra un commit y despliegue exactos.
