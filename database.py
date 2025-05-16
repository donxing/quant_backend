from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

# MySQL 连接配置
MYSQL_USER = "root"  # 替换为你的 MySQL 用户名
MYSQL_PASSWORD = "root"  # 替换为你的 MySQL 密码
MYSQL_HOST = "192.168.44.137"  # 替换为你的 MySQL 主机地址
MYSQL_PORT = "3306"  # 替换为你的 MySQL 端口
MYSQL_DATABASE = "quant_factor"  # 替换为你的数据库名

# 构建 MySQL 异步连接 URL
# 使用 asyncmy 驱动（推荐，性能更好）
DATABASE_URL = f"mysql+asyncmy://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# 或者使用 aiomysql 驱动（备选）
# DATABASE_URL = f"mysql+aiomysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # 设置为 True 可以打印 SQL 语句，调试时很有用
    future=True,
    pool_pre_ping=True,  # 建议启用，会自动检查连接是否有效
    pool_recycle=3600,  # 设置连接回收时间（秒）
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()