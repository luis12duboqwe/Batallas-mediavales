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


def _fmt_effect(effect: dict) -> str:
    effect_type = effect.get("type")
    if effect_type == "defense_bonus":
        return f"+{effect['per_level'] * 100:g}% defensa/nivel"
    if effect_type == "merchant_capacity":
        return f"+{effect['per_level']:g} capacidad comercial/nivel"
    if effect_type == "population_capacity":
        return f"+{effect['per_level']:g} población/nivel"
    if effect_type == "storage_capacity":
        return f"+{effect['per_level']:g} almacenamiento/nivel"
    if effect_type == "research_access":
        return f"Habilita investigación ({effect['queue_slots']} cola/ciudad)"
    if effect_type == "expansion_points":
        return f"+{effect['per_completion']} puntos de expansión/nivel completado"
    if effect_type == "world_victory":
        return f"Victoria al nivel {effect['target_level']}"
    return "Desbloquea requisitos de progresión"


def _build_troop_article() -> str:
    lines = [
        "# Tropas del reino",
        "",
        f"Versión de balance: `{balance.BALANCE_VERSION}`.",
        "",
        "Orden de recursos en costes: **Madera/Piedra/Hierro/Oro**.",
        "",
        "| Unidad | Ataque | Def. Inf. | Def. Cab. | Def. Asedio | Carga | Velocidad | Coste (M/P/H/O) | Tiempo (s) | Requisitos |",
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
            "- Las unidades investigables solo pueden entrenarse después de completar su investigación.",
        ]
    )
    return "\n".join(lines)


def _build_research_article() -> str:
    lines = [
        "# Investigación militar",
        "",
        f"Versión de balance: `{balance.BALANCE_VERSION}`.",
        "",
        "La Academia Militar es el edificio que habilita investigación. Una ciudad puede mantener una sola investigación activa.",
        "",
        "| Tecnología | Coste (M/P/H/O) | Tiempo (s) | Requisitos |",
        "| --- | --- | ---: | --- |",
    ]
    for unit_type in balance.UNIT_ORDER:
        definition = balance.UNIT_CATALOG[unit_type]
        if not definition["researchable"]:
            continue
        lines.append(
            f"| {balance.UNIT_DISPLAY_NAMES[unit_type]} "
            f"| {_fmt_cost(definition['research_cost'])} "
            f"| {int(definition['research_time_seconds'])} "
            f"| {_fmt_requirements(definition['research_requirements'])} |"
        )

    lines.extend(
        [
            "",
            "## Reglas de la cola",
            f"- Slots de investigación por ciudad: `{balance.RESEARCH_QUEUE_SLOTS_PER_CITY}`.",
            "- Los recursos se descuentan al iniciar la investigación.",
            "- La tecnología no se desbloquea hasta que el worker completa la cola.",
            f"- Una cancelación futura devuelve el {balance.QUEUE_REFUND_FACTOR * 100:.0f}% del pago registrado.",
            "- El pago exacto queda guardado en la cola; el reembolso no se recalcula con un balance posterior.",
        ]
    )
    return "\n".join(lines)


