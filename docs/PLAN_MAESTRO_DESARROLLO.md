# Plan Maestro de Desarrollo — Batallas Medievales

| Campo | Valor |
|---|---|
| Estado | Activo |
| Versión | 2.0 |
| Fecha de auditoría | 2026-08-06 |
| Repositorio | `luis12duboqwe/Batallas-mediavales` |
| Rama auditada | `main` |
| Commit base auditado | `90d667a9ed9163401eea57c7c0c52e0c3fb1ccd6` |
| Próxima revisión | Al completar cada hito de salida |

## 1. Propósito

Este documento convierte el prototipo actual en un proyecto ejecutable por etapas. Es la fuente de verdad para decidir qué se construye, en qué orden, qué se pospone y qué evidencia se exige antes de considerar terminada una tarea o una versión.

El objetivo no es conservar todas las funciones existentes a cualquier costo. El objetivo final es entregar **Batallas Medievales v1.0 como juego completo, público, operable y mantenible**. La alpha y la beta son hitos intermedios para validar el producto; no representan el cierre del proyecto.

En este plan, “100 % terminado” significa cumplir todo el alcance aprobado para v1.0 y su puerta G10 con evidencia real. No significa que un juego vivo nunca pueda recibir nuevos mundos, balance, contenido o expansiones después del lanzamiento.

## 2. Dictamen de la auditoría inicial

No existía un plan de desarrollo, README, hoja de ruta, backlog, hitos ni definición de terminado. El repositorio es un prototipo con una superficie funcional grande, pero no es todavía una aplicación finalizada.

### Evidencia reproducible

| Área | Evidencia observada | Consecuencia |
|---|---|---|
| Backend | `app/main.py` importa `hero_service`, módulo que no existe con ese nombre | La API no puede iniciar desde el HEAD auditado |
| Registro de routers | Existen routers de administración, logros, anti-cheat, conquista, economía, iconos, tienda y temas que no se registran en `main.py` | Varias funciones y pantallas no pueden llegar a su API |
| Frontend | `npm run build` falla porque `SocketContext.jsx` importa `../store/authStore`, archivo inexistente | No se puede generar el paquete de producción |
| Lint frontend | `npm run lint` falla porque no existe configuración de ESLint | El control configurado en CI no puede pasar |
| Pruebas | Hay 26 casos de prueba para una superficie de aproximadamente 37 routers y 38 servicios | La cobertura funcional es insuficiente y no hay E2E |
| CI | El HEAD auditado no tiene ejecuciones ni estados de GitHub Actions | No hay evidencia automática de calidad del código actual |
| Workflow | El workflow ejecuta `pytest batalla_medieval_backend`, aunque las pruebas están en `/tests` | La validación de backend está mal dirigida |
| Datos | Se usa `Base.metadata.create_all()` y no existe un sistema de migraciones | No se pueden evolucionar esquemas de producción de forma segura |
| Seguridad | Se permite CORS global con credenciales, hay un secreto JWT por defecto, la verificación de correo está desactivada y Socket.IO permite elegir cualquier `user_id` al unirse a una sala | Riesgo alto de suplantación y configuración insegura |
| Despliegue | El Dockerfile frontend contiene una instrucción `COPY` inválida y Nginx fija certificados de `example.com` | El despliegue descrito no es reproducible |
| Higiene | Hay bases SQLite, `__pycache__`, `.pyc`, cobertura y logs versionados; se detectaron 197 artefactos generados | El historial y los cambios quedan contaminados |
| Consistencia | Hay constantes de economía duplicadas entre servicios | El balance puede variar según el endpoint utilizado |

### Fortalezas aprovechables

- Separación general por modelos, esquemas, servicios y routers.
- Backend FastAPI y frontend React ya estructurados.
- Sistemas de ciudades, mundos, colas, tropas, movimientos, combate, espionaje, alianzas, mercado y reportes parcialmente implementados.
- Pruebas iniciales de economía, combate, colas, multi-mundo y autenticación.
- Infraestructura inicial de Docker, Nginx y GitHub Actions.
- Regla explícita de aislamiento por mundo y prohibición de conquista PvP.

### Conclusión

La estrategia correcta es **estabilizar y recortar antes de ampliar**. Hasta aprobar el hito G1 queda congelada la creación de funciones nuevas que no corrijan un bloqueo del MVP.

## 3. Visión del producto

Batallas Medievales será un juego persistente de estrategia para navegador donde cada jugador desarrolla una ciudad, administra recursos, forma un ejército, interactúa con un mapa compartido y compite o coopera con otros jugadores dentro de mundos independientes.

### Ciclo jugable principal

1. Crear y verificar una cuenta.
2. Elegir o unirse a un mundo.
3. Recibir una ciudad inicial protegida.
4. Producir y gastar recursos.
5. Mejorar edificios y ampliar capacidad.
6. Investigar y entrenar tropas.
7. Explorar el mapa.
8. Atacar bárbaros o jugadores, espiar, reforzar y transportar.
9. Recibir informes, recuperarse y planificar el siguiente movimiento.
10. Progresar en clasificación y alianza durante la vida del mundo.

### Resultado final esperado

La versión v1.0 debe poder ser utilizada por jugadores reales sin intervención técnica cotidiana: registro, progreso, economía, combate, interacción social, contenido, administración, soporte, seguridad, recuperación ante fallos y despliegue deben funcionar de extremo a extremo. Toda función visible debe estar terminada; una función incompleta debe completarse o retirarse antes del lanzamiento.

