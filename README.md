# Batallas Medievales

Juego de estrategia medieval multijugador para navegador, inspirado en los juegos de construcción de ciudades, gestión de recursos, alianzas y guerra persistente.

> **Estado actual: prototipo en estabilización.** El repositorio contiene una cantidad amplia de sistemas, pero la rama `main` todavía no representa una versión ejecutable ni apta para producción. La prioridad vigente es recuperar una base verificable antes de añadir funciones.

## Fuente de verdad

El documento rector del proyecto es el [Plan Maestro de Desarrollo](docs/PLAN_MAESTRO_DESARROLLO.md). Define el alcance del MVP, prioridades, fases, criterios de aceptación, riesgos y la definición de terminado.

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

## Flujo de trabajo

1. Seleccionar una tarea del backlog del plan maestro.
2. Trabajar en una rama corta y enfocada.
3. Añadir o actualizar pruebas junto con el cambio.
4. Abrir un PR en borrador con evidencia reproducible.
5. Fusionar únicamente cuando todos los controles obligatorios estén en verde.

No debe anunciarse una versión jugable hasta cumplir el hito **G5 — Beta cerrada publicable** definido en el plan maestro.
