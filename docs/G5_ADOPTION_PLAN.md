# Plan de adopción administrada G5

**Estado: NO-GO para #174 y #161.** `ops/g5_adoption_plan.py` es únicamente un
contrato puro para planificar la posible adopción futura de un host poblado.
No inspecciona el host, no es un adaptador de producción y no autoriza ni
ejecuta despliegues. Un plan sin bloqueadores sigue teniendo el estado
`NO_GO_PLAN_ONLY`; no existe un resultado GO.

## Alcance

La implementación está limitada a este documento, `ops/g5_adoption_plan.py`
y `tests/test_g5_adoption_plan_planner.py`. No cambia Compose, workflows,
scripts legacy, rollback, restore ni lifecycle; no incorpora comandos, rutas
operativas, Docker, SQL, acceso a SSH/VPS, registry privado ni SMTP real.
No registra ni publica metadata y no habilita legacy ni producción.

La función `plan_adoption(observations, declarations, now=...)` recibe:

- Evidencia de checkout completo por SHA y worktree limpio; imágenes backend,
  frontend y worker vinculadas a ese SHA, cada una por digest e ID
  inmutables. Backend y worker deben compartir exactamente la imagen backend.
- Dos inventarios completos e independientemente recogidos (checkout, imágenes,
  contenedores, edge y metadata) que deben coincidir. Los IDs de contenedor y
  red deben ser completos, el nombre de proyecto/volumen validable y todos los
  writers one-shot `migrate`/`seed` observados deben estar detenidos con
  `restart=no`.
- El edge real de Compose: Caddy debe dirigirse al contenedor Nginx observado;
  Nginx debe dirigir `/api/` y `/socket.io/` a los contenedores backend
  observados y `/` al frontend observado. Rutas adicionales, faltantes o con
  destino alternativo se bloquean.
- Variantes explícitas de estado: metadata ausente sin artefactos, host legacy
  sin gestión, metadata legacy administrada, recibo G5 administrado e
  incidente. Metadata ausente con marcador/manifiesto/recuperación es
  contradictoria. La metadata legacy no equivale a un recibo G5 terminal.
- Declaraciones externas separadas de observaciones: copia enlazada a OID,
  huella de esquema y release fuente; restauración en clon enlazada al mismo
  hash, esquema y OID, con red y volumen distintos; mediciones frescas de
  capacidad, ventana y autorización humana. Son declaraciones no verificadas;
  el plan comprueba consistencia y frescura, pero no autentica pruebas.

La validación de imágenes reutiliza `preflight.validate_image`. El contrato de
roles reutiliza `validate_split` únicamente con credenciales sintéticas para
revisar los nombres y la separación estática. No recibe, conserva, muestra ni
certifica contraseñas reales, configuración efectiva de conexión, privilegios
PostgreSQL ni barreras vivas. La identidad y fase del manifiesto se comprueban
con `Identity`, `Manifest` y `Phase` existentes; no se define otro formato de
estado G5.

## Secuencia propuesta, no ejecutable

Los pasos que retorna el planner son condicionales y requieren un adaptador
posterior auditado y autorización humana explícita:

1. Acordar alcance, autorización humana y ventana aprobada.
2. Fijar checkout limpio e imágenes backend/frontend/worker por digest e ID.
3. Confirmar la topología real Caddy → Nginx → backend/frontend, incluyendo
   API y Socket.IO, sin rutas de bypass.
4. Aprovisionar o certificar un rol de aplicación no privilegiado y probar
   privilegios permitidos y denegados.
5. Cerrar HTTP/Socket.IO, desactivar reinicios de writers, detenerlos y
   establecer una barrera durable contra escrituras y reconexiones.
6. Capturar y verificar la copia externa con barrera e identidad continuas.
7. Restaurarla solo en un clon con red y volumen distintos, y verificar OID,
   esquema y datos.
8. Solo después de validar evidencia durable de rollback, registrar la
   identidad de la release previa.
9. Publicar la candidata inmutable bajo admisión controlada y verificar su
   salud antes de cualquier probe público.
10. Solo con autorización separada y admisión controlada, probar HTTPS,
    entrega SMTP y carga acotada; la adopción no constituye activación.

Este bootstrap de identidad de release para un host legacy es separado del
cutover G5 protegido y de sus fases/recibos terminales. El plan no escribe
metadata: primero se verifica copia y restore de rollback y solo después un
adaptador futuro podría registrar la identidad previa. Nunca convertir
metadata ausente o legacy en un recibo G5 fingido.

El orden es una lista para diseño futuro, no prueba de prerrequisitos ni una
autorización para ejecutarlos. Una futura integración debe demostrar
observaciones frescas e independientes bajo continuidad de identidad, verificar
el rol real mediante pruebas SQL negativas/positivas, excluir writers fuera de
Compose, tareas programadas y conexiones externas, conservar estado en
almacenamiento independiente de la DB/volumen y mantener admisión controlada
hasta verificar la candidata. Los probes públicos no preceden a esa
verificación.

## Límites de confianza

La igualdad de dos identidades observadas detecta discrepancias aportadas al
planner, pero no autentica al observador ni impide cambios posteriores. Las
declaraciones de copia, clon, capacidad, ventana y autorización no son
atestiguadas por esta función. La autorización humana no puede ser sustituida
por un estado sin bloqueadores.

Root, el daemon/administrador Docker, el host, el kernel, PostgreSQL superuser,
un writer fuera del inventario y los proveedores de backup/edge están fuera de
la exclusión del contrato. Una futura implementación debe definir controles
auditables para esos actores y no tratar el inventario puntual como una
barrera. No registrar evidencia en disco ni emitir secretos o URLs de conexión.

Las pruebas son sintéticas y no acceden a sistemas externos. #174 y #161
continúan explícitamente NO-GO; el estado sin metadata de release administrada
de la vista previa histórica es un bloqueador, no una invitación a inicializar
metadata sobre un host poblado.
