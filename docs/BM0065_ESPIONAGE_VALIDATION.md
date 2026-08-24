# BM-0065 — Validación del espionaje completo, reproducible y privado

## Estado

BM-0065 alcanzó un corte funcional completamente verde en **Validation #436** (`run_id=32750304839`) sobre el HEAD `67cc2a879f016beb968cc0a57d4b210f1ff19997`.

Ese corte valida en conjunto el resolver autoritativo de espionaje, la suerte controlada y reproducible, éxito y detección como tiradas independientes, niveles progresivos de inteligencia, privacidad de informes, pérdidas/retorno de espías, permisos PvP, aislamiento entre mundos, resistencia a reintentos y concurrencia, contrato público de balance, wiki, UI auditable, recorrido Browser G10 y las imágenes Docker.

El cierre definitivo del PR exige una Validation completa verde adicional sobre el HEAD que contenga **este documento**. Solo ese SHA documental puede marcarse Ready y fusionarse.

Versiones relevantes:

- `ESPIONAGE_ALGORITHM_VERSION = "2026.08.24-bm0065-v1"`;
- `BALANCE_VERSION = "2026.08.23-bm0063.1"`;
- suerte de espionaje entre `-0.20` y `+0.20`;
- probabilidad de éxito limitada a `0.05..0.95`;
- probabilidad de detección limitada a `0.05..0.95`;
- bonus de detección al fracasar: `+0.35` antes del clamp;
- umbral de inteligencia de tropas: `1.0`;
- umbral de inteligencia de edificios: `2.0`;
- offset defensivo de espías: `1.0`;
- probabilidad de que un atacante detectado permanezca sin identificar: `0.10`.

BM-0065 no reabre BM-0064 ni crea un segundo sistema militar: la unidad `spy`, sus requisitos, coste, velocidad y mantenimiento continúan viniendo del catálogo canónico de BM-0063.

## Criterios del plan maestro cubiertos

BM-0065 cierra el espionaje v1.0 como operación militar PvP autoritativa y auditable. El comportamiento final cubre:

- éxito o fracaso calculado únicamente por servidor;
- suerte controlada y reproducible;
- detección independiente del éxito;
- inteligencia parcial/progresiva en niveles 0..3;
- privacidad del objetivo cuando la misión no obtuvo autorización para revelar datos;
- informe del atacante siempre ligado al evento resuelto;
- informe del defensor únicamente cuando la misión fue detectada;
- identificación del atacante separada de la detección;
- pérdida total de la expedición cuando la misión fracasa;
- retorno de los espías enviados cuando la misión tiene éxito;
- exactamente un cierre de movimiento y, si corresponde, exactamente un retorno;
- aislamiento por mundo, prohibición de autoespionaje y respeto de protecciones;
- resistencia a doble ejecución secuencial y concurrente.

También preserva las decisiones de producto ya fijadas:

- el servidor es la única autoridad sobre resultado e información revelada;
- el cliente no controla semilla, suerte, tiradas ni nivel de inteligencia;
- las operaciones militares deben ser atómicas, idempotentes y resistentes a concurrencia;
- las reglas de mundo se exponen de forma versionada y verificable;
- BM-0064 conserva intactas sus semillas y reglas de combate.

## Resolver autoritativo

El resolver vive en `app/services/espionage.py` y se integra en el worker existente de movimientos. No existe una segunda cola ni un resolver paralelo de espionaje.

Para una misión válida, el servidor:

1. carga ciudad atacante y objetivo dentro del mismo mundo;
2. exige al menos un espía enviado;
3. obtiene el número actual de espías defensores;
4. obtiene el `spy_modifier` de eventos activos;
5. construye una semilla SHA-256 a partir del movimiento y del snapshot autoritativo del objetivo;
6. crea un `random.Random(seed)` local;
7. genera suerte dentro de `[-0.20, +0.20]`;
8. calcula y limita la probabilidad de éxito;
9. ejecuta la tirada de éxito;
10. calcula por separado la probabilidad de detección;
11. ejecuta la tirada de detección;
12. si fue detectado, resuelve por separado si el atacante queda identificado;
13. calcula el nivel de inteligencia 0..3;
14. construye informes distintos según rol y permisos de información;
15. devuelve al worker el número de espías supervivientes.