## 4. Alcance de la primera versión jugable — hito intermedio

### Incluido en el MVP

- Registro, inicio de sesión, recuperación de contraseña y verificación de correo.
- Selección, ingreso y aislamiento completo de mundos.
- Ciudad inicial, producción de madera, barro e hierro, almacén y población.
- Edificios, requisitos, costos y una cola de construcción confiable.
- Investigación y cola de entrenamiento de tropas.
- Mapa, ciudades bárbaras y protección de jugador nuevo.
- Movimientos de ataque, espionaje, refuerzo, transporte y retorno.
- Combate PvE y PvP, saqueo, bajas e informes reproducibles.
- Conquista exclusiva de ciudades bárbaras.
- Ranking básico, alianza, mensajería y notificaciones.
- Panel administrativo mínimo para mundos, usuarios, sanciones y diagnóstico.
- Tutorial corto que complete el primer ciclo de progreso.
- Despliegue de beta cerrada con copias de seguridad y monitoreo.

### Pospuesto hasta después del MVP

El código existente puede conservarse, pero estas funciones permanecerán desactivadas hasta que el núcleo sea estable:

- Héroes, inventario y aventuras.
- Medallas de honor, tienda, temas y cosméticos.
- Temporadas, eventos avanzados y ciclo automatizado de mundos.
- Wiki editable, foro avanzado y API pública.
- Premium, monetización y pagos.
- Generación dinámica de iconos.
- Expansión de idiomas más allá del español necesario para la beta.
- Animaciones, música y efectos que afecten rendimiento o accesibilidad.

Estas funciones están fuera del corte MVP, pero no se consideran automáticamente fuera de v1.0. Las fases G6–G10 determinan cuáles forman parte obligatoria del juego completo y cuáles se retiran de forma explícita.

### Alcance obligatorio del juego completo v1.0

- Todo el MVP estabilizado y validado con jugadores reales.
- Economía canónica de madera, piedra, hierro y oro, con producción, almacenamiento, costes, comercio y mantenimiento de tropas consistentes.
- Ciudades y campamentos, con expansión mediante los puntos generados por iglesia y catedral.
- Catálogo completo y balanceado de edificios, investigaciones y unidades.
- Combate instantáneo por rondas, sin terreno ni obstáculos, con resultados reproducibles desde una semilla auditable.
- Espionaje completo con probabilidad y suerte controladas por el servidor.
- Comercio disponible desde el inicio bajo límites antiabuso.
- Bárbaros, oasis, héroe, inventario y aventuras como paquetes completos, balanceados e integrados; no se publicarán versiones parciales.
- Alianzas, diplomacia, chat, mensajería, foro de alianza, informes, notificaciones y clasificaciones.
- Tutorial como único sistema de misiones obligatorias y medallas de honor sin bonos de recursos o combate.
- Ciclo de vida de mundos, eventos administrables y temporadas únicamente cuando no destruyan el progreso sin una regla anunciada.
- Administración, moderación, soporte, auditoría y controles antiabuso.
- Interfaz final adaptable, accesible y consistente, con arte, animación y sonido dentro del presupuesto de rendimiento.
- Español completo; inglés completo si permanece seleccionable en producción.
- Producción con monitoreo, alertas, copias de seguridad, restauración, seguridad, privacidad, términos y canal de soporte.

### Fuera de v1.0 salvo decisión posterior del propietario

- Conquista de ciudades de otros jugadores.
- Venta de ventajas directas de combate, producción, velocidad o capacidad.
- Aplicaciones móviles nativas; v1.0 será web adaptable e instalable cuando la plataforma lo permita.
- API pública para terceros.
- Niveles sin límite como requisito de contenido: la arquitectura aceptará crecimiento por fórmula, pero v1.0 tendrá un rango balanceado y probado.

## 5. Decisiones canónicas del juego

| ID | Decisión |
|---|---|
| PD-001 | El MVP puede estabilizar temporalmente los tres recursos actuales, pero v1.0 usa cuatro recursos canónicos: madera, piedra, hierro y oro. La sustitución de barro y la incorporación de oro se ejecutan mediante migración versionada después de G5. |
| PD-002 | El servidor calcula y valida recursos, costos, tiempo, combate, botín y recompensas. El frontend nunca es autoridad. |
| PD-003 | Toda entidad y consulta jugable se filtra por `world_id`. Las acciones entre mundos son inválidas. |
| PD-004 | Se permite atacar y saquear a otro jugador cuando no existe protección aplicable. |
| PD-005 | Está prohibido conquistar ciudades de otros jugadores; solamente pueden conquistarse ciudades bárbaras con `owner_id = null`. |
| PD-006 | La protección inicial dura 48 horas por defecto y debe probarse en todos los tipos de movimiento hostil. |
| PD-007 | El tiempo se almacena en UTC y se muestra en la zona del jugador. |
| PD-008 | La beta no vende ventajas de combate, producción, velocidad ni capacidad. |
| PD-009 | Cada mundo tiene reglas y balance versionados; un cambio no altera silenciosamente mundos ya iniciados. |
| PD-010 | Una operación económica o militar debe ser atómica, idempotente cuando corresponda y resistente a solicitudes simultáneas. |
| PD-011 | El combate se resuelve de forma instantánea por rondas en el servidor; no usa terreno ni obstáculos tácticos. |
| PD-012 | El espionaje puede revelar información completa según la relación entre espías y una suerte limitada, auditable y calculada en servidor. |
| PD-013 | Las unidades tienen mantenimiento; no puede entrenarse o conservarse un ejército ignorando la capacidad económica definida para el mundo. |
| PD-014 | El comercio está disponible desde el inicio y sus límites, transporte y protección antiabuso son reglas versionadas del mundo. |
| PD-015 | Las misiones obligatorias pertenecen únicamente al tutorial. Las medallas de honor reconocen logros, pero no entregan bonos económicos o militares. |
| PD-016 | La expansión territorial usa ciudades y campamentos; iglesia y catedral generan los puntos requeridos para la expansión según el balance del mundo. |
| PD-017 | “Juego completo” significa una v1.0 que aprueba G10. Las ampliaciones posteriores se gestionan como operación viva y no impiden declarar terminado el alcance v1.0. |

