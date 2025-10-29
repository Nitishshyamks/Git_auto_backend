import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing from .env")

# Async engine for Neon (postgresql+asyncpg://...)
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

Base = declarative_base()

# FastAPI dependency
async def get_db():
    async with SessionLocal() as session:
        yield session

# Called on startup OR via `main.py init-db`
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
