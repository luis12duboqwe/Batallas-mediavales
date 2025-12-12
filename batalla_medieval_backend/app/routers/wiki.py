from datetime import datetime
import threading
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import combat, economy, conquest, event as event_service
from ..utils import utc_now

router = APIRouter(tags=["wiki"])

_seed_lock = threading.Lock()
_builtin_seeded = False


def require_admin(current_user: models.User = Depends(get_current_user)):
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


def _build_troop_article() -> str:
    stat_key_map = {
        "Lancero Común": "lancero_comun",
        "Soldado de Acero": "soldado_de_acero",
        "Arquero Real": "arquero_real",
        "Jinete Explorador": "jinete_explorador",
        "Caballero Imperial": "caballero_imperial",
        "Infiltrador": "infiltrador",
        "Quebramuros": "quebramuros",
        "Tormenta de Piedra": "tormenta_de_piedra",
    }

    lines = [
        "# Tropas del reino",
        "",
        "| Unidad | Ataque | Def. Infantería | Def. Caballería | Def. Asedio | Población | Coste (M/A/H) | Tiempo base (s) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for troop_name, costs in economy.BASE_TROOP_COSTS.items():
        stat_key = stat_key_map.get(troop_name)
        stats = combat.UNIT_STATS.get(stat_key, {})
        training_time = economy.BASE_TRAINING_TIMES.get(troop_name, 0)
        line = (
            f"| {troop_name} "
            f"| {int(stats.get('attack', 0))} "
            f"| {int(stats.get('def_inf', 0))} "
            f"| {int(stats.get('def_cav', 0))} "
            f"| {int(stats.get('def_siege', 0))} "
            f"| {int(costs.get('population', 0))} "
            f"| {int(costs.get('wood', 0))}/{int(costs.get('clay', 0))}/{int(costs.get('iron', 0))} "
            f"| {int(training_time)} |"
        )
        lines.append(line)

    lines.extend(
        [
            "",
            "## Fórmulas rápidas",
            "- El coste total de entrenamiento escala linealmente con la cantidad solicitada.",
            "- El tiempo de entrenamiento se calcula como `base_time * (1.18 ** (nivel_cuartel - 1))`.",
            "- Las unidades de asedio infligen daño a murallas si sobreviven y no quedan defensores.",
        ]
    )
    return "\n".join(lines)


def _build_building_article() -> str:
    descriptions = {
        "Casa Central": "Desbloquea construcción y mejora el resto de edificios.",
        "Aserradero": "Produce madera de manera pasiva.",
        "Cantera de Ladrillo": "Genera arcilla para tus construcciones.",
        "Mina Profunda": "Produce hierro utilizado en unidades y mejoras.",
        "Hacienda": "Aumenta la capacidad de población disponible.",
        "Gran Depósito": "Incrementa el almacenamiento máximo de recursos.",
        "Barracas": "Entrena infantería y desbloquea tropas básicas.",
        "Establos Imperiales": "Permite reclutar caballería y unidades rápidas.",
        "Forja Bélica": "Mejora el equipamiento y desbloquea maquinaria de asedio.",
        "Muralla de Guardia": "Otorga bonificación defensiva del 5% por nivel.",
        "Plaza Comercial": "Gestiona intercambios y caravanas.",
        "Comandancia Militar": "Coordina ataques conjuntos y despliegues avanzados.",
    }
    lines = ["# Edificios", "", "| Edificio | Función | Coste base (M/A/H) |", "| --- | --- | --- |"]
    for building, costs in economy.BASE_BUILDING_COSTS.items():
        description = descriptions.get(building, "Estructura del reino.")
        lines.append(
            f"| {building} | {description} | {int(costs.get('wood', 0))}/"
            f"{int(costs.get('clay', 0))}/{int(costs.get('iron', 0))} |"
        )

    lines.extend(
        [
            "",
            "## Fórmula de mejora",
            "El coste de cada nivel es `coste_base * (1.26 ** (nivel - 1))`.",
            "La capacidad del Gran Depósito sigue `5000 * (1.32 ** (nivel - 1))`.",
            "La población máxima de la Hacienda es `50 * (1.22 ** (nivel - 1))`.",
        ]
    )
    return "\n".join(lines)


def _build_combat_article() -> str:
    lines = [
        "# Cómo funciona el combate",
        "",
        "1. Se separa el ataque por tipo de tropa (infantería, caballería, asedio).",
        "2. La defensa se calcula sumando las defensas específicas de cada unidad por tipo.",
        "3. La muralla añade un `+5%` de defensa por nivel (`1 + nivel * 0.05`).",
        "4. Se aplica moral: `sqrt(defensa/ataque)` limitado entre `0.3` y `1.5`.",
        "5. Se agrega suerte aleatoria entre `-25%` y `+25%` al ataque efectivo.",
        "6. Se obtienen ratios de bajas comparando ataque efectivo vs defensa ponderada.",
        "7. Si el defensor cae y hay asedio, la muralla puede perder niveles. ",
        "8. Si el defensor cae, el atacante saquea un 30% de cada recurso, modificado por eventos.",
        "",
        "Las fórmulas se basan en `app/services/combat.py` y respetan modificadores de eventos globales.",
    ]
    return "\n".join(lines)


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
            "- Solo los ataques con nobles (`noble` en el ejército) pueden reducir lealtad.",
            f"- Cada victoria con noble reduce la lealtad en {conquest.LOYALTY_DROP_PER_SUCCESS:.0f} puntos.",
            "- Si la lealtad llega a 0 la ciudad cambia de dueño y vuelve a 100 de lealtad.",
            "- La fuerza se calcula como la suma de unidades supervivientes tras el combate inicial.",
            "- Fundar ciudades nuevas cuesta 800 de cada recurso y requiere un espacio libre en el mapa.",
        ]
    )