## 6. Arquitectura objetivo

### Backend

- FastAPI como API HTTP y puerta de autenticación.
- SQLAlchemy con PostgreSQL como base de producción.
- Alembic para cada cambio de esquema.
- Servicios de dominio sin dependencias HTTP.
- Transacciones y bloqueo de filas en gastos, colas, mercado, botín y movimientos.
- Worker único o cola de trabajos para procesar eventos; el scheduler no debe duplicarse por cada proceso web.
- Socket.IO autenticado con JWT y autorización de salas en servidor.

### Frontend

- React, Vite, Tailwind y Zustand.
- Un único store de sesión y contrato uniforme para Axios.
- Estado proveniente del servidor para todos los datos jugables.
- Manejo global de carga, errores, expiración de sesión y reintentos seguros.
- Diseño adaptable primero a móvil y controles accesibles por teclado.

### Operación

- Dockerfiles reproducibles y sin pasos opcionales ocultos.
- Nginx configurable por dominio y con soporte de WebSocket.
- Separación entre validación continua y despliegue.
- Entornos local, pruebas, staging y producción con configuración explícita.
- Logs estructurados, métricas, alertas, copias de seguridad y restauración probada.

## 7. Hoja de ruta por hitos

Las duraciones son orientativas. Ninguna fase avanza por fecha: avanza únicamente cuando cumple su puerta de salida.

### Fase 0 — Recuperación de la línea base

Objetivo: lograr que el repositorio pueda instalarse, iniciar, validarse y revisarse de forma repetible.

- Corregir el entrypoint del backend y registrar explícitamente solo routers válidos.
- Unificar `authStore` y `userStore`; eliminar importaciones inexistentes.
- Añadir configuración de ESLint y corregir los errores bloqueantes.
- Corregir rutas de Pytest, `PYTHONPATH`, cobertura y fixtures.
- Separar CI de despliegue y ejecutar CI en cada PR.
- Corregir Dockerfiles, variables de entorno y configuración de Nginx.
- Ampliar `.gitignore` y retirar del control de versiones bases, cachés, cobertura y logs.
- Crear instrucciones verificadas de instalación y ejecución local.
- Fijar versiones de Python y Node compatibles.

**G0 — Línea base recuperada**

- Backend inicia y responde un endpoint de salud.
- Frontend instala con `npm ci` y genera `dist/`.
- Lint y pruebas se ejecutan con un solo comando documentado.
- El PR de recuperación tiene CI verde.
- No quedan artefactos generados versionados.

### Fase 1 — Fundación segura y mantenible

Objetivo: asegurar datos, autenticación, contratos y ejecución en segundo plano antes de probar el juego.

- Incorporar Alembic y crear una migración base reproducible.
- Eliminar secretos por defecto en producción y validar configuración al iniciar.
- Corregir CORS, cookies/tokens, verificación de correo y política de contraseñas.
- Autenticar Socket.IO y derivar la sala desde el JWT, nunca desde un `user_id` enviado por el cliente.
- Separar scheduler/worker del proceso web y garantizar un solo procesamiento por evento.
- Definir errores de dominio y respuestas API consistentes.
- Añadir transacciones, bloqueos e idempotencia a operaciones económicas.
- Crear seed mínimo versionado para unidades, edificios, mundos y bárbaros.
- Crear pruebas de contrato entre cliente y API.

**G1 — Plataforma confiable**

- Una base vacía puede migrarse y sembrarse automáticamente.
- Registro, verificación, login y recuperación funcionan de extremo a extremo.
- No hay vulnerabilidades críticas o altas conocidas en dependencias o flujos propios.
- Dos solicitudes simultáneas no pueden gastar los mismos recursos.
- Reiniciar API y worker no duplica colas, tropas ni movimientos.

### Fase 2 — Corte vertical jugable

Objetivo: completar un recorrido de un jugador sin depender de sistemas secundarios.

- Crear/unirse a un mundo y recibir ciudad inicial.
- Calcular producción y límites de almacenamiento en servidor.
- Mejorar un edificio con costo, requisitos, tiempo, cancelación y finalización.
- Investigar y entrenar una unidad.
- Mostrar mapa y una ciudad bárbara cercana.
- Enviar ataque, resolverlo, retornar tropas y generar informe.
- Completar tutorial inicial con recompensas idempotentes.
- Desactivar en interfaz todas las rutas fuera del MVP que aún no sean confiables.

**G2 — Alpha jugable**

- Un usuario nuevo completa el ciclo principal sin intervención administrativa.
- Recargar, cerrar sesión o reiniciar servicios no pierde ni duplica progreso.
- El flujo crítico tiene pruebas API y E2E automatizadas.
- No hay errores de consola ni respuestas 5xx durante el recorrido aceptado.

### Fase 3 — Núcleo multijugador

Objetivo: validar interacciones entre jugadores dentro de un mundo.

