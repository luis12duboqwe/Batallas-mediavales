# BM-0090 — Cobertura de exportación de datos del jugador

La API de descarga de cuenta usa exclusivamente las columnas de titularidad
del usuario autenticado. Esta ampliación añade, sin modificar el esquema
existente ni la autenticación:

- Membresías, invitaciones enviadas y recibidas, y mensajes escritos en alianzas.
- Marcadores del mapa, preferencias premium y temas obtenidos.
- Resultados de temporada propios y bloqueos creados por el usuario.

No se exportan los bloqueos creados por otros jugadores contra el titular,
los mensajes de alianza escritos por terceros, ni las preferencias de otras
cuentas. La exportación conserva el campo schema_version=1 porque incorpora
solo claves nuevas opcionales (compatibilidad aditiva); las claves
anteriormente publicadas no se alteran.

**Fuera del alcance de esta ampliación:** movimientos cuyo origen pudo
cambiar de propietario; informes de combate/espionaje que exponen datos
compartidos; evidencias internas de moderación; logs de infraestructura;
datos de servicios externos y las decisiones jurídicas sobre retención.
Requieren un diseño de autorización histórico y política de privacidad
aprobada, no filtros por propietario actual de la ciudad.

Las pruebas validan datos positivos, negativos, cuenta sin registros y
aislamiento con dos cuentas, incluso cuando comparten alianza, mundo, tema
y temporada. No se ejecuta ninguna eliminación ni cambio de cuenta.
