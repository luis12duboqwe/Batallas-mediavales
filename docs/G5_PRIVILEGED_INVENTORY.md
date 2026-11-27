# G5 — inventario PostgreSQL de escritores privilegiados (#174)

**NO-GO.** Observación de solo lectura para un clúster dedicado, no una
barrera, una autorización de despliegue o una prueba de exclusión continua.

`inspect_privileged_inventory` exige sesiones frescas de solo lectura y
devuelve bloqueadores, no permisos. Revisa PG15 y la identidad de
mantenimiento, base objetivo, bases ajenas, roles adicionales incluso
NOLOGIN, membresías de roles, atributos del rol app, sesiones cliente,
transacciones preparadas, slots, suscripciones y tipos de backend
inesperados. Rechaza bibliotecas preload y overrides; en la base objetivo y postgres
rechaza extensiones fuera de plpgsql, tablas extranjeras, event triggers y
funciones SECURITY DEFINER no estándar y rutinas nativas/no confiables
ajenas al catálogo estándar. Rechaza CONNECT efectivo del rol app a otras
bases y privilegios efectivos (incluido PUBLIC y columnas) en funciones
sensibles de archivos y catálogos de credenciales/suscripciones. La lista
sensible es deliberadamente explícita, no una auditoría universal de ACL. Reobserva el clúster después
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

Revisión P2: las tres categorías de Codex se cubren con casos de grants directos y PUBLIC, ACL de columna, rutina nativa inocua y rutina privilegiada en postgres, además de CONNECT a postgres/template1. Pendiente nueva CI y revisión.

Segunda revisión: el ensayo inicial falló por ACL estándar de PG15. Se diferencia el acceso inicial de initdb (`pg_init_privs`, o ACL por defecto) de grants efectivos nuevos sobre funciones incorporadas; se inspeccionan columnas confidenciales concretas y privilegios de modificación en catálogos. Se rechazan además grants explícitos SET/ALTER SYSTEM en `pg_parameter_acl`, incluso PUBLIC, sin depender del valor vigente. Política limitada a instalación PostgreSQL confiable y al alcance documentado, no una auditoría de toda capacidad privilegiada. Nuevos casos de regresión con parámetros sin alterar sus valores. CI pendiente.

Tercera revisión: CI 46021949133 confirmó falso positivo de catálogo en instalación estándar. Se exceptúa exclusivamente UPDATE estándar de la vista pg_settings (OID incorporado y relkind=v); la vista aplica set_config con permisos. INSERT/DELETE/TRUNCATE/TRIGGER y UPDATE en otras relaciones siguen bloqueados, además de grants UPDATE explícitos adicionales en pg_settings. El fixture verifica el permiso stock y prueba grants adicionales de tabla y columna. CI pendiente.

Se cubre también UPDATE explícito por columna en pg_settings y el caso de base ajena que genera simultáneamente dos bloqueadores (topología y CONNECT). El ensayo exige ambos, no oculta hallazgos adicionales.

CI 46032871751 superó la comprobación positiva inicial y falló un caso adversarial sin identificar su nombre en el log. Se amplía la detección explícita de lo_import/lo_export y ownership de funciones incorporadas, independiente de pg_init_privs. El runner identifica cada escenario, recoge todos los fallos de aserción independientes, revierte cada fixture y exige volver a baseline después de cada caso. Los casos fallidos siguen bloqueando CI; no se relajan expectativas. Pendiente nuevo resultado real.