El servicio no hace `commit` por su cuenta: la transición completa queda dentro de la transacción del worker de movimientos.

## Fórmula de éxito

La relación base es:

`attacker_spies / (defender_spies + 1.0)`

La probabilidad autoritativa aplica después:

`ratio * max(spy_modifier, 0) * (1 + luck)`

El resultado se limita siempre al intervalo `[0.05, 0.95]`.

Consecuencias:

- nunca existe éxito garantizado al 100%;
- nunca existe fracaso garantizado al 100%;
- más espías atacantes aumentan la presión ofensiva;
- más espías defensores reducen la relación;
- eventos como `DARK_MOON` pueden modificar la eficacia mediante `spy_modifier` sin alterar el algoritmo base;
- la suerte está acotada y no puede dominar ilimitadamente la relación de fuerzas.

## Detección independiente

La detección no es sinónimo de fracaso.

Su base es:

`defender_spies / (attacker_spies + 1.0)`

Después se aplica el efecto de suerte del atacante:

`base * (1 - luck)`

Si la misión fracasa se añade `0.35` antes de limitar el resultado a `[0.05, 0.95]`.

La detección se resuelve con una tirada RNG distinta a la de éxito. Por ello son posibles, entre otros, estos estados válidos:

- éxito y no detectado;
- éxito y detectado;
- fracaso y no detectado;
- fracaso y detectado.

Cuando una misión detectada resuelve identificación, existe un `10%` de probabilidad canónica de mantener al atacante como `Desconocido`. Esa decisión usa el mismo RNG local del evento.

## Niveles de inteligencia

Un fracaso produce siempre `intel_level = 0`.

Si la misión tiene éxito, el score usa la misma relación modificada de espionaje:

`ratio * max(spy_modifier, 0) * (1 + luck)`

Los niveles son:

- **nivel 1**: revela recursos;
- **nivel 2**: revela recursos + tropas;
- **nivel 3**: revela recursos + tropas + edificios.

Umbrales:

- score `< 1.0` -> nivel 1;
- score `>= 1.0` y `< 2.0` -> nivel 2;
- score `>= 2.0` -> nivel 3.

El snapshot de recursos usa exclusivamente los cuatro recursos canónicos `wood`, `stone`, `iron` y `gold`. No se reintroduce `clay`.

La ausencia de una unidad en el snapshot de tropas significa cantidad cero dentro de una misión que sí alcanzó autorización de inteligencia de tropas; no debe confundirse con información oculta de un nivel inferior.

## Semilla reproducible y auditabilidad

La semilla se deriva con SHA-256 de una representación JSON canónica ordenada que incluye:

- versión del algoritmo;
- versión de balance;
- `movement_id`;
- `world_id`;
- ciudad de origen;
- ciudad objetivo;
- espías atacantes;
- espías defensores;
- `spy_modifier`;
- snapshot objetivo de recursos;
- snapshot objetivo de tropas;
- snapshot objetivo de edificios.

La semilla inicializa una instancia local de `random.Random`. El resolver no usa el generador global de Python para el resultado de misión.

Consecuencias:

- el mismo movimiento y el mismo preestado autoritativo reproducen la misma suerte y las mismas tiradas;
- un rollback/reintento sobre el mismo preestado no obtiene una nueva oportunidad aleatoria;
- otras tareas del proceso no alteran la secuencia RNG de una misión;
- el cliente no puede elegir la semilla;
- los informes pueden auditar después el resultado exacto mediante la seed persistida en su contenido.

El informe atacante conserva:

- `algorithm_version`;
- `balance_version`;
- `seed`;
- `luck`;
- `success_chance` y `success_roll`;
- `detection_chance` y `detection_roll`;
- `success`;
- `detected`;
- `attacker_identified`;
- `intel_level`;
- categorías `revealed`;
- únicamente los bloques de inteligencia que el nivel alcanzado autoriza.

## Privacidad de informes

BM-0065 separa deliberadamente el payload del atacante y el del defensor.

### Informe del atacante

El atacante recibe la auditoría de su propia misión y solo la inteligencia autorizada por el nivel alcanzado.

Reglas principales:

- una misión fallida no filtra recursos, tropas ni edificios;
- los espías defensores no deben filtrarse por una ruta lateral cuando no se obtuvo inteligencia de tropas;
- si se alcanzó nivel 2 o 3, la composición de tropas ya es información autorizada y puede representar correctamente cero espías defensores;
- los valores ocultos no se sustituyen por `0`, `undefined` ni `NaN` en la UI.

### Informe del defensor

El defensor recibe un informe **solo si `detected == true`**.

Ese informe no replica todo el payload privado del atacante. Incluye la información necesaria para el objetivo, como la probabilidad de detección y la fuerza defensiva de espionaje.

Si el atacante no fue identificado, su nombre se presenta como `Desconocido`.

Una misión no detectada no crea informe defensor, incluso cuando el espionaje tuvo éxito.

Esto evita convertir la mera existencia del informe en un canal lateral que revelaría toda misión secreta.

## Pérdidas y retorno

La regla v1.0 queda cerrada de forma simple y auditable:

- **éxito**: sobreviven todos los espías enviados;
- **fracaso**: se pierden todos los espías enviados.

La detección no añade una segunda tabla de bajas. Su efecto es informativo/defensivo y de posible identificación del atacante.

El worker de movimientos recibe `surviving_spies` desde el resolver y crea el retorno correspondiente una sola vez cuando hay supervivientes.

Por tanto:

- una misión exitosa produce retorno de los espías enviados;
- una misión fallida no puede devolver espías;
- un retry de un movimiento ya completado no puede crear un segundo retorno.

## Exactly-once, reintentos y concurrencia

BM-0065 reutiliza la transición de movimientos ya endurecida en hitos anteriores.

La garantía final es:

- el movimiento `spy` se resuelve una sola vez;
- al confirmar, pasa a `completed`;
- se crea exactamente un informe atacante;
- se crea cero o un informe defensor según detección;
- se crea como máximo un movimiento de retorno;
- una invocación posterior del worker no vuelve a tirar suerte ni duplica efectos.

Además de la prueba secuencial de retry del fixture G10, el gate PostgreSQL contiene una carrera real con **dos workers compitiendo por la misma misión espía**. Solo uno puede efectuar la transición autoritativa; el otro observa que la misión ya fue consumida.

Esto extiende a espionaje la misma disciplina de PD-010 aplicada a economía y combate.

## Permisos, mundo y protección

El lanzamiento `movement_type = "spy"` usa la matriz de permisos del router de movimientos, no un bypass específico.

Las pruebas HTTP cubren:

- objetivo PvP válido dentro del mismo mundo;
- cruce de mundo rechazado;
- ciudad propia rechazada;
- atacante bajo protección rechazado cuando corresponde;
- defensor bajo protección rechazado cuando corresponde.

El servicio vuelve a comprobar la frontera de mundo durante resolución para defensa en profundidad.

Una misión no puede espiar su misma ciudad ni resolver contra una ciudad de otro mundo aunque se construyera un movimiento inválido fuera del flujo HTTP normal.

## Fuente única de reglas y contrato público

`app/services/espionage.py` contiene el algoritmo BM-0065 y sus constantes deliberadamente separadas de BM-0064 para no cambiar semillas de combate ya versionadas.

`GET /economy/balance_preview` expone un bloque `espionage` con el contrato público correspondiente, incluyendo:

- `algorithm_version`;
- límites de suerte;
- límites de éxito;
- límites de detección;
- niveles de inteligencia;
- política de informe para misiones no detectadas.

Las pruebas de contrato verifican que ese preview no conserve el bloque legacy y que coincida con las reglas reales del servicio.

La wiki/ayuda fue alineada al mismo contrato: documenta suerte acotada, éxito/detección independientes, niveles 1/2/3, pérdidas/retorno y privacidad del defensor. Las pruebas impiden volver a introducir la explicación antigua de “éxito revela todo” o “el defensor siempre recibe informe”.

## UI de reportes

`ReportsView` interpreta el payload de espionaje autorizado por servidor.

La presentación final distingue:

- éxito o fracaso;
- misión detectada o no detectada;
- espías enviados;
- información defensiva conocida u oculta;
- recursos revelados;
- tropas reveladas;
- edificios revelados;
- panel de auditoría de espionaje.

