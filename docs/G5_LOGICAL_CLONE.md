# G5 — restauración lógica en clúster independiente

**NO-GO para #174 y #161.** Ensayo CI-only, no adaptador de producción. Complementa el restore de esquema en la misma base de #206. Reusa el fixture PG15 y el recibo de snapshot verificado, no acepta endpoints, archivos de credenciales, nombres de DB ni imágenes externas aportados por el usuario.

1. Establece una base histórica 0019 poblada con una escritura de aplicación confirmada y una sesión activa, utilizando la imagen backend del checkout CI exacto.
2. Cierra la barrera persistente; comprueba la identidad del clúster (system_identifier, OID, contenedor, red interna, volumen), captura el dump custom y verifica el FD/hash, filas y secuencias.
3. Inicializa dos clústeres PG15 independientes en redes y volúmenes distintos (testigo y clon), ambos con aplicación bloqueada. Restaura el mismo archivo en bases vacías con pg_restore en una sola transacción, sin --create, --clean, ni reemplazo de base.
4. Compara todas las filas, secuencias, propiedades de DB y namespace contra la fuente; compara el catálogo completo restaurado con el testigo independiente. Comprueba identidad y fence antes/después y ausencia de deriva en la fuente. Conserva incertidumbre ante fallos; limpia recursos de fixture tras éxito.

El catálogo de 0019 puede deparsear distinto tras recargar (índice parcial, ya observado en #206). Se registran hashes de catálogo fuente y restaurado por separado, nunca se fabrican hashes iguales. La igualdad del testigo y clon no sustituye una auditoría de equivalencia semántica de DDL fuente/restaurada; la evidencia de fuente y archivo permanece separada. Se comparan las filas y secuencias sin depender de OIDs idénticos entre clústeres. No se certifica backup externo: ambos clústeres y archivo están en el mismo runner efímero. No habilita escritores ni autoriza despliegue. Pendiente CI y revisión.

La prueba usa identidades y credenciales sintéticas de fixture, incluyendo el propietario auxiliar de #206 para probar preservación de ownership. No implica que esa topología cumpla la política dedicada #215 de producción.