- Ataque PvP, saqueo, refuerzo, espionaje y retorno.
- Protección de novatos y restricciones entre mundos.
- Mercado con ofertas atómicas y transporte.
- Alianzas, invitaciones, rangos y diplomacia mínima.
- Mensajería, notificaciones y tiempo real autenticado.
- Ranking por mundo y ocultamiento de datos sensibles.
- Herramientas de moderación y bitácora administrativa.

**G3 — Alpha multijugador**

- Escenarios automatizados de al menos dos jugadores cubren todos los movimientos.
- Ninguna prueba logra atacar, comerciar, espiar o leer datos entre mundos.
- Ninguna prueba logra conquistar una ciudad de otro jugador.
- Una simulación concurrente acordada completa 24 horas sin duplicaciones ni stock negativo.

### Fase 4 — Balance, contenido y retención

Objetivo: convertir el núcleo correcto en un juego entendible y sostenible.

- Centralizar todas las constantes de balance en datos versionados.
- Definir edificios, unidades, requisitos, tiempos, mantenimiento y capacidad.
- Balancear progreso inicial, protección, botín y recuperación tras derrota.
- Mejorar tutorial, ayudas contextuales e informes.
- Cerrar el tutorial como único sistema de misiones e incorporar medallas de honor sin ventajas cuando usen eventos de dominio confiables.
- Probar accesibilidad, móvil, latencia lenta y traducciones visibles.

**G4 — Candidato a beta**

- No existen fórmulas contradictorias entre API, UI y documentación.
- La primera sesión tiene objetivos claros y no presenta bloqueos económicos.
- Las métricas de progreso y abandono pueden observarse sin exponer datos personales.
- Todas las funciones visibles cumplen la definición de terminado.

### Fase 5 — Operación de beta cerrada

Objetivo: publicar de forma controlada y recuperable.

- Desplegar staging idéntico a producción.
- Ejecutar análisis de seguridad, prueba de carga y prueba de larga duración.
- Configurar dominio, TLS, correo, backups, alertas y rotación de secretos.
- Crear runbooks de despliegue, rollback, restauración y respuesta a incidentes.
- Definir términos, privacidad, retención de datos y canal de soporte.
- Ejecutar beta cerrada por oleadas y corregir severidades P0/P1 antes de ampliar cupos.

**G5 — Beta cerrada publicable**

- CI, staging, migraciones, backup y restauración tienen evidencia reciente.
- Cero defectos P0/P1 abiertos.
- La tasa de error 5xx y la latencia permanecen dentro de los objetivos acordados.
- Existe rollback probado para aplicación y base de datos.
- El propietario del producto aprueba explícitamente la apertura de la beta.

### Fase 6 — Mecánicas completas de v1.0

Objetivo: convertir el núcleo probado en el conjunto final de reglas del juego, sin mantener dos economías o fórmulas incompatibles.

- Migrar la economía a madera, piedra, hierro y oro, con compatibilidad de datos y rollback ensayado.
- Completar edificios, investigaciones, unidades, requisitos, costes, mantenimiento y capacidades.
- Implementar ciudades, campamentos y expansión mediante iglesia y catedral.
- Cerrar combate instantáneo por rondas, moral, suerte limitada, bajas, botín y recuperación.
- Completar espionaje, refuerzos, transporte, comercio desde el inicio y protección de novatos.
- Terminar bárbaros y oasis con comportamiento, recompensas y dificultad versionados.
- Completar como paquete indivisible héroe, objetos y aventuras, incluyendo balance, persistencia, API, UI y pruebas E2E.
- Eliminar código, rutas, pantallas y datos de prototipo que contradigan las reglas finales.

**G6 — Reglas finales cerradas**

- El catálogo y todas las fórmulas provienen de una única versión de balance.
- Una migración de staging conserva cuentas y progreso al adoptar los cuatro recursos.
- Todos los movimientos, combates, expansiones y gastos tienen pruebas negativas, concurrentes y E2E.
- No existe una pantalla visible que use una regla provisional o un servicio alternativo.
- El propietario aprueba el documento de diseño y el catálogo de contenido de v1.0.

### Fase 7 — Mundo, contenido y comunidad completos

Objetivo: cerrar todos los sistemas que dan vida y continuidad a un mundo multijugador.

- Completar alianzas, rangos, permisos, invitaciones, diplomacia y foro de alianza.
- Completar chat, mensajería, notificaciones, informes y controles de privacidad/bloqueo.
- Completar ranking por mundo y medallas de honor sin recompensas de recursos o combate.
- Limitar las misiones al tutorial y retirar recompensas repetibles incompatibles con PD-015.
- Definir eventos administrables, temporadas y ciclo de apertura/cierre de mundos sin cambios silenciosos.
- Completar panel administrativo, moderación, sanciones, soporte, auditoría y herramientas anti-cheat.
- Publicar ayuda y wiki de solo lectura alineadas con las reglas versionadas; la edición pública y la API de terceros quedan fuera de v1.0.

**G7 — Mundo completo**

- Un mundo puede abrirse, operar, moderarse, respaldarse y cerrarse siguiendo un runbook probado.
- Los sistemas sociales superan pruebas de permisos, privacidad, abuso e aislamiento por mundo.
- Todo contenido visible tiene dueño, estado, pruebas, texto final y comportamiento documentado.
- No hay recompensas explotables, funciones huérfanas ni enlaces hacia rutas incompletas.

### Fase 8 — Experiencia final, arte y accesibilidad

