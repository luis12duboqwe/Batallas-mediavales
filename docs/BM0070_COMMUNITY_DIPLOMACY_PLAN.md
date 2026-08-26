# BM-0070 — Plan de cierre: comunidad y diplomacia completas

Fecha de inicio: 2026-08-26  
Rama: `feature/BM-0070-community-diplomacy-final`  
Base: `main` posterior a BM-0068 (`653770133a313d4a6636f44d6746973949570e1b`)

## Objetivo

Cerrar el paquete social obligatorio de Fase 7 para que alianzas, rangos, invitaciones, diplomacia, chat, mensajería y foro funcionen con permisos explícitos, privacidad, moderación, aislamiento por mundo y pruebas E2E.

BM-0070 no debe crear un segundo sistema social paralelo. El trabajo consiste en consolidar lo existente, eliminar contratos contradictorios y dejar una única superficie final.

## Estado encontrado en `main`

La base ya contiene:

- modelos y API de alianzas;
- membresía por mundo y rangos `Member`, `General` y `Leader`;
- creación, invitación, aceptación, salida, promoción, degradación y expulsión;
- chat de alianza persistido dentro del servicio de alianzas;
- chat WebSocket con canales `global`, `world`, `alliance` y `private`;
- historial de chat filtrado por mundo;
- diplomacia `nap`, `ally` y `war` con solicitudes y aceptación;
- foro de alianza con hilos y respuestas;
- mensajería masiva desde rangos altos;
- UI existente de alianza, diplomacia y foro.

## Riesgos y brechas detectadas

### 1. Permisos incompletos o demasiado implícitos

Algunas rutas confían en `require_membership()` sin un contrato central de capacidades. BM-0070 debe definir permisos nominales por rango para invitar, administrar miembros, editar alianza, diplomacia, moderar chat/foro y mensajería masiva.

Los permisos no deben depender de comparaciones numéricas dispersas por routers y servicios.

### 2. Gestión de liderazgo incompleta

El líder no puede abandonar una alianza con miembros, pero falta un flujo explícito y auditable de transferencia de liderazgo. BM-0070 debe incorporar transferencia atómica y garantizar que una alianza con miembros tenga exactamente un líder válido.

### 3. Concurrencia en membresías y administración

Invitaciones, aceptación, promoción, degradación, expulsión y transferencia deben ser resistentes a acciones simultáneas. Deben existir constraints/locks suficientes para impedir:

- doble membresía en el mismo mundo;
- dos líderes simultáneos por una carrera;
- aceptar dos invitaciones de alianzas distintas en paralelo;
- administrar un miembro usando estado obsoleto.

### 4. Diplomacia sin contrato final de ciclo de estado

El servicio actual conserva dirección de solicitudes y separa `pending_nap`, `pending_ally` y `war`, pero BM-0070 debe cerrar:

- matriz de transiciones válidas;
- declaración unilateral de guerra;
- aceptación exclusiva por alianza objetivo para NAP/alianza;
- cancelación/ruptura por cualquiera de las partes según el tipo;
- idempotencia y concurrencia;
- aislamiento por mundo en todos los accesos;
- metadatos de actor/tiempo necesarios para auditoría.

### 5. Dos superficies de chat que pueden divergir

Existe chat de alianza mediante endpoints HTTP de `alliance` y chat WebSocket persistido en `ChatMessage`. BM-0070 debe decidir una única fuente de verdad para mensajes en tiempo real e historial, manteniendo compatibilidad solo donde sea necesaria.

No se debe conservar silenciosamente dos historiales de alianza incompatibles.

### 6. Privacidad y bloqueo

El chat privado valida mundo compartido, pero BM-0070 requiere un contrato final para bloqueo/privacidad. Un usuario bloqueado no debe poder enviar mensajes privados, invitaciones o interacciones sociales que el contrato prohíba.

La lectura de historial privado debe requerir que el solicitante sea una de las dos partes.

