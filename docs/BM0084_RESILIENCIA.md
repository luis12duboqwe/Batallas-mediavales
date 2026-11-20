# BM-0084 — Resiliencia de interfaz (bloque 1)

## Alcance implementado

- Las peticiones de una sesión vigente que reciben HTTP 401 invalidan el token, conservan un aviso visible en español y redirigen al inicio de sesión.
- Un 401 tardío perteneciente a un token antiguo no invalida un inicio de sesión nuevo; los rechazos normales de credenciales no expulsan al jugador.
- El login no conserva el token si falla la carga del perfil posterior a la autenticación.
- El indicador global distingue desconexión del navegador, reconexión Socket.IO y fallos temporales 502/503/504; conserva todos los endpoints fallidos y solo anuncia recuperación cuando cada ruta afectada vuelve a responder correctamente.
- Las respuestas tardías de carga de perfil o ciudad no sobrescriben ni expulsan una sesión posterior.
- Las funciones de operación del juego y sus contratos HTTP no cambian; tampoco se activan servicios externos.

## Pruebas

- `npm run test:resilience`: rutas de autenticación pública, errores HTTP, token actual/obsoleto, carreras de estado y motivos temporales.
- `node e2e/g24-resilience.mjs`: desconexión, recuperación, mantenimiento, recarga con JWT inválido y sesión expirada en español.
- Frontend lint/build, backend, concurrencia, G21–G24, navegador, auditoría y Docker obligatorios antes de fusionar.

## Bloque 2: estados de carga, vacío, error y reintento

- Mapa: cada nueva zona descarta respuestas retrasadas de zonas anteriores; los errores se distinguen de un mapa sin casillas, con reintento manual.
- Mensajería: cambio de carpeta y reintento cancelan lógicamente peticiones anteriores; la carpeta vacía solo se muestra si la solicitud tuvo éxito.
- Reportes: estado de carga, error recuperable y vacío real separados; no quedan esqueletos de carga permanentes.
- G25 fuerza respuestas 503, recuperaciones y vacíos de las tres pantallas a través de Playwright.

## Siguiente bloque de BM-0084

Completar estados vacíos, fallos recuperables y casos adversariales por pantalla (mapa, mensajes, reportes, recursos) antes de certificar toda la fase.
