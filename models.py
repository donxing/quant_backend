from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String

Base = declarative_base()

class User(Base):
    __tablename__ = 'stock_users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)

class StockTradeProcessor(Base):
    __tablename__ = 'stock_trade_processor'
    
    date = Column(String(255), primary_key=True, nullable=False)  # Primary key part 1
    code = Column(String(255), primary_key=True, nullable=False)  # Primary key part 2
    datekey = Column(String(255), nullable=True)  # YYYYMMDD as string
    close = Column(String(255), nullable=True)  # Numeric value as string
    open = Column(String(255), nullable=True)  # Numeric value as string
    low = Column(String(255), nullable=True)  # Numeric value as string
    high = Column(String(255), nullable=True)  # Numeric value as string
    volume = Column(String(255), nullable=True)  # Numeric value as string
    ddx = Column(String(255), nullable=True)  # Additional field
    POWERLINE = Column(String(255), nullable=True)  # Additional field
    POWERUP = Column(String(255), nullable=True)  # Boolean as string
    ENTRYBUY = Column(String(255), nullable=True)  # Boolean as string
    BOTTOMBUY = Column(String(255), nullable=True)  # Boolean as string
    BOTTOMUPBUY = Column(String(255), nullable=True)  # Boolean as string
    POTENTIALBUY = Column(String(255), nullable=True)  # Boolean as string
    STRONGBUY = Column(String(255), nullable=True)  # Boolean as string
    TRENDBUY = Column(String(255), nullable=True)  # Boolean as string
    POWERDOWNSELL = Column(String(255), nullable=True)  # Boolean as string
    TRENDSELL = Column(String(255), nullable=True)  # Boolean as string
    CLEANSELL = Column(String(255), nullable=True)  # Boolean as string
    STAGESELL = Column(String(255), nullable=True)  # Boolean as string
    buy_score = Column(String(255), nullable=True)  # Numeric value as string

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},  # Ensure InnoDB engine for MySQL
    )