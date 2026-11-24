# G5 — Cierre durable de admisión Nginx (#174)

**NO-GO; sin activación del overlay ni cambios en VPS.**

El componente EdgeAdmission cierra únicamente una compuerta G5 ya
instalada y verifica un Nginx concreto. Valida proyecto, ID completo,
estado, montajes bind de solo lectura y dispositivo/inodo real de
configuración y directorio. El directorio privado de estado debe ser
0700; el subdirectorio edge-maintenance, 0755 para los workers Nginx.
Elimina exclusivamente el directorio vacío open mediante rmdir relativo
al descriptor, sincroniza el directorio y conserva el cierre ante un
fallo. Rechaza rutas reemplazadas, enlaces, archivos inesperados, montajes
anidados, respuestas ambiguas o redirecciones. Comprueba HTTP 503
directo para API, rutas sin slash, polling y solicitud de upgrade.

No instala ni cambia la configuración del proxy, no recrea contenedores,
no vuelve a abrir la admisión. El coordinador debe mantener el lock
G5 y controlar el acceso administrativo al host y Docker. La verificación
de rutas no es prueba de que otro proxy o acceso directo esté cerrado.

## Rehearsal aislado

CI usa la configuración nginx.g5.conf real, Nginx 1.28 y un backend
sintético con HTTP y WebSocket; red Docker interna sin puertos publicados
ni credenciales. Demuestra HTTP abierto, una conexión WebSocket con 101,
cierre durable de nuevas solicitudes (503), que la conexión antigua aún
responde a ping, y que se desconecta al detener el backend. Recomprueba
503 después. El fixture no ejecuta Socket.IO del juego, ni demuestra
drain de transacciones reales; todavía hace falta integrar la barrera
PostgreSQL, el cierre Docker y el coordinador con todos los servicios.

Pruebas de regresión: marcadores inseguros, montajes ajenos, deriva de
inodo, fallos de transporte, 429/502, redirecciones y reapertura.