Objetivo: transformar la aplicación funcional en un juego coherente, entendible y agradable en escritorio y móvil.

- Crear y aplicar un sistema visual medieval consistente para navegación, mapa, ciudad, unidades, edificios e informes.
- Sustituir recursos visuales provisionales por arte con licencia y trazabilidad válidas.
- Completar diseño adaptable, navegación táctil, teclado, contraste, foco, textos y lectores de pantalla en flujos críticos.
- Incorporar sonido, música y animaciones con controles independientes, reducción de movimiento y carga diferida.
- Completar estados vacíos, carga, error, reconexión, sesión expirada, mantenimiento y pérdida de red.
- Completar español; completar inglés o retirar el selector antes del lanzamiento.
- Optimizar tamaño de descarga, memoria, renderizado del mapa y rendimiento en equipos de gama media/baja.

**G8 — Candidato de lanzamiento**

- Las pruebas visuales y E2E cubren las resoluciones y navegadores soportados.
- No quedan textos, iconos, sonidos, pantallas o rutas provisionales visibles.
- Se cumplen presupuestos medidos de accesibilidad y rendimiento.
- Jugadores que no conocen el proyecto pueden completar tutorial, progreso, comercio y combate sin ayuda del desarrollador.

### Fase 9 — Producción, legal y sostenibilidad

Objetivo: asegurar que v1.0 pueda publicarse y mantenerse de forma responsable.

- Ejecutar auditoría de seguridad, abuso, privacidad, dependencias y configuración de producción.
- Finalizar términos de uso, privacidad, cookies, edades aplicables, eliminación/exportación de cuenta y retención de datos.
- Completar soporte, estado del servicio, respuesta a incidentes y procedimiento de apelación de sanciones.
- Probar carga, larga duración, escalado, despliegue sin pérdida, rollback, backup y restauración.
- Decidir el modelo de sostenibilidad: sin pagos o tienda exclusivamente cosmética/conveniencia sin ventaja; un pago real exige integración, conciliación, reembolso y pruebas propias.
- Preparar analítica respetuosa de privacidad para errores, embudo inicial, retención y balance.

**G9 — Aprobación para lanzamiento público**

- Cero vulnerabilidades críticas o altas y cero defectos P0/P1 abiertos.
- Restauración, rollback y respuesta a incidentes tienen simulacros recientes.
- Todos los requisitos legales y de soporte aplicables están publicados.
- La capacidad medida soporta el cupo de lanzamiento con margen acordado.
- Si hay pagos, una compra, fallo, reintento, devolución y conciliación pasan de extremo a extremo; si no, todos los endpoints y botones de pago permanecen desactivados.

### Fase 10 — Lanzamiento controlado y cierre de v1.0

Objetivo: demostrar en condiciones reales que el producto completo funciona y cerrar formalmente el proyecto v1.0.

- Ejecutar lanzamiento gradual con límites de jugadores y ampliación basada en métricas.
- Observar economía, balance, errores, abuso, rendimiento y soporte durante un periodo mínimo acordado.
- Corregir todos los P0/P1 y decidir explícitamente cada P2 antes de declarar la versión final.
- Congelar catálogo, reglas, migraciones, arte, documentación y runbooks de v1.0.
- Etiquetar la versión, publicar notas, registrar evidencias y aprobar el acta de cierre.

**G10 — Batallas Medievales v1.0 terminado al 100 %**

- G0–G9 permanecen aprobados y su evidencia sigue vigente.
- El 100 % del alcance obligatorio de v1.0 está terminado o existe una decisión aprobada que lo retire del alcance antes del lanzamiento.
- Cero funciones visibles incompletas, P0/P1 abiertos, migraciones pendientes o controles obligatorios omitidos.
- Los objetivos de producción se cumplen durante el periodo de observación acordado.
- Código, infraestructura, datos, contenido, seguridad, soporte y documentación pueden mantenerse sin depender de conocimiento no escrito.
- El propietario del producto firma el cierre de v1.0 contra el commit y la versión desplegada exactos.

### Fase 11 — Operación viva posterior a v1.0

Esta fase comienza después del cierre y no se usa para ocultar trabajo incompleto de v1.0. Incluye nuevos mundos, balance, temporadas, eventos, contenido, cosméticos, idiomas y expansiones aprobadas. Cada cambio mantiene las mismas reglas de issue, PR, pruebas, migración y observabilidad.

## 8. Backlog maestro priorizado

