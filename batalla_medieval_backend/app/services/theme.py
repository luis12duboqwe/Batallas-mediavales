from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from .. import models, schemas


def list_themes(db: Session) -> List[models.Theme]:
    return db.query(models.Theme).all()


def get_theme(db: Session, theme_id: int) -> Optional[models.Theme]:
    return db.query(models.Theme).filter(models.Theme.id == theme_id).first()


def create_theme(db: Session, payload: schemas.ThemeCreate) -> models.Theme:
    theme = models.Theme(**payload.dict())
    db.add(theme)
    db.commit()
    db.refresh(theme)
    return theme


def update_theme(db: Session, theme_id: int, payload: schemas.ThemeUpdate) -> models.Theme:
    theme = get_theme(db, theme_id)
    if not theme:
        raise ValueError("Theme not found")
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(theme, key, value)
    db.commit()
    db.refresh(theme)
    return theme


def delete_theme(db: Session, theme_id: int) -> None:
    theme = get_theme(db, theme_id)
    if not theme:
        raise ValueError("Theme not found")
    db.delete(theme)
    db.commit()


def grant_theme_to_user(db: Session, payload: schemas.ThemeOwnershipCreate) -> models.ThemeOwnership:
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise ValueError("User not found")
    theme = get_theme(db, payload.theme_id)
    if not theme:
        raise ValueError("Theme not found")

    existing = (
        db.query(models.ThemeOwnership)
        .filter(
            models.ThemeOwnership.user_id == payload.user_id,
            models.ThemeOwnership.theme_id == payload.theme_id,
        )
        .first()
    )
    if existing:
        return existing

    ownership = models.ThemeOwnership(**payload.dict())
    db.add(ownership)
    db.commit()
    db.refresh(ownership)
    return ownership


def _build_css_variables(theme: models.Theme) -> Dict[str, str]:
    return {
        "--primary-color": theme.primary_color,
        "--secondary-color": theme.secondary_color,
        "--background-image": f"url({theme.background_url})",
    }


def _build_assets(theme: models.Theme) -> Dict[str, str]:
    return {
        "background_url": theme.background_url,
        "icon_pack_url": theme.icon_pack_url,
    }


def _require_ownership(db: Session, user: models.User, theme: models.Theme) -> None:
    owned = (
        db.query(models.ThemeOwnership)
        .filter(
            models.ThemeOwnership.user_id == user.id,
            models.ThemeOwnership.theme_id == theme.id,
        )
        .first()
    )
    if not owned:
        raise ValueError("Theme is locked for this user. Unlock it before selecting.")


def select_theme(db: Session, user: models.User, theme_id: int) -> Dict[str, object]:
    theme = get_theme(db, theme_id)
    if not theme:
        raise ValueError("Theme not found")

    _require_ownership(db, user, theme)

    user.current_theme = theme
    db.commit()
    db.refresh(user)

    return serialize_theme(theme)


def get_current_theme(db: Session, user: models.User) -> Dict[str, object]:
    if not user.current_theme:
        raise ValueError("No theme selected")
    return serialize_theme(user.current_theme)


def serialize_theme(theme: models.Theme) -> Dict[str, object]:
    return {
        "id": theme.id,
        "name": theme.name,
        "primary_color": theme.primary_color,
        "secondary_color": theme.secondary_color,
        "background_url": theme.background_url,
        "icon_pack_url": theme.icon_pack_url,
        "locked": theme.locked,
        "css_variables": _build_css_variables(theme),
        "assets": _build_assets(theme),
    }