def _build_economy_article() -> str:
    return "\n".join(
        [
            "# Economía y fórmulas de progresión",
            "- Coste de edificios: `coste_base * (1.26 ** (nivel - 1))`.",
            "- Coste de tropas: el coste base de cada recurso se multiplica por la cantidad reclutada.",
            "- Tiempo de entrenamiento: `tiempo_base * (1.18 ** (nivel_cuartel - 1))`.",
            f"- Capacidad de almacén: `{economy.STORAGE_BASE_CAPACITY} * ( {economy.STORAGE_GROWTH} ** (nivel - 1))`.",
            f"- Población máxima: `{economy.POPULATION_BASE} * ( {economy.POPULATION_GROWTH} ** (nivel - 1))`.",
            "- Población usada por tropas: suma de `population` definido en cada unidad multiplicado por su cantidad.",
        ]
    )


def _build_events_article() -> str:
    parts = ["# Eventos del mundo", "", "Modificadores base:"]
    for key, value in event_service.DEFAULT_MODIFIERS.items():
        parts.append(f"- `{key}`: {value}")
    parts.append("\nEventos prediseñados:")
    for key, (name, description, modifiers) in event_service.EVENT_TEMPLATES.items():
        mod_text = ", ".join(f"{m}={v}" for m, v in modifiers.items())
        parts.append(f"- **{name}** (`{key}`): {description} ({mod_text})")
    return "\n".join(parts)


def _build_beginner_article() -> str:
    return "\n".join(
        [
            "# Guía para principiantes",
            "1. Construye Hacienda y Gran Depósito temprano para sostener tropas y recursos.",
            "2. Prioriza Aserradero, Cantera y Mina Profunda para acelerar producción.",
            "3. Desbloquea Barracas y entrena lanceros como defensa básica.",
            "4. Usa espías antes de atacar para evitar sorpresas.",
            "5. Sube la Muralla de Guardia para obtener bonificaciones defensivas tempranas.",
            "6. Aprovecha eventos activos (ver sección de eventos) para optimizar producción y ataques.",
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
    global _builtin_seeded
    if _builtin_seeded:
        return
    with _seed_lock:
        if _builtin_seeded:
            return
        for article in _builtin_articles():
            existing = db.query(models.WikiArticle).filter(models.WikiArticle.title == article["title"]).first()
            if existing:
                continue
            db_article = models.WikiArticle(
                title=article["title"],
                category=article["category"],
                content_markdown=article["content_markdown"],
            )
            db.add(db_article)
        db.commit()
        _builtin_seeded = True


@router.get("/categories", response_model=List[str])
def list_categories() -> List[str]:
    return list(schemas.WIKI_CATEGORIES)


@router.get("/article/{article_id}", response_model=schemas.WikiArticleRead)
def get_article(article_id: int, db: Session = Depends(get_db)):
    ensure_builtin_articles(db)
    article = db.query(models.WikiArticle).filter(models.WikiArticle.id == article_id).first()
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
    article = models.WikiArticle(**payload.dict())
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
    article = db.query(models.WikiArticle).filter(models.WikiArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    for field, value in payload.dict(exclude_unset=True).items():
        setattr(article, field, value)
    article.updated_at = utc_now()
    db.add(article)
    db.commit()
    db.refresh(article)
    return article