def _build_building_article() -> str:
    lines = [
        "# Edificios",
        "",
        f"Versión de balance: `{balance.BALANCE_VERSION}`.",
        "",
        "Orden de recursos en costes: **Madera/Piedra/Hierro/Oro**.",
        "",
        "| Edificio | Función | Coste base (M/P/H/O) | Máx. | Tiempo base (s) | Requisitos |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for building_type in balance.BUILDING_ORDER:
        effect = balance.get_building_effect_definition(building_type)
        lines.append(
            f"| {balance.BUILDING_DISPLAY_NAMES[building_type]} "
            f"| {balance.BUILDING_DESCRIPTIONS[building_type]} {_fmt_effect(effect)} "
            f"| {_fmt_cost(balance.BUILDING_COSTS[building_type])} "
            f"| {balance.BUILDING_MAX_LEVELS[building_type]} "
            f"| {balance.BUILDING_BASE_BUILD_TIME_SECONDS[building_type]} "
            f"| {_fmt_requirements(balance.BUILDING_PREREQUISITES.get(building_type, {}))} |"
        )

    lines.extend(
        [
            "",
            "## Fórmulas live",
            f"- Coste de nivel: `coste_base * ({balance.BUILDING_COST_GROWTH} ** (nivel - 1))`.",
            "- Tiempo de construcción: `tiempo_base_del_edificio * nivel_objetivo`.",
            f"- Al cancelar una cola futura se devuelve el {balance.QUEUE_REFUND_FACTOR * 100:.0f}% del pago registrado.",
            f"- Almacén: `{balance.STORAGE_BASE_CAPACITY:g} + {balance.STORAGE_PER_WAREHOUSE_LEVEL:g} * nivel_warehouse`.",
            f"- Hacienda: `population_max_base + {balance.POPULATION_PER_FARM_LEVEL} * nivel_farm` para ciudades.",
            "- Los campamentos conservan su capacidad base y no pueden construir Hacienda ni Academia.",
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
            "8. El botín está limitado por la capacidad de carga efectiva de las tropas supervivientes; los eventos pueden modificar esa capacidad mediante `loot_modifier`.",
            "9. La conquista de ciudades pertenecientes a otro jugador está deshabilitada en esta versión.",
        ]
    )


def _build_espionage_article() -> str:
    reveal_line = (
        "- Un espionaje exitoso revela recursos, tropas y niveles de edificios."
        if balance.SPY_REVEALS_BUILDINGS_ON_SUCCESS
        else "- Los edificios no se revelan en esta versión."
    )
    return "\n".join(
        [
            "# Mecánicas de espionaje",
            f"- Probabilidad base de éxito: `espias_atacantes / (espias_defensores + {balance.SPY_DEFENDER_OFFSET:g})`.",
            f"- Los eventos aplican `spy_modifier` (base {balance.EVENT_DEFAULT_MODIFIERS['spy_modifier']:g}).",
            f"- Si falla la misión hay {balance.SPY_UNKNOWN_ATTACKER_CHANCE * 100:.0f}% de probabilidad de que el atacante aparezca como 'Desconocido'.",
            reveal_line,
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
            "- El tiempo de edificio usa su tiempo base canónico multiplicado por el nivel objetivo.",
            "- Coste y tiempo de tropas provienen del catálogo de unidades y escalan linealmente con la cantidad.",
            "- Coste y tiempo de investigación provienen del mismo catálogo server-authoritative.",
            f"- Capacidad de almacén: `{balance.STORAGE_BASE_CAPACITY:g} + {balance.STORAGE_PER_WAREHOUSE_LEVEL:g} * nivel_warehouse`.",
            f"- Capacidad de población de ciudad: `base_persistida + {balance.POPULATION_PER_FARM_LEVEL} * nivel_farm`.",
            f"- Recuperación de lealtad: `{balance.LOYALTY_RECOVERY_PER_HOUR:g}` puntos por hora hasta {balance.LOYALTY_MAX:g}.",
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
            "1. Usa la Casa Central (`town_hall`) para desbloquear requisitos de progreso.",
            "2. Mejora el Gran Depósito (`warehouse`) cuando la capacidad empiece a limitar tus recursos.",
            "3. Construye Barracas (`barracks`) para entrenar la infantería inicial.",
            "4. Construye la Academia Militar (`academy`) para investigar nuevas unidades; las investigaciones tardan tiempo real y solo se desbloquean al completar la cola.",
            "5. Mejora la Hacienda (`farm`) si necesitas aumentar la capacidad de población.",
            "6. Usa espionaje antes de una hostilidad y respeta la protección de novatos.",
            "7. La Muralla (`wall`) mejora la defensa y puede recibir daño de asedio.",
            "8. El mercado permite comercio y transporte dentro del mismo mundo.",
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
            "title": "Investigación militar",
            "category": schemas.WIKI_CATEGORIES[1],
            "content_markdown": _build_research_article(),
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