El panel de auditoría muestra desde el payload persistido:

- versión del algoritmo;
- versión de balance;
- nivel de inteligencia;
- probabilidad de éxito;
- probabilidad de detección;
- suerte;
- seed SHA-256 completa.

Cuando un dato no fue autorizado por el servidor, la UI presenta `Oculto` en vez de inventar un cero. Cuando la inteligencia de tropas sí fue autorizada, una cantidad real de cero se muestra como cero.

G10 compara la seed visible contra la API y el contrato público para impedir que el panel sea una representación decorativa desconectada del resultado autoritativo.

## Evidencia funcional — Validation #436

HEAD funcional: `67cc2a879f016beb968cc0a57d4b210f1ff19997`  
Run: `32750304839`

### Backend

**SUCCESS**

- `224` pruebas recolectadas;
- `205 passed`;
- `19 skipped` por requerir el gate PostgreSQL dedicado;
- `4 warnings`;
- cobertura total `75%`;
- `espionage.py`: `93%` en la suite backend completa.

También quedaron verdes:

- compilación Python;
- Alembic `base -> 0009`;
- seed canónico idempotente;
- validación de migraciones/downgrade del workflow.

BM-0065 no agrega migración; el schema head continúa en `0009`.

### PostgreSQL concurrency

**SUCCESS**

- `19 passed`;
- `3 warnings`;
- `16.91s`.

La matriz incluye economía, onboarding, edificios, unidades, movimientos, mercado, expansión, simulación y tutorial. BM-0065 añade específicamente la carrera de dos workers sobre la misma misión de espionaje para demostrar exactly-once bajo bloqueo PostgreSQL real.

### Frontend

**SUCCESS**

- instalación reproducible;
- lint;
- build de producción.

### Dependency/security

**SUCCESS**

- auditoría Python;
- análisis estático de seguridad;
- auditoría frontend.

### G5 operations

**SUCCESS**

- deployment probes;
- backup;
- restore;
- recovery/load probes.

### Browser E2E

**SUCCESS**

Pasaron en secuencia:

- G2 sesión/realtime;
- G4 UX responsive, teclado e i18n;
- G6 expansión;
- G7 investigación;
- G8 catálogo/mantenimiento militar;
- G9 combate determinista por rondas;
- **G10 espionaje completo BM-0065**.

El mensaje final del gate fue:

`G10 BM-0065 complete espionage browser journey passed`

Fixture G10 del corte funcional:

`prepared-g10:5:1:15:16:seed=49a232a1d7482eaf12053f5c46b5a87f392f1d36cb6f534b20fff2ed2e9bf499:intel=3:detected=False:return=4`

G10 valida end-to-end que:

1. existe exactamente un informe BM-0065 del atacante;
2. `role = attacker`;
3. la misión fue exitosa;
4. la misión no fue detectada;
5. `intel_level = 3`;
6. `revealed = [resources, troops, buildings]`;
7. la seed es SHA-256 de 64 hexadecimales;
8. la suerte permanece dentro de `[-0.20, 0.20]`;
9. éxito y detección permanecen dentro de `[0.05, 0.95]`;
10. el snapshot autorizado contiene los recursos canónicos;
11. el snapshot de tropas contiene la inteligencia preparada;
12. el snapshot de edificios contiene la inteligencia preparada;
13. `/economy/balance_preview` coincide con la versión y límites del algoritmo;
14. el contrato declara que una misión no detectada no crea informe defensor;
15. existe exactamente una misión `spy` completada;
16. existe exactamente un retorno de espías;
17. el retorno contiene los seis espías enviados en el escenario exitoso;
18. `/reports` muestra recursos, tropas y edificios autorizados;
19. la seed del panel UI coincide exactamente con la seed del informe API;
20. la UI muestra nivel 3 y versiones correctas;
21. un cero defensivo autorizado se muestra como cero, no como información oculta;
22. la UI no contiene `undefined` ni `NaN`.

El fixture prepara y resuelve la misión mediante el worker real antes de arrancar el navegador y vuelve a invocar el worker para comprobar que el retry no duplica resolución, informe ni retorno.

