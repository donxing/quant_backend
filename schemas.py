from pydantic import BaseModel
from typing import List, Optional

class UserCreate(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    username: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class StockData(BaseModel):
    date: str  # YYYY-MM-DD
    code: str
    close: float
    open: float
    low: float
    high: float
    volume: int
    POWERUP: bool
    ENTRYBUY: bool
    BOTTOMBUY: bool
    BOTTOMUPBUY: bool
    POTENTIALBUY: bool
    STARK: Optional[bool] = False
    TRENDBUY: bool
    STRONGBUY: bool
    POWERDOWNSELL: bool
    TRENDSELL: bool
    CLEANSELL: bool
    STAGESELL: bool
    buy_score: float
    POWERLINE: Optional[float] = None  # Added as optional

class StockResponse(BaseModel):
    code: str
    data: List[StockData]