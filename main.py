from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine, async_session
from auth import router as auth_router
from stock import get_stock_router
from backtest import get_backtest_router
from backtest2000 import router as backtest2000_router
import os
from contextlib import asynccontextmanager
import akshare as ak
import pandas as pd
from retrying import retry
from sqlalchemy.ext.asyncio import AsyncSession
from dependencies import get_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Initialize database tables
    print("⚙️ 正在初始化数据库表结构...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库表初始化完成")

    # Skip loading stock_trade_processor data during startup
    app.state.df = None  # Explicitly set to None
    print("ℹ️ Skipped loading stock_trade_processor data during startup")

    yield
    # Cleanup
    app.state.df = None

app = FastAPI(
    title="股票数据与用户管理API服务",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AKShare retry decorator
@retry(stop_max_attempt_number=3, wait_fixed=2000)
def fetch_index_data(start_date_ak, end_date_ak):
    return ak.index_zh_a_hist(symbol="932000", start_date=start_date_ak, end_date=end_date_ak)

# CSI2000 index data endpoint
@app.get("/api/index/csi2000")
async def get_csi2000_index(start_date: str, end_date: str):
    try:
        start_date_ak = start_date.replace('-', '')
        end_date_ak = end_date.replace('-', '')
        df = fetch_index_data(start_date_ak, end_date_ak)
        if df.empty:
            raise ValueError("未找到中证2000指数数据")
        df = df.rename(columns={'日期': 'date', '收盘': 'close'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        return {"data": df[['date', 'close']].to_dict(orient='records')}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取中证2000指数数据失败: {str(e)}")

# Include routers
app.include_router(auth_router)
stock_router, _ = get_stock_router(app)  # Ignore load_data_func
backtest_router = get_backtest_router(app, None)  # Pass None for load_parquet
app.include_router(stock_router)
app.include_router(backtest_router)
app.include_router(backtest2000_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)