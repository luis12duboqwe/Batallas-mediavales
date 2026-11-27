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
  frontend y worker vinculadas a ese SHA, cada una por digest inmutable e ID.
- Inventario tipado de contenedores, Compose, red, volumen, DB OID, huella de
  esquema, roles y Caddy/TLS; dos observaciones de identidad para detectar
  cambios durante la recopilación.
- Estado del marcador/manifiesto. Un host sin metadata administrada, un
  incidente, una fase no terminal o cualquier contradicción es bloqueador; no
  se considera una primera instalación aunque ya contenga datos.
- Declaraciones externas separadas de observaciones: ID/hash/OID de la copia
  externa, ID del clon y hash de origen restaurado, capacidad, ventana y
  autorización humana. El plan comprueba consistencia entre los valores
  declarados, pero no autentica ni verifica las pruebas subyacentes.

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

1. Acordar alcance, autorización y ventana aprobada.
2. Fijar checkout limpio e imágenes por digest e ID.
3. Reconfirmar identidad administrada completa, sin cambio de DB, red, volumen
   o esquema.
4. Aprovisionar o certificar un rol de aplicación no privilegiado y probar
   privilegios permitidos y denegados.
5. Cerrar HTTP/Socket.IO, desactivar reinicios de writers, detenerlos y
   establecer una barrera durable contra escrituras y reconexiones.
6. Con la barrera bajo control, preservar de forma durable la identidad de la
   release previa y su recuperación.
7. Capturar/verificar la copia externa con barrera e identidad continuas.
8. Restaurar esa copia solo en un clon aislado y verificar esquema y datos.
9. Publicar la release aprobada e inmutable únicamente después de preservar la
   release previa y su evidencia.
10. Probar HTTPS público, entrega SMTP y carga acotada; ante incertidumbre,
    mantener cerrada la admisión.

El orden es una lista para diseño futuro, no prueba de prerrequisitos ni una
autorización para ejecutarlos. Una futura integración debe demostrar
observaciones frescas y continuidad bajo un lock y barrera durables; verificar
el rol real mediante pruebas SQL negativas/positivas; excluir writers fuera de
Compose, tareas programadas y conexiones externas; conservar estado en
almacenamiento independiente de la DB/volumen; y validar copia, permisos,
capacidad, edge, restore clonado y probes antes de cualquier publicación.

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