### 7. Moderación y antiabuso social

El `chat_manager` ya aplica filtro y rate limit en WebSocket, pero el mismo nivel de protección debe existir para cualquier vía persistente equivalente. BM-0070 debe cubrir:

- límites de tamaño;
- contenido vacío/solo espacios;
- rate limiting razonable;
- permisos de moderación;
- borrado/ocultamiento auditable cuando corresponda;
- prohibición de acciones administrativas irreversibles automáticas.

### 8. Foro de alianza mínimo

El foro actual comprueba membresía para leer/crear/reply, pero necesita cerrar:

- aislamiento por mundo derivado de la alianza;
- permisos de moderación;
- hilos bloqueados/cerrados;
- límites de contenido;
- orden/paginación;
- eliminación o edición con política explícita y auditada;
- pruebas de expulsión: un exmiembro no puede seguir leyendo contenido privado.

### 9. UI y E2E

BM-0070 requiere una superficie final coherente de comunidad. Como mínimo el journey E2E debe demostrar con dos o más jugadores:

1. crear alianza;
2. invitar y aceptar;
3. gestionar rango;
4. enviar/recibir chat de alianza;
5. enviar/recibir mensaje privado respetando privacidad;
6. crear y responder foro;
7. solicitar y aceptar diplomacia con una segunda alianza;
8. probar una acción denegada por rango;
9. probar aislamiento entre mundos;
10. probar salida/expulsión y pérdida inmediata de acceso privado.

## Contratos finales propuestos

### Rangos y capacidades

Definir capacidades servidor-autoritativas, como mínimo:

- `alliance.invite`
- `alliance.manage_members`
- `alliance.transfer_leadership`
- `alliance.edit`
- `alliance.diplomacy`
- `alliance.mass_message`
- `alliance.moderate_chat`
- `alliance.moderate_forum`

`Leader` posee todas. `General` recibe únicamente las aprobadas explícitamente. `Member` conserva lectura/participación social ordinaria.

### Aislamiento

Toda operación social debe quedar vinculada a `world_id` directa o transitivamente a través de una alianza verificada. No se aceptan relaciones diplomáticas, invitaciones, chat privado o lectura de foro entre mundos.

### Atomicidad

Cambios de membresía, liderazgo y diplomacia se resuelven dentro de una transacción. Los reintentos no deben crear membresías, relaciones o mensajes duplicados cuando exista una clave idempotente aplicable.

### Privacidad

Los canales privados solo son visibles a sus participantes. El foro y chat de alianza solo son visibles a miembros actuales de esa alianza y mundo.

## Orden de implementación

1. Consolidar modelo de permisos por rango y tests de autorización.
2. Cerrar constraints/locks de membresía y transferencia de liderazgo.
3. Versionar/cerrar máquina de estados de diplomacia.
4. Consolidar chat de alianza con la fuente de verdad de `ChatMessage` y tiempo real autenticado.
5. Añadir privacidad/bloqueo y límites antiabuso comunes.
6. Cerrar foro con moderación y membresía actual.
7. Ajustar API/UI para consumir únicamente los contratos finales.
8. Añadir Browser E2E G14 para comunidad/diplomacia.
9. Ejecutar validación SQLite + PostgreSQL concurrente + Browser G2–G14 + imágenes.
10. Documentar `BM0070_COMMUNITY_DIPLOMACY_VALIDATION.md` y fusionar solo con el HEAD exacto completamente verde.

## Criterio de terminado

BM-0070 está terminado únicamente cuando:

- no hay dos sistemas sociales visibles con reglas contradictorias;
- permisos y privacidad tienen pruebas negativas;
- relaciones y membresías resisten concurrencia PostgreSQL;
- chat, mensajes y foro quedan aislados por mundo y membresía actual;
- un E2E multijugador cubre el flujo completo;
- todos los gates obligatorios están verdes sobre el HEAD exacto;
- existe evidencia final reproducible en el repositorio.
