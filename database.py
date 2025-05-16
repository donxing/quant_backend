from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

# 获取项目根目录（database.py 的上一级目录）
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "quant_backend/auth.db"

# 构建数据库连接 URL
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

engine = create_async_engine(DATABASE_URL, echo=True, future=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()
