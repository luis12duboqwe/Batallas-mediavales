import threading
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import balance, event as event_service
from ..utils import utc_now

router = APIRouter(tags=["wiki"])

_seed_lock = threading.Lock()
_builtin_seeded = False


def require_admin(current_user: models.User = Depends(get_current_user)):
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


def _fmt_cost(cost: dict) -> str:
    return "/".join(
        str(int(cost.get(resource, 0))) for resource in balance.RESOURCE_FIELDS
    )


def _fmt_requirements(requirements: dict) -> str:
    if not requirements:
        return "—"
    return ", ".join(f"{name} {level}" for name, level in requirements.items())


def _build_troop_article() -> str:
    lines = [
        "# Tropas del reino",
        "",
        f"Versión de balance: `{balance.BALANCE_VERSION}`.",
        "",
        "| Unidad | Ataque | Def. Inf. | Def. Cab. | Def. Asedio | Carga | Velocidad | Coste (M/A/H) | Tiempo (s) | Requisitos |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for unit_type in balance.UNIT_ORDER:
        definition = balance.UNIT_CATALOG[unit_type]
        stats = balance.UNIT_COMBAT_STATS[unit_type]
        lines.append(
            f"| {balance.UNIT_DISPLAY_NAMES[unit_type]} "
            f"| {int(stats['attack'])} "
            f"| {int(stats['def_inf'])} "
            f"| {int(stats['def_cav'])} "
            f"| {int(stats['def_siege'])} "
            f"| {int(stats['carry'])} "
            f"| {balance.UNIT_SPEED[unit_type]:g} "
            f"| {_fmt_cost(definition['training_cost'])} "
            f"| {int(definition['training_time_seconds'])} "
            f"| {_fmt_requirements(definition['training_requirements'])} |"
        )

    lines.extend(
        [
            "",
            "## Reglas de entrenamiento",
            "- El coste total es el coste por unidad multiplicado por la cantidad.",
            "- El tiempo total es el tiempo por unidad multiplicado por la cantidad y por el modificador activo del mundo.",
            "- El nivel del edificio sirve como requisito; no aplica una fórmula de tiempo paralela.",
            "- Investigación y entrenamiento usan el mismo catálogo mostrado arriba.",
        ]
    )
    return "\n".join(lines)


def _build_building_article() -> str:
    descriptions = {
        "town_hall": "Centro de progreso de la ciudad y requisito para estructuras avanzadas.",
        "barracks": "Desbloquea y entrena infantería.",
        "stable": "Desbloquea caballería y espionaje.",
        "wall": "Aumenta la defensa de la ciudad.",
        "market": "Habilita capacidad comercial y transportes.",
        "farm": "Estructura económica básica de la ciudad.",
        "warehouse": "Aumenta el almacenamiento máximo de recursos.",
        "smithy": "Requisito para unidades militares avanzadas.",
        "workshop": "Desbloquea maquinaria de asedio.",
        "world_wonder": "Objetivo de mundo de alto nivel.",
    }
    lines = [
        "# Edificios",
        "",
        f"Versión de balance: `{balance.BALANCE_VERSION}`.",
        "",
        "| Edificio | Función | Coste base (M/A/H) | Requisitos |",
        "| --- | --- | --- | --- |",
    ]
    for building_type in balance.BUILDING_ORDER:
        costs = balance.BUILDING_COSTS[building_type]
        lines.append(
            f"| {balance.BUILDING_DISPLAY_NAMES[building_type]} "
            f"| {descriptions.get(building_type, 'Estructura del reino.')} "
            f"| {_fmt_cost(costs)} "
            f"| {_fmt_requirements(balance.BUILDING_PREREQUISITES.get(building_type, {}))} |"
        )

    lines.extend(
        [
            "",
            "## Fórmulas live",
            f"- Coste de nivel: `coste_base * ({balance.BUILDING_COST_GROWTH} ** (nivel - 1))`.",
            f"- Tiempo de construcción: `{balance.BASE_BUILD_TIME_SECONDS} * nivel` segundos antes de modificadores aplicables.",
            f"- Al cancelar una cola futura se devuelve el {balance.QUEUE_REFUND_FACTOR * 100:.0f}% del pago registrado.",
            f"- Almacén: `{balance.STORAGE_BASE_CAPACITY:g} + {balance.STORAGE_PER_WAREHOUSE_LEVEL:g} * nivel_warehouse`.",
        ]
    )
    return "\n".join(lines)


def _build_combat_article() -> str:
    return "\n".join(
        [
            "# Cómo funciona el combate",
            "",
            f"Versión de balance: `{balance.BALANCE_VERSION}`.",
            "",
            "1. Se separa el ataque por infantería, caballería y asedio.",
            "2. La defensa pondera las defensas específicas contra cada tipo.",
            f"3. La muralla `wall` añade {balance.WALL_BONUS_PER_LEVEL * 100:.0f}% de defensa por nivel.",
            f"4. La moral usa `sqrt(defensa/ataque)` limitada entre `{balance.MORALE_MIN}` y `{balance.MORALE_MAX}`.",
            f"5. La suerte del ataque está limitada entre `{balance.LUCK_MIN:+.0%}` y `{balance.LUCK_MAX:+.0%}`.",
            "6. Las bajas se obtienen comparando ataque efectivo y defensa ponderada.",
            "7. Arietes y catapultas supervivientes pueden reducir niveles de edificios.",
            "8. El botín está limitado por la capacidad de carga de las tropas supervivientes; no existe un porcentaje fijo alternativo.",
            "9. La conquista de ciudades pertenecientes a otro jugador está deshabilitada en esta versión.",
        ]
    )


def _build_espionage_article() -> str:
    return "\n".join(
        [
            "# Mecánicas de espionaje",
            "- Probabilidad de éxito: `espias_atacantes / (espias_defensores + 1)`.",
            "- Los eventos afectan con el modificador `spy_modifier` (por defecto 1.0).",
            "- Si falla la misión hay 10% de probabilidad de que el atacante aparezca como 'Desconocido'.",
            "- Con ≥5 espías exitosos también se listan niveles de edificios además de recursos y tropas.",
            "- Los informes se guardan para atacante y defensor y activan notificaciones.",
        ]
    )


def _build_conquest_article() -> str:
    return "\n".join(
        [
            "# Conquista y lealtad",
            "- La conquista PvP está deshabilitada: una ciudad perteneciente a otro jugador nunca cambia de dueño por ataque.",
            "- Los nobles solo pueden reducir lealtad para la conquista PvE de ciudades bárbaras sin dueño.",
            f"- Cada noble bárbaro exitoso reduce entre {balance.BARBARIAN_LOYALTY_DROP_MIN} y {balance.BARBARIAN_LOYALTY_DROP_MAX} puntos de lealtad.",
            f"- Al conquistar una ciudad bárbara su lealtad queda en {balance.BARBARIAN_CONQUEST_RESET_LOYALTY:g}.",
            "- Fundar y expandir ciudades se gestiona por sus flujos server-authoritative; no equivale a conquistar ciudades PvP.",
        ]
    )


def _build_economy_article() -> str:
    rates = ", ".join(
        f"{resource}={rate:g}/h"
        for resource, rate in balance.PRODUCTION_RATES_PER_HOUR.items()
    )
    return "\n".join(
        [
            "# Economía y fórmulas de progresión",
            f"Versión de balance: `{balance.BALANCE_VERSION}`.",
            f"- Producción base: `{rates}` antes de mundo, oasis y eventos.",
            f"- Coste de edificios: `coste_base * ({balance.BUILDING_COST_GROWTH} ** (nivel - 1))`.",
            "- Coste y tiempo de tropas provienen del catálogo de unidades y escalan linealmente con la cantidad.",
            f"- Capacidad de almacén: `{balance.STORAGE_BASE_CAPACITY:g} + {balance.STORAGE_PER_WAREHOUSE_LEVEL:g} * nivel_warehouse`.",
            f"- Recuperación de lealtad: `{balance.LOYALTY_RECOVERY_PER_HOUR:g}` puntos por hora hasta 100.",
        ]
    )


def _build_events_article() -> str:
    parts = ["# Eventos del mundo", "", "Modificadores base:"]
    for key, value in event_service.DEFAULT_MODIFIERS.items():
        parts.append(f"- `{key}`: {value}")
    parts.append("\nEventos prediseñados:")
    for key, (name, description, modifiers) in event_service.EVENT_TEMPLATES.items():
        mod_text = ", ".join(f"{name_}={value}" for name_, value in modifiers.items())
        parts.append(f"- **{name}** (`{key}`): {description} ({mod_text})")
    return "\n".join(parts)


def _build_beginner_article() -> str:
    return "\n".join(
        [
            "# Guía para principiantes",
            "1. Usa el Ayuntamiento (`town_hall`) para desbloquear requisitos de progreso.",
            "2. Mejora el Almacén (`warehouse`) cuando la capacidad empiece a limitar tus recursos.",
            "3. Construye Barracas (`barracks`) para entrenar la infantería inicial.",
            "4. Investiga unidades desde el catálogo que muestra el juego; los costes visibles son los que cobra el servidor.",
            "5. Usa espionaje antes de una hostilidad y respeta la protección de novatos.",
            "6. La Muralla (`wall`) mejora la defensa y puede recibir daño de asedio.",
            "7. El mercado permite comercio y transporte dentro del mismo mundo.",
        ]
    )


def _builtin_articles() -> List[dict]:
    return [
        {
            "title": "Tropas y estadísticas base",
            "category": schemas.WIKI_CATEGORIES[1],
            "content_markdown": _build_troop_article(),
        },
        {
            "title": "Edificios y progresión",
            "category": schemas.WIKI_CATEGORIES[0],
            "content_markdown": _build_building_article(),
        },
        {
            "title": "Fórmulas de combate",
            "category": schemas.WIKI_CATEGORIES[2],
            "content_markdown": _build_combat_article(),
        },
        {
            "title": "Economía y producción",
            "category": "economy",
            "content_markdown": _build_economy_article(),
        },
        {
            "title": "Espionaje y reportes",
            "category": schemas.WIKI_CATEGORIES[4],
            "content_markdown": _build_espionage_article(),
        },
        {
            "title": "Conquista y lealtad",
            "category": "combat",
            "content_markdown": _build_conquest_article(),
        },
        {
            "title": "Eventos del mundo",
            "category": "events",
            "content_markdown": _build_events_article(),
        },
        {
            "title": "Guía para nuevos jugadores",
            "category": schemas.WIKI_CATEGORIES[6],
            "content_markdown": _build_beginner_article(),
        },
    ]


def ensure_builtin_articles(db: Session):
    """Create or refresh server-owned help so deployed DBs cannot stay stale."""

    global _builtin_seeded
    if _builtin_seeded:
        return
    with _seed_lock:
        if _builtin_seeded:
            return
        changed = False
        for article in _builtin_articles():
            existing = (
                db.query(models.WikiArticle)
                .filter(models.WikiArticle.title == article["title"])
                .first()
            )
            if existing:
                if (
                    existing.category != article["category"]
                    or existing.content_markdown != article["content_markdown"]
                ):
                    existing.category = article["category"]
                    existing.content_markdown = article["content_markdown"]
                    existing.updated_at = utc_now()
                    db.add(existing)
                    changed = True
                continue
            db.add(
                models.WikiArticle(
                    title=article["title"],
                    category=article["category"],
                    content_markdown=article["content_markdown"],
                )
            )
            changed = True
        if changed:
            db.commit()
        _builtin_seeded = True


@router.get("/categories", response_model=List[str])
def list_categories() -> List[str]:
    return list(schemas.WIKI_CATEGORIES)


@router.get("/article/{article_id}", response_model=schemas.WikiArticleRead)
def get_article(article_id: int, db: Session = Depends(get_db)):
    ensure_builtin_articles(db)
    article = (
        db.query(models.WikiArticle)
        .filter(models.WikiArticle.id == article_id)
        .first()
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.get("/search", response_model=List[schemas.WikiArticleRead])
def search_articles(
    q: str | None = Query(default=None, description="Texto a buscar en título o contenido"),
    db: Session = Depends(get_db),
):
    ensure_builtin_articles(db)
    query = db.query(models.WikiArticle)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                models.WikiArticle.title.ilike(pattern),
                models.WikiArticle.content_markdown.ilike(pattern),
            )
        )
    return query.order_by(models.WikiArticle.updated_at.desc()).all()


@router.post("/create", response_model=schemas.WikiArticleRead)
def create_article(
    payload: schemas.WikiArticleCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    ensure_builtin_articles(db)
    article = models.WikiArticle(**payload.model_dump())
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


@router.patch("/edit/{article_id}", response_model=schemas.WikiArticleRead)
def edit_article(
    article_id: int,
    payload: schemas.WikiArticleUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    ensure_builtin_articles(db)
    article = (
        db.query(models.WikiArticle)
        .filter(models.WikiArticle.id == article_id)
        .first()
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(article, field, value)
    article.updated_at = utc_now()
    db.add(article)
    db.commit()
    db.refresh(article)
    return article
