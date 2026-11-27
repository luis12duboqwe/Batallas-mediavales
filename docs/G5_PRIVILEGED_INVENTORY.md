# G5 — inventario PostgreSQL de escritores privilegiados (#174)

**NO-GO.** Observación de solo lectura para un clúster dedicado, no una
barrera, una autorización de despliegue o una prueba de exclusión continua.

`inspect_privileged_inventory` exige sesiones frescas de solo lectura y
devuelve bloqueadores, no permisos. Revisa PG15 y la identidad de
mantenimiento, base objetivo, bases ajenas, roles adicionales incluso
NOLOGIN, membresías de roles, atributos del rol app, sesiones cliente,
transacciones preparadas, slots, suscripciones y tipos de backend
inesperados. Rechaza bibliotecas preload y overrides; en la base objetivo
rechaza extensiones fuera de plpgsql, tablas extranjeras, event triggers y
funciones SECURITY DEFINER no estándar. Reobserva el clúster después
de cerrar la conexión temporal de mantenimiento. Ante evidencia ambigua,
no devuelve una observación positiva.

La política es intencionalmente conservadora: si hay bases, roles o
extensiones compartidas, requiere un diseño explícito diferente. No elimina
roles, permisos ni sesiones, no cambia SQL y no se integra en una ruta
de producción. La consulta de catálogo puede detectar ciertas vías
privilegiadas, pero **no** controla administradores Docker/root, otros
poseedores de credenciales, archivos HBA/config, acceso al volumen, procesos
externos, reinicio del host o cambios entre consultas. La exclusividad
externa continua sigue siendo requisito independiente. No se certifica
RPO=0 ni se cierra #174 por esta observación.

CI ejecuta un PostgreSQL 15 sin red ni puertos, credenciales sintéticas,
pruebas de roles adicionales, membresía, DB ajena, slot, función privilegiada,
transacción preparada, override de preload y sesión admin ajena, antes y
después del fence persistente. Se preservan las demás compuertas G5.
`tests/test_g5_pg15_privileged_inventory.py` cubre respuestas ambiguas,
todas las categorías y deriva entre observaciones. Certificación pendiente
del HEAD exacto.
