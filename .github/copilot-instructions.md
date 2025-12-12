# Batallas Medievales — AI Coding Agent Instructions
## Copilot / CodeGen Development Guide

**Versión completa ✓**

### 🏰 1. Project Overview

**Batallas Medievales** es un juego de estrategia medieval tipo navegador (similar a Travian / Medievol).
El proyecto es un monorepo con:

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL
- **Frontend**: React 18 + Vite + Tailwind + Zustand
- **Infraestructura**: Docker Compose + Nginx

Copilot debe respetar esta arquitectura.

### 🏗️ 2. Architecture & Tech Stack

#### Backend (`batalla_medieval_backend/`)

- **Framework**: FastAPI
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy
- **Schemas**: Pydantic
- **Auth**: JWT
- **Tests**: Pytest

**Carpetas principales**
- `app/main.py`                → entrypoint del backend  
- `app/routers/`               → controladores (API)  
- `app/models/`                → modelos SQLAlchemy  
- `app/schemas/`               → DTOs Pydantic  
- `app/services/`              → lógica del juego  
- `app/middleware/`            → middlewares personalizados  

#### Frontend (`batalla_medieval_frontend/`)

- **React + Vite**
- **Tailwind CSS**
- **Zustand** para estado global
- **Axios** como cliente HTTP

**Carpetas principales**
- `src/api/axiosClient.js`     → cliente axios con interceptores  
- `src/store/`                 → global stores (auth, city, game, UI)  
- `src/components/`            → UI reusable  
- `src/pages/`                 → vistas del juego  

### 🛡️ 3. Game Mechanics (Resumen para Copilot)

Copilot debe usar estas reglas al generar lógica nueva.

**Cities**
- Producen recursos (madera, barro, hierro) por hora.
- Buildings afectan:
    - producción
    - almacenamiento
    - defensa
    - velocidad de reclutamiento
- Tienen colas de:
    - Construcción
    - Tropas

**Resources**
- Cada recurso aumenta basado en una fórmula dependiente del nivel del edificio.

**Troops**
- Cada tropa tiene:
    - `attack`
    - `defense_infantry`
    - `defense_cavalry`
    - `speed`
    - `carry_capacity`

**Movements**
- Tipos:
    - `attack`
    - `spy`
    - `reinforce`
    - `return`
- Todos tienen:
    - `ciudad_origen`
    - `ciudad_destino`
    - `tropas`
    - `arrival_time = now + travel_time`

**Combat System**
1. Sumar ataque del atacante
2. Sumar defensa del defensor
3. Aplicar bonus de muralla
4. Aplicar moral
5. Aplicar “suerte”
6. Calcular bajas proporcionales
7. Generar informe

**Conquest Rules**
- **PvP Conquest Restricted**: La conquista de ciudades de otros jugadores está **estrictamente prohibida** por diseño. Solo se permite conquistar ciudades bárbaras (owner_id=None). No sugerir ni implementar cambios para permitir PvP conquest.

**Espionage**
- Comparar espías atacante vs defensor
- Si falla → el defensor descubre al atacante

### 🌍 4. Multi-World Rules

**Copilot debe SIEMPRE respetar multi-mundos.**

- Todos los objetos jugables incluyen: `world_id`
- Las queries deben filtrar por `world_id`
- Nunca crear ciudades/tropas sin asignar mundo

### 🧩 5. Backend Architecture Rules
Copilot debería seguir SIEMPRE este flujo:
`Model` → `Schema` → `Service` → `Router` → `Frontend API` → `UI Component`

**Responsibilities**

- **Routers**
    - NO contienen lógica del juego
    - Solo:
        - validación
        - llamadas a servicios
        - HTTP responses

- **Services**
    - Contienen TODA la lógica
    - NO deben lanzar HTTPException (eso va en routers)

- **Models**
    - Estructura de BD solamente
    - Sin lógica

- **Schemas**
    - Solo DTOs
    - Nada de lógica

- **Middleware**
    - Se usa para:
        - idioma
        - autenticación extendida
        - logging
        - rate limiting (si se agrega)

### 🔐 6. Authentication Rules

- **JWT obligatorio**
- Token se almacena como `bm_token`
- Axios interceptor inserta “Authorization: Bearer X”
- Backend valida con: `Depends(get_current_user)`

**Copilot NO debe modificar el sistema JWT sin instrucciones.**

### 🎨 7. Frontend Rules & Patterns

**Naming**
- Componentes: `PascalCase`
- Stores Zustand: `camelCase` + Store (`authStore`, `cityStore`)
- APIs: `camelCase` (`getCity`, `upgradeBuilding`)

**Axios usage**
- Siempre:
  ```javascript
  import { api } from '../api/axiosClient';
  ```
- Nunca usar `fetch` directamente salvo que se solicite.

**Global State**
- Siempre usar **Zustand**
- Nunca use Context API para lógica de juego

### 🚫 8. Copilot NO debe hacer esto

**Muy importante:**

❌ No inventar rutas nuevas
❌ No cambiar nombres de modelos
❌ No crear endpoints sin revisar routers existentes
❌ No duplicar lógica en varios services
❌ No agregar dependencias externas sin permiso
❌ No romper consistencia de multiworld
❌ No mover carpetas ni archivos sin permiso

### 📘 9. Coding Conventions

**Python**
- `snake_case` para funciones y archivos
- `PascalCase` para modelos
- Variables de sesión BD siempre: `db`

**React**
- JSX limpio
- No lógica de negocios en componentes
- Estado global solo con Zustand
- Evitar `useEffect` innecesario

### 🧪 10. Testing Rules

- Todo endpoint nuevo requiere un test en `tests/`
- Patrón obligatorio:
  `Arrange` → `Act` → `Assert`
- Usar `TestClient` de FastAPI

### 🚚 11. Deployment Rules

Copilot debe asumir que la app usa:
- Docker / Docker Compose
- Nginx reverse proxy
- Backend en `:8000`
- Frontend en `:5173`
- `/api`  → backend  
- `/`     → frontend  

### 🤖 12. Copilot Behavior Rules

Copilot debe actuar como un desarrollador senior:

- Buscar patrones existentes ANTES de generar código
- Reutilizar lógica ya escrita
- Mantener arquitectura limpia
- Seguir SOLID
- Escribir documentación breve en código
- Minimizar cambios a lo estrictamente necesario

### 📝 13. Example Task Flow for Copilot

Si el usuario pide “agregar sistema de misiones”:

1. Ver si existe `/models/quest.py`
2. Ver si hay servicio en `/services/quest.py`
3. Ver si router existe
4. Extender cada capa sin romper el patrón
5. Agregar endpoint
6. Agregar API en frontend
7. Agregar UI
8. Agregar test