### Imágenes Docker

**SUCCESS**

- backend image;
- frontend image.

## Hallazgos corregidos durante BM-0065

1. resolver legacy dependiente de aleatoriedad global y no auditable;
2. éxito y detección acoplados de forma insuficiente para modelar misiones secretas correctamente;
3. ausencia de una seed reproducible por misión;
4. ausencia de niveles explícitos de inteligencia;
5. riesgo de filtrar defensa del objetivo en informes fallidos o de bajo nivel;
6. creación histórica de informe defensor incluso cuando no correspondía por detección;
7. pruebas legacy que dependían de `random.random` global;
8. falta de contrato público de espionaje en `balance_preview`;
9. wiki que describía reglas antiguas incompatibles con el resolver final;
10. UI sin auditoría completa de seed/versión/probabilidades;
11. falta de una carrera PostgreSQL dedicada a la misma misión espía;
12. fixture Browser inicialmente dependiente del avance temporal de producción para el snapshot/seed;
13. expectativa E2E incorrecta que trataba un cero defensivo autorizado en nivel 3 como si debiera mostrarse `Oculto`.

Los dos últimos hallazgos fueron de evidencia/fixture: el primero se estabilizó fijando el reloj económico del objetivo para que el snapshot elegido no varíe por milisegundos durante preparación; el segundo se corrigió sin alterar las reglas del servidor.

## Rollout operativo

BM-0065 no cambia schema, pero sí cambia la semántica final de espionaje. Debe tratarse como cambio de reglas de mundo.

Para un mundo ya iniciado:

1. pausar temporalmente nuevas órdenes de espionaje;
2. pausar el worker de movimientos;
3. tomar snapshot/backup;
4. identificar movimientos `spy` todavía `ongoing`;
5. desplegar API, worker y frontend como conjunto compatible;
6. conservar schema `0009`;
7. verificar health/readiness;
8. ejecutar una misión canaria exitosa/no detectada y verificar ausencia de informe defensor;
9. ejecutar una misión canaria detectada y verificar el informe defensor y posible anonimato;
10. comprobar seed/versión/nivel en API y UI;
11. comprobar retorno/pérdidas según éxito;
12. reanudar worker;
13. observar errores, duplicados, tiempos de resolución e informes antes de ampliar tráfico.

No es seguro mezclar durante la misma ventana workers con algoritmo legacy y BM-0065: aunque el schema sea compatible, podrían interpretar de forma distinta un movimiento de espionaje pendiente.

## Rollback

No se requiere `alembic downgrade` para revertir únicamente BM-0065.

Rollback recomendado:

1. pausar nuevas misiones de espionaje y worker;
2. tomar snapshot/backup;
3. identificar movimientos `spy` todavía `ongoing`;
4. no reabrir tráfico hasta que todos los workers ejecuten la misma versión;
5. desplegar API, worker y frontend anteriores como conjunto;
6. no modificar ni rerresolver movimientos ya `completed`;
7. conservar informes BM-0065 confirmados como evidencia histórica;
8. verificar retornos existentes;
9. reanudar worker y luego tráfico.

Los informes ya confirmados contienen versión y seed suficientes para distinguirlos de resultados legacy. Un rollback de código nunca debe usar esa información para rerrollear una misión ya resuelta.

## Límite deliberado hacia el siguiente hito

BM-0065 cierra el espionaje completo v1.0 sobre el sistema de movimientos y reportes existente, sin reabrir las reglas de combate finalizadas en BM-0064.

El siguiente hito del plan maestro debe partir del `main` que resulte de este PR y respetar como contratos cerrados:

- catálogo/mantenimiento BM-0063;
- combate reproducible BM-0064;
- espionaje reproducible y privado BM-0065.

No debe duplicar sus fuentes de balance ni introducir rutas paralelas de resolución.

## Criterio de cierre

Validation #436 demuestra el corte funcional.

El PR #98 solo puede cerrarse cuando el **HEAD que contiene este documento** obtenga una Validation completa verde, incluyendo Backend, PostgreSQL, Frontend, seguridad, G5, Browser G2–G10 e imágenes Docker.

Solo ese SHA será válido para marcar el PR Ready y hacer squash merge.
