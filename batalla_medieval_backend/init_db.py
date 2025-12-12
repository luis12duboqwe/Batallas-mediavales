from app.database import Base, engine
from app.main import app
from app.models.movement import Movement

print("Creating tables...")
print("Movement columns:", Movement.__table__.columns.keys())
Base.metadata.create_all(bind=engine)
print("Tables created.")