| ID | Prioridad | Tamaño | Trabajo | Criterio de aceptación principal |
|---|---:|---:|---|---|
| BM-0001 | P0 | M | Limpiar entrypoint e imports del backend | `uvicorn app.main:app` inicia sin error y `/health` devuelve 200 |
| BM-0002 | P0 | S | Unificar store de autenticación frontend | No existe referencia a `authStore`; login y SocketProvider usan el mismo estado |
| BM-0003 | P0 | M | Recuperar build y lint frontend | `npm ci`, `npm run lint` y `npm run build` terminan en 0 |
| BM-0004 | P0 | M | Reparar suite y comando Pytest | Se recopilan y ejecutan las pruebas de `/tests` desde una instalación limpia |
| BM-0005 | P0 | M | Crear workflow de validación de PR | Backend, frontend y build de imágenes se validan sin secretos de despliegue |
| BM-0006 | P0 | S | Limpiar archivos generados del repositorio | No hay `.db`, `.pyc`, `__pycache__`, cobertura ni logs rastreados |
| BM-0007 | P0 | M | Corregir Docker y Nginx | `docker compose build` funciona y la configuración no fija `example.com` |
| BM-0008 | P0 | S | Alinear dependencias de contraseñas | Registro crea y verifica el hash en un entorno limpio |
| BM-0010 | P1 | L | Introducir Alembic | Base nueva y actualización desde versión anterior pasan migraciones |
| BM-0011 | P1 | M | Endurecer configuración y secretos | Producción se niega a iniciar con secreto o CORS inseguro |
| BM-0012 | P1 | M | Autenticar Socket.IO | Un usuario no puede unirse a la sala de otro usuario |
| BM-0013 | P1 | L | Separar worker y hacer colas idempotentes | Reintentos y dos workers no duplican resultados |
| BM-0014 | P1 | L | Proteger transacciones económicas | Pruebas concurrentes nunca generan recursos negativos ni doble gasto |
| BM-0015 | P1 | M | Corregir registro de routers y contrato API | Toda ruta visible en el MVP existe y tiene prueba de contrato |
| BM-0016 | P1 | M | Seed canónico del juego | Mundo, edificios, unidades y bárbaros se crean de forma repetible |
| BM-0020 | P1 | L | Completar ciclo de ciudad y producción | Recursos y almacenamiento coinciden tras pausa, reinicio y recarga |
| BM-0021 | P1 | L | Completar cola de edificios | Crear, cancelar y finalizar son atómicos e idempotentes |
| BM-0022 | P1 | L | Completar investigación y tropas | Requisitos, costo, población y finalización están validados en servidor |
| BM-0023 | P1 | L | Corte vertical contra bárbaros | Ataque, combate, botín, retorno e informe pasan E2E |
| BM-0024 | P1 | M | Tutorial inicial | Puede completarse una vez y las recompensas no se duplican |
| BM-0030 | P1 | XL | Movimientos multijugador | Ataque, espía, refuerzo, transporte y retorno pasan matrices de permisos |
| BM-0031 | P1 | L | Protección y conquista | Protección cubre hostilidades y conquista PvP es imposible |
| BM-0032 | P1 | L | Mercado atómico | Oferta, aceptación y cancelación resisten concurrencia y autorización |
| BM-0033 | P2 | L | Alianzas y diplomacia mínima | Rangos y acciones tienen permisos y aislamiento por mundo |
| BM-0034 | P2 | M | Mensajes y notificaciones | Privacidad, lectura, borrado y entrega se prueban de extremo a extremo |
| BM-0040 | P2 | L | Fuente única de balance | API, simulador, servicios y UI consumen la misma versión de reglas |
| BM-0050 | P1 | L | Observabilidad y alertas | Logs correlacionados, métricas y alertas cubren API, worker y BD |
| BM-0051 | P1 | L | Backup y restauración | Una restauración ensayada recupera cuentas y progreso dentro del RPO |
| BM-0052 | P1 | L | Pruebas de carga y larga duración | Se documentan capacidad, límites y ausencia de duplicación |
| BM-0053 | P1 | M | Seguridad previa a beta | Cero hallazgos críticos/altos abiertos y dependencias revisadas |
| BM-0060 | P1 | XL | Migrar a cuatro recursos | Madera, piedra, hierro y oro funcionan con migración, rollback, pruebas y una única fuente de balance |
| BM-0061 | P1 | XL | Ciudades, campamentos y expansión | Iglesia/catedral generan puntos y la expansión completa pasa E2E sin permitir conquista PvP |
| BM-0062 | P1 | XL | Catálogo final de edificios e investigación | Requisitos, efectos, tiempos y niveles aprobados coinciden en servidor, UI y ayuda |
| BM-0063 | P1 | XL | Catálogo final de unidades y mantenimiento | Entrenamiento, población, mantenimiento, velocidad, carga y defensa quedan balanceados y probados |
| BM-0064 | P1 | XL | Combate final por rondas | PvE/PvP, moral, suerte, bajas, botín y retorno son reproducibles y resistentes a reintentos |
| BM-0065 | P1 | L | Espionaje completo | Éxito, detección y datos revelados respetan suerte limitada, permisos y aislamiento |
| BM-0066 | P1 | L | Comercio desde el inicio | Mercado y transporte aplican límites, autorización, atomicidad y protección antiabuso |
| BM-0067 | P2 | XL | Bárbaros y oasis finales | Generación, dificultad, IA, recompensas y regeneración están versionadas y balanceadas |
| BM-0068 | P2 | XL | Paquete héroe, objetos y aventuras | El paquete completo pasa balance, permisos, datos, API, UI y E2E sin rutas parciales |
| BM-0070 | P1 | XL | Comunidad y diplomacia completas | Alianzas, rangos, diplomacia, chat, mensajes y foro pasan permisos, privacidad y moderación |
| BM-0071 | P2 | L | Ranking y medallas de honor | Cálculo, desempate y privacidad son correctos; las medallas no entregan ventajas |
| BM-0072 | P1 | XL | Ciclo de vida de mundos | Crear, abrir, pausar, cerrar y archivar un mundo conserva datos y sigue reglas anunciadas |
| BM-0073 | P1 | XL | Administración, soporte y moderación | Acciones sensibles requieren permisos, motivo, auditoría y procedimiento de reversión |
| BM-0074 | P1 | L | Anti-cheat y protección contra abuso | Detección, rate limit y sanciones reducen abuso sin decisiones automáticas irreversibles |
| BM-0075 | P2 | L | Tutorial y ayuda final | El tutorial es el único sistema obligatorio de misiones y la ayuda coincide con el balance vigente |
| BM-0080 | P1 | XL | Sistema visual y arte final | No quedan recursos provisionales y cada activo tiene licencia y uso documentados |
| BM-0081 | P1 | XL | Adaptabilidad y accesibilidad | Flujos críticos funcionan en móvil, escritorio, teclado y tecnologías de asistencia |
| BM-0082 | P2 | L | Sonido, música y animaciones | Controles, reducción de movimiento, carga diferida y presupuesto de rendimiento pasan QA |
| BM-0083 | P2 | L | Localización final | Español está completo; inglés está completo o se retira de producción sin rutas rotas |
| BM-0084 | P1 | L | Resiliencia de interfaz | Carga, vacío, error, reconexión, mantenimiento y expiración de sesión tienen UX probada |
| BM-0085 | P1 | L | Rendimiento cliente | Descarga, memoria, mapa e interacción cumplen presupuestos medidos en dispositivos objetivo |
| BM-0090 | P1 | L | Privacidad, términos y cuentas | Consentimiento, exportación, eliminación y retención funcionan y están documentados |
| BM-0091 | P2 | XL | Sostenibilidad y pagos opcionales | Se aprueba juego sin pagos o se completa compra, fallo, reembolso y conciliación sin pay-to-win |
| BM-0092 | P1 | XL | Plataforma final de producción | Despliegue, TLS, correo, escalado, observabilidad, alertas y estado del servicio están operativos |
| BM-0093 | P1 | L | Recuperación de desastres | Backup, restauración, rollback y pérdida de una dependencia pasan simulacros |
| BM-0100 | P1 | L | Lanzamiento gradual | Cupos y ampliaciones se gobiernan por errores, capacidad, abuso y soporte observados |
| BM-0101 | P1 | XL | Cierre de defectos de lanzamiento | No quedan P0/P1 y cada P2 tiene resolución o aceptación explícita documentada |
| BM-0102 | P1 | M | Certificación y cierre v1.0 | Matriz de alcance, gates, commit, despliegue, notas y acta de cierre quedan vinculados |

