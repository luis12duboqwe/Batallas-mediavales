# QA adversarial independiente — comunidad y ciclo de mundos

## Alcance y estado

QA anticipado para BM-0070–0074 y G16–G18; **no es certificación G7 ni declara G7 cerrado**. La revisión se limita a pruebas nuevas `tests/test_parallel_g7_adversarial*.py` y este informe. No se modificó código de aplicación, pruebas existentes, workflows ni configuración.

El árbol revisado tenía `b265eb02b754090b84f477d78bba61bdd7cfaf4d`, sobre la base indicada `86adbd83dedc9a3e4c2d89b3adc247b72184d158`. Se compararon las pruebas y evidencias existentes de comunidad/diplomacia, ciclo de mundos, administración/soporte/moderación y anti-cheat. Se añadieron reproducciones enfocadas en rutas que no estaban cubiertas por esos casos.

## Hallazgos reproducidos

Los cuatro hallazgos siguientes son P2: el árbol actual permite una mutación social durante pausa o descarta un mensaje privado válido al rechazar otro mensaje. Los tests expresan el contrato esperado y fallan contra la implementación actual. No se corrigió código fuera del scope solicitado.

| Grupo | Reproducción y resultado | Archivo responsable |
| --- | --- | --- |
| Ciclo de mundos / diplomacia | Crear y aceptar una relación `ally`, pausar el mundo y cancelar la relación. `cancel_relation()` la elimina en vez de rechazar la mutación; la prueba espera HTTP 409 y que la relación se conserve. | `batalla_medieval_backend/app/services/diplomacy.py`, `cancel_relation()` |
| Ciclo de mundos / invitaciones | Con el mundo pausado, pedir una invitación válida desde una alianza. Se crea una invitación pendiente; la prueba espera HTTP 409 y ninguna fila nueva. | `batalla_medieval_backend/app/services/alliance.py`, `invite_member()` |
| Ciclo de mundos / mensajes | Con el mundo pausado, un líder envía un mensaje masivo a su alianza. Se persisten mensajes privados; la prueba espera HTTP 409 y ninguna fila nueva. | `batalla_medieval_backend/app/services/alliance.py`, `send_mass_message()` |
| Integridad de mensajería | Llenar la bandeja del receptor hasta su límite y enviar un asunto compuesto solo por espacios. Se confirma la eliminación del mensaje más antiguo antes de que la normalización rechace el nuevo envío con HTTP 400. La prueba espera que el mensaje previo y el tamaño de la bandeja se conserven. | `batalla_medieval_backend/app/routers/message.py`, `send_message()` |

Las tres primeras reproducciones incumplen la política BM-0072 de lectura histórica sin mutaciones sociales fuera de `open`. La cuarta es pérdida de datos: la expulsión del mensaje antiguo se confirma antes de validar asunto y contenido.

## Carrera exploratoria, pendiente de PostgreSQL

Se añadió una prueba PostgreSQL para dos invitaciones idénticas que pasan simultáneamente la comprobación previa. La tabla tiene una restricción única por alianza/usuario, pero la operación de servicio hace lectura y creación separadas. La prueba exige un único éxito y un conflicto de dominio para la otra solicitud. **No se concluye si esta carrera se reproduce**: el entorno local usa SQLite y el caso quedó omitido; debe ejecutarse en el gate PostgreSQL dedicado.

La suite PostgreSQL existente para invitaciones competidoras valida que el usuario no acabe con membresía en dos alianzas, no la carrera de dos invitaciones iguales. Los contratos de concurrencia de BM-0070/0072/0073/0074 que dependen de locks tampoco se consideran verificados por esta ejecución SQLite.

No se confirmó un hallazgo nuevo en los flujos de rangos, soporte, moderación o anti-cheat; se mantienen fuera de los hallazgos en vez de inferir fallos a partir de cobertura ausente.

## Pruebas ejecutadas

Comando: `/tmp/g7-adversarial-venv/bin/python -m pytest -q tests/test_parallel_g7_adversarial_community.py`, en un entorno temporal con las dependencias ya declaradas por el backend.

Resultado en SQLite: **4 fallidas (reproducciones esperadas), 1 omitida (PostgreSQL), 4 warnings**. La prueba omitida requiere el dialecto PostgreSQL para hacer válida la carrera; ninguna afirmación de concurrencia se deriva de SQLite.

Las cuatro fallidas son los hallazgos listados arriba, no fallos ajenos observados en la suite existente. Se ejecutó `git diff --check` sin errores. No se ejecutó la suite completa ni gates de navegador.

## Conclusión

Los casos identifican trabajo de corrección fuera del alcance permitido para este cambio de QA. El estado permanece como **hallazgos de QA pendientes de triage/corrección y validación**; no se certifica G7, no se recomienda merge y no se declara cerrado BM-0070–0074.
