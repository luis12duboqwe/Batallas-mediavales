# G5 — soporte, severidades y apertura de beta cerrada

Estado: **PREPARADO / PENDIENTE DE CANAL REAL Y APROBACIÓN DEL PROPIETARIO**

## 1. Objetivo

La beta se abre por oleadas pequeñas para detectar defectos operativos antes de ampliar usuarios. No se incrementan cupos con defectos P0/P1 abiertos.

## 2. Canal de soporte

Antes de invitar usuarios externos debe existir un correo o sistema de tickets real y verificable. Ese contacto debe aparecer en los textos públicos de soporte y privacidad.

Cada solicitud debe registrar al menos:

- fecha/hora;
- categoría;
- severidad;
- estado;
- descripción sin contraseñas/tokens;
- release SHA afectada cuando sea técnica;
- resolución o workaround.

Nunca pedir al usuario contraseña, token JWT, llave privada o secreto de infraestructura.

## 3. Severidades

### P0 — crítico

Ejemplos:

- pérdida/corrupción de datos;
- fuga de datos o acceso entre cuentas/mundos;
- compromiso de credenciales;
- indisponibilidad general sin workaround;
- duplicación económica explotable a escala;
- backup/restore o rollback imposible durante incidente.

Acción: congelar despliegues y ampliación de beta inmediatamente. Mitigar/rollback primero y analizar después.

### P1 — alto

Ejemplos:

- autenticación o ciclo principal inutilizable para un grupo relevante;
- 5xx sostenidos;
- worker detenido provocando acumulación de colas;
- latencia sostenida muy por encima del presupuesto;
- mercado/movimientos con pérdida de consistencia sin explotación masiva.

Acción: no ampliar cupos; priorizar corrección y nueva Validation/staging antes de reanudar.

### P2 — medio

Función secundaria degradada o UX importante con workaround razonable.

### P3 — bajo

Cosmética, texto, mejora menor o deuda sin impacto relevante en integridad/seguridad.

## 4. Oleadas de beta

Secuencia recomendada:

1. **staging interno**: operadores/desarrolladores, sin usuarios externos;
2. **oleada A**: grupo muy pequeño y conocido;
3. **oleada B**: ampliar solo después de varios días sin P0/P1 y con métricas dentro del presupuesto;
4. **oleada C**: ampliar gradualmente, nunca por salto grande sin observar la oleada previa.

No se fija un número rígido de usuarios en el repositorio porque depende de capacidad real medida en staging.

## 5. Go / no-go por oleada

Para ampliar una oleada deben cumplirse simultáneamente:

- Validation reciente verde en la release activa;
- staging/release con smoke verde;
- p95 <= 750 ms en el probe acordado o presupuesto explícitamente revisado;
- error total <= 0.5% y cero 5xx en probes aceptados;
- backup reciente verificado;
- restore drill reciente;
- monitorización de staging activa;
- cero P0/P1 abiertos;
- no existe incidente de seguridad sin cerrar;
- soporte operativo disponible;
- aprobación explícita del propietario.

## 6. Gestión de incidentes de usuarios

Si un reporte puede implicar seguridad o pérdida de datos:

1. elevar inicialmente a P0/P1;
2. preservar logs/evidencia;
3. no pedir al usuario que reproduzca acciones destructivas;
4. correlacionar con release SHA;
5. aplicar rollback o congelación si el riesgo continúa;
6. comunicar al usuario solo hechos confirmados y medidas tomadas;
7. documentar causa raíz y prevención.

## 7. Cierre de un defecto P0/P1

No basta con que "parezca arreglado". Se requiere:

- causa identificada;
- cambio versionado;
- prueba que reproduce el fallo anterior cuando sea posible;
- Validation verde;
- deploy de staging;
- smoke/carga dentro de presupuesto;
- revisión de efectos secundarios;
- issue cerrado con evidencia.

## 8. Aprobación del propietario

G5 exige una decisión humana explícita. Una Validation verde o un despliegue correcto **no abre automáticamente la beta**.

La aprobación debe registrar al menos:

- release SHA aprobada;
- fecha;
- ambiente;
- oleada autorizada;
- confirmación de cero P0/P1;
- confirmación de soporte/privacidad/términos disponibles.

Hasta que exista esa aprobación, el estado correcto es `NO-GO` para usuarios externos.
