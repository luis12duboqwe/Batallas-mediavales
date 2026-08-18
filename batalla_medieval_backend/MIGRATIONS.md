# Migraciones de base de datos

Alembic es la única vía autorizada para crear o cambiar el esquema. La
aplicación no ejecuta `Base.metadata.create_all()` al arrancar.

## Base nueva

Desde `batalla_medieval_backend`:

```bash
export DATABASE_URL='postgresql+psycopg://usuario:clave@host/base'
alembic -c alembic.ini upgrade head
```

En Docker Compose, el servicio `migrate` completa este paso antes de que el
backend pueda arrancar.

## Base heredada del prototipo

No se debe aplicar ni marcar una revisión sin respaldo. Para adoptar una base
que fue creada por `create_all()`:

1. crear y verificar un backup restaurable;
2. ejecutar `alembic -c alembic.ini check` contra una copia;
3. resolver cualquier diferencia de esquema;
4. marcar la copia con `alembic -c alembic.ini stamp 0001`;
5. ejecutar `alembic -c alembic.ini upgrade head`;
6. repetir el procedimiento en el entorno objetivo solo después de validar la
   copia.

## Nueva revisión

```bash
alembic -c alembic.ini revision --autogenerate -m "descripcion breve"
alembic -c alembic.ini upgrade head
alembic -c alembic.ini check
```

Cada revisión debe incluir una ruta de `downgrade`, pruebas con una base nueva
y una prueba de actualización con datos representativos desde la revisión
anterior.

## Reversión

```bash
alembic -c alembic.ini downgrade -1
```

El rollback de producción siempre requiere backup reciente y el procedimiento
específico de la revisión. Una reversión destructiva no se ejecuta sin una
decisión operativa explícita.
