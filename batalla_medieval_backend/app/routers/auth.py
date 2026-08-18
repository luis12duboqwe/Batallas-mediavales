from datetime import timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import PROTECTED_ENVIRONMENTS, get_settings
from ..database import get_db
from ..services import anticheat, emailer
from ..utils import utc_now

router = APIRouter(tags=["auth"])

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
settings = get_settings()

VERIFICATION_TOKEN_TTL = timedelta(hours=24)
PASSWORD_RESET_TOKEN_TTL = timedelta(minutes=15)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a signed JWT with an explicit purpose."""

    to_encode = data.copy()
    to_encode.setdefault("type", "access")
    expire = utc_now() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_typed_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.exceptions.InvalidTokenError as exc:
        raise ValueError("Invalid or expired token") from exc

    if payload.get("type") != expected_type or not payload.get("sub"):
        raise ValueError("Invalid token purpose")
    return payload


def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()


def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def _email_delivery_required() -> bool:
    return settings.app_env in PROTECTED_ENVIRONMENTS


def _verification_token(user: models.User) -> str:
    return create_access_token(
        {"sub": user.username, "type": "verify"},
        expires_delta=VERIFICATION_TOKEN_TTL,
    )


def _send_verification_email(user: models.User) -> bool:
    verify_link = f"{settings.frontend_url}/verify-email?token={user.verification_token}"
    return emailer.send_email(
        user.email,
        "Verify your email - Batalla Medieval",
        f"Welcome {user.username}! Please verify your email by clicking here: {verify_link}",
    )


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    try:
        payload = decode_typed_token(token, "access")
    except ValueError:
        raise _credentials_exception()

    user = get_user_by_username(db, username=payload["sub"])
    if user is None or payload.get("ver") != user.auth_version:
        raise _credentials_exception()
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )
    if user.is_frozen:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account frozen")

    user.last_active_at = utc_now()
    db.commit()
    db.refresh(user)
    return user


@router.post("/register", response_model=schemas.UserRead)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(models.User)
        .filter((models.User.username == user.username) | (models.User.email == user.email))
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        protection_ends_at=utc_now() + timedelta(hours=settings.protection_hours),
        email_notifications=user.email_notifications,
        language=user.language,
        is_verified=False,
    )
    db_user.verification_token = _verification_token(db_user)
    db.add(db_user)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="User already exists")

    delivered = _send_verification_email(db_user)
    if not delivered and _email_delivery_required():
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification email could not be delivered",
        )

    db.commit()
    db.refresh(db_user)
    return db_user


@router.post("/token", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )
    if user.is_frozen:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account frozen: {user.freeze_reason or 'Contact an admin'}",
        )

    client_ip = request.client.host if request and request.client else None
    anticheat.check_multiaccount_ip(db, user, client_ip)
    access_token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "language": user.language,
    }


@router.get("/me", response_model=schemas.UserRead)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserRead)
def update_me(
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    security_changed = False
    email_changed = False

    if payload.email and payload.email != current_user.email:
        existing = db.query(models.User).filter(models.User.email == payload.email).first()
        if existing and existing.id != current_user.id:
            raise HTTPException(status_code=400, detail="Email already registered")

        current_user.email = payload.email
        current_user.is_verified = False
        current_user.verification_token = _verification_token(current_user)
        email_changed = True
        security_changed = True

    if payload.password:
        current_user.hashed_password = get_password_hash(payload.password)
        current_user.password_reset_token = None
        security_changed = True

    if security_changed:
        current_user.auth_version += 1
    if payload.email_notifications is not None:
        current_user.email_notifications = payload.email_notifications
    if payload.language:
        current_user.language = payload.language

    if email_changed:
        delivered = _send_verification_email(current_user)
        if not delivered and _email_delivery_required():
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verification email could not be delivered",
            )

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        payload = decode_typed_token(token, "verify")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user = (
        db.query(models.User)
        .filter(
            models.User.username == payload["sub"],
            models.User.verification_token == token,
        )
        .first()
    )
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user.is_verified = True
    user.verification_token = None
    db.commit()
    return {"message": "Email verified successfully"}


@router.post("/forgot-password")
def forgot_password(payload: schemas.PasswordResetRequest, db: Session = Depends(get_db)):
    generic_response = {"message": "If the email exists, a reset link has been sent."}
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user:
        return generic_response

    reset_token = create_access_token(
        {"sub": user.username, "type": "reset", "ver": user.auth_version},
        expires_delta=PASSWORD_RESET_TOKEN_TTL,
    )
    user.password_reset_token = reset_token

    reset_link = f"{settings.frontend_url}/reset-password?token={reset_token}"
    delivered = emailer.send_email(
        user.email,
        "Password Reset Request",
        f"Click here to reset your password: {reset_link}",
    )
    if not delivered and _email_delivery_required():
        db.rollback()
        return generic_response

    db.commit()
    return generic_response


@router.post("/reset-password")
def reset_password(payload: schemas.PasswordResetConfirm, db: Session = Depends(get_db)):
    try:
        data = decode_typed_token(payload.token, "reset")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = (
        db.query(models.User)
        .filter(
            models.User.username == data["sub"],
            models.User.password_reset_token == payload.token,
        )
        .first()
    )
    if not user or data.get("ver") != user.auth_version:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user.hashed_password = get_password_hash(payload.new_password)
    user.password_reset_token = None
    user.auth_version += 1
    db.commit()

    return {"message": "Password updated successfully"}