P0 bloquea cualquier otro trabajo. P1 bloquea la siguiente puerta y siempre bloquea G10. Un P2 solo puede diferirse del lanzamiento mediante decisión explícita del propietario, con impacto y seguimiento documentados; no se oculta como “mejora futura”.

## 9. Estrategia de pruebas

| Nivel | Qué debe cubrir | Cuándo se ejecuta |
|---|---|---|
| Unitarias | Fórmulas, costos, tiempos, permisos y resultados deterministas | Cada PR |
| Integración | Servicios con PostgreSQL real, transacciones, migraciones y workers | Cada PR |
| API | Autenticación, validación, errores, autorización y aislamiento por mundo | Cada PR |
| Contrato | Rutas, payloads y respuestas utilizadas por Axios | Cada PR |
| Frontend | Stores, componentes críticos y manejo de errores | Cada PR |
| E2E | Registro, ciudad, edificio, tropa, ataque, retorno e informe | Cada PR y staging |
| Concurrencia | Doble gasto, mercado, colas, botín e idempotencia | Antes de G3 |
| Balance | Progresión, costes, mantenimiento, recuperación y simulaciones de economía/combate | Antes de G4, G6 y cada versión de reglas |
| Visual/accesibilidad | Resoluciones, navegadores, teclado, contraste, movimiento y tecnologías de asistencia | Continuo desde G4 y obligatorio para G8 |
| Carga | API, mapa, ranking, WebSocket y procesamiento de colas | Antes de G5, G9 y cada ampliación de cupo |
| Seguridad | Dependencias, secretos, auth, autorización, abuso y rate limit | Continuo y antes de G5, G9 y G10 |
| Pagos | Compra, idempotencia, fallo, reintento, reembolso y conciliación | Solo si se habilitan pagos, antes de G9 |
| Restauración | Backup, migración, rollback y recuperación | Antes de cada versión pública |

Objetivos iniciales:

- 100 % de los recorridos críticos con E2E.
- Al menos 80 % de cobertura en servicios del núcleo; la cobertura nunca sustituye los escenarios.
- Cero pruebas inestables aceptadas en `main`.
- Cero errores ignorados para obtener un CI verde.
- 100 % de funciones visibles vinculadas a pruebas, evidencia manual repetible o ambas según el riesgo.

## 10. Integración y despliegue continuos

### Workflow de validación

Se ejecuta en `pull_request` y en cada push a `main`:

1. Instalación bloqueada por lockfiles.
2. Lint y formato backend.
3. Migraciones en PostgreSQL temporal.
4. Pruebas backend y reporte de cobertura.
5. Lint y pruebas frontend.
6. Build de frontend.
7. Pruebas de contrato/E2E seleccionadas.
8. Build de imágenes Docker sin publicarlas.
9. Escaneo de dependencias, secretos e imágenes.

### Workflow de despliegue

- Staging tras fusionar a `main` y aprobar validación.
- Producción solamente mediante versión etiquetada y aprobación manual.
- Nunca se despliega desde un PR ni se mezclan pruebas con secretos SSH.
- Toda versión registra commit, migración, imágenes, responsable y procedimiento de rollback.

## 11. Definición de terminado

### Para una tarea

Una tarea no está terminada solo porque el código existe. Debe cumplir todo lo aplicable:

- Requisito y criterios de aceptación claros.
- Diseño compatible con multi-mundo y reglas canónicas.
- Código revisado, sin duplicación relevante ni dependencias no aprobadas.
- Migración y rollback cuando cambia datos.
- Pruebas unitarias, integración, contrato y/o E2E según el riesgo.
- Autorización y casos negativos probados.
- Lint, build, pruebas y seguridad en verde.
- Logs y métricas suficientes para diagnosticar el flujo.
- Documentación y variables de entorno actualizadas.
- Evidencia reproducible incluida en el PR.
- Sin defectos P0/P1 conocidos introducidos o aplazados silenciosamente.

### Para Batallas Medievales v1.0

El proyecto solo se declara terminado cuando:

- La matriz de alcance asigna a cada sistema obligatorio un estado `TERMINADO`, nunca `CASI`, `PARCIAL` o `POR VALIDAR`.
- G0–G10 tienen fecha, commit, responsable, pruebas y evidencia enlazada.
- Todas las pantallas y rutas publicadas corresponden a servicios terminados; el código descartado se elimina o queda fuera del artefacto desplegado.
- Una instalación limpia, una actualización desde la versión anterior, un rollback y una restauración se han ensayado.
- La versión desplegada coincide exactamente con la etiqueta y commit certificados.
- Documentación de jugador, operación, soporte, seguridad y desarrollo refleja el comportamiento real.
- El acta de cierre v1.0 está aprobada por el propietario del producto.

## 12. Objetivos operativos

Estos valores deben revisarse con resultados de carga reales:

- Disponibilidad mensual inicial: 99.5 %.
- Latencia p95 de API jugable: menor de 300 ms sin contar procesos programados largos.
- Error 5xx: menor de 0.5 % de solicitudes.
- RPO: máximo 24 horas durante beta cerrada.
- RTO: máximo 4 horas durante beta cerrada.
- Cero duplicaciones conocidas de recursos, tropas, recompensas o movimientos.
- Cero acceso comprobado a datos o acciones de otro mundo sin autorización.

Para G9/G10 se endurecen como mínimo a:

- Disponibilidad mensual objetivo: 99.9 %.
- Latencia p95 de API jugable: menor de 250 ms bajo la carga objetivo.
- Error 5xx: menor de 0.2 % de solicitudes.
- RPO: máximo 1 hora; RTO: máximo 2 horas.
- Cero vulnerabilidades críticas/altas, pérdida silenciosa de progreso, doble gasto o ruptura de aislamiento.
- Presupuestos de cliente, concurrencia y cupo documentados a partir de mediciones, no estimaciones.

## 13. Riesgos principales

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---:|---:|---|
| Gran cantidad de funciones no integradas | Alta | Crítico | Congelar extras y trabajar por cortes verticales |
| Doble gasto o duplicación por concurrencia | Alta | Crítico | Transacciones, locks, idempotencia y pruebas concurrentes |
| Ruptura del aislamiento multi-mundo | Media | Crítico | Filtros obligatorios, helpers centrales y pruebas negativas |
| Scheduler duplicado al escalar API | Alta | Alto | Worker separado con elección de líder o cola de trabajos |
| Migraciones inexistentes | Alta | Alto | Alembic desde Fase 1 y ensayo de rollback |
| Autenticación WebSocket suplantable | Alta | Alto | JWT en handshake y sala derivada del usuario verificado |
| Balance contradictorio | Alta | Alto | Catálogo versionado como fuente única |
| CI que no representa producción | Alta | Alto | PostgreSQL real, imágenes y E2E en validación |
| Confundir beta con juego terminado | Alta | Alto | G5 es intermedio; solo G10 autoriza declarar v1.0 terminada |
| “100 %” sin alcance verificable | Alta | Alto | Matriz v1.0, criterios binarios y retiro explícito de cualquier función descartada |
| Alcance excesivo | Alta | Alto | MVP estricto, paquetes verticales, gates y aprobación para cambiar v1.0 |
| Arte y sonido antes de estabilidad | Media | Medio | Presupuesto de rendimiento y activación posterior a G4 |

## 14. Gobierno del plan

- Cada issue y PR debe citar un ID `BM-####` o crear uno nuevo en este documento.
- Cambiar una regla `PD-###`, el alcance del MVP/v1.0 o una puerta de salida requiere aprobación explícita del propietario del producto.
- Los PR deben ser pequeños, permanecer en borrador mientras falte evidencia y no mezclar correcciones sin relación.
- No se fusiona con CI rojo, pruebas omitidas sin justificación o una migración irreversible no ensayada.
- Al cerrar un hito se actualizan: estado del backlog, evidencia, riesgos, métricas y siguiente prioridad.
- Desde G5 se mantiene una matriz de alcance v1.0 con sistema, responsable, estado, pruebas, defectos y evidencia; “existe código” no cuenta como avance terminado.
- Solo puede existir una fase activa de construcción. Investigación o diseño futuro puede adelantarse, pero no desplaza P0/P1 de la puerta vigente.

## 15. Próximos diez trabajos, en orden

1. BM-0001 — Recuperar el backend.
2. BM-0002 — Unificar autenticación frontend.
3. BM-0003 — Recuperar build y lint frontend.
4. BM-0004 — Recuperar Pytest.
5. BM-0006 — Limpiar artefactos versionados.
6. BM-0005 — Implantar CI real en PR.
7. BM-0007 — Corregir contenedores y proxy.
8. BM-0008 — Alinear hashing y dependencias.
9. BM-0010 — Crear migraciones.
10. BM-0011 y BM-0012 — Endurecer HTTP y WebSocket.

Hasta completar estos trabajos no debe iniciarse ninguna función nueva de juego.
