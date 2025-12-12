from sqlalchemy.orm import Session
from fastapi import HTTPException
from .. import models, schemas
from ..utils import utc_now

def list_threads(db: Session, alliance_id: int) -> list[schemas.ForumThreadRead]:
    threads = db.query(models.ForumThread).filter(models.ForumThread.alliance_id == alliance_id).order_by(models.ForumThread.is_pinned.desc(), models.ForumThread.updated_at.desc()).all()
    
    result: list[schemas.ForumThreadRead] = []
    for t in threads:
        reply_count = db.query(models.ForumPost).filter(models.ForumPost.thread_id == t.id).count() - 1 # Subtract OP? No, usually posts are replies + OP. Let's say count is total posts.
        # Actually, usually thread has posts.
        
        result.append(schemas.ForumThreadRead(
            id=t.id,
            alliance_id=t.alliance_id,
            author_id=t.author_id,
            author_name=t.author.username,
            title=t.title,
            is_pinned=bool(t.is_pinned),
            is_locked=bool(t.is_locked),
            created_at=t.created_at,
            updated_at=t.updated_at,
            reply_count=reply_count
        ))
    return result

def get_thread(db: Session, thread_id: int):
    thread = db.query(models.ForumThread).filter(models.ForumThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    posts = db.query(models.ForumPost).filter(models.ForumPost.thread_id == thread_id).order_by(models.ForumPost.created_at.asc()).all()
    
    post_reads = [
        schemas.ForumPostRead(
            id=p.id,
            thread_id=p.thread_id,
            author_id=p.author_id,
            author_name=p.author.username,
            content=p.content,
            created_at=p.created_at
        ) for p in posts
    ]
    
    return schemas.ForumThreadDetail(
        id=thread.id,
        alliance_id=thread.alliance_id,
        author_id=thread.author_id,
        author_name=thread.author.username,
        title=thread.title,
        is_pinned=bool(thread.is_pinned),
        is_locked=bool(thread.is_locked),
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        reply_count=len(posts),
        posts=post_reads
    )

def create_thread(db: Session, alliance_id: int, user: models.User, payload: schemas.ForumThreadCreate):
    thread = models.ForumThread(
        alliance_id=alliance_id,
        author_id=user.id,
        title=payload.title,
        updated_at=utc_now()
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    
    post = models.ForumPost(
        thread_id=thread.id,
        author_id=user.id,
        content=payload.content,
        created_at=utc_now()
    )
    db.add(post)
    db.commit()
    
    return get_thread(db, thread.id)

def create_reply(db: Session, thread_id: int, user: models.User, payload: schemas.ForumPostCreate):
    thread = db.query(models.ForumThread).filter(models.ForumThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
        
    if thread.is_locked:
        raise HTTPException(status_code=400, detail="Thread is locked")
        
    post = models.ForumPost(
        thread_id=thread.id,
        author_id=user.id,
        content=payload.content,
        created_at=utc_now()
    )
    db.add(post)
    
    thread.updated_at = utc_now()
    db.commit()
    db.refresh(post)
    
    return schemas.ForumPostRead(
        id=post.id,
        thread_id=post.thread_id,
        author_id=post.author_id,
        author_name=user.username,
        content=post.content,
        created_at=post.created_at
    )
