from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine, DATABASE_URL
from auth import router as auth_router
from stock import get_stock_router
from backtest import get_backtest_router
from backtest2000 import router as backtest2000_router
import os
from contextlib import asynccontextmanager
import akshare as ak
import pandas as pd
from retrying import retry

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Initialize user database
    db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if not os.path.exists(db_path):
        print("⚙️ 用户数据库文件不存在，正在初始化...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ 用户数据库初始化完成。")
    else:
        print("🗃 用户数据库已存在，跳过初始化。")

    # Load parquet data
    try:
        app.state.df = load_parquet()
        print("Parquet 数据加载成功")
    except FileNotFoundError as e:
        print(f"错误: {e}")
        app.state.df = None
    except Exception as e:
        print(f"加载 Parquet 文件时发生错误: {e}")
        app.state.df = None

    yield
    # Cleanup
    app.state.df = None

app = FastAPI(
    title="股票数据与用户管理API服务",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Retry decorator for AKShare
@retry(stop_max_attempt_number=3, wait_fixed=2000)
def fetch_index_data(start_date_ak, end_date_ak):
    return ak.index_zh_a_hist(symbol="932000", start_date=start_date_ak, end_date=end_date_ak)

# API endpoint for CSI2000 index data
@app.get("/api/index/csi2000")
async def get_csi2000_index(start_date: str, end_date: str):
    try:
        # Convert dates to YYYYMMDD for AKShare
        start_date_ak = start_date.replace('-', '')
        end_date_ak = end_date.replace('-', '')
        df = fetch_index_data(start_date_ak, end_date_ak)
        if df.empty:
            raise ValueError("未找到中证2000指数数据")
        # Format for frontend
        df = df.rename(columns={'日期': 'date', '收盘': 'close'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        return {"data": df[['date', 'close']].to_dict(orient='records')}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取中证2000指数数据失败: {str(e)}")

# Include Routers
app.include_router(auth_router)
stock_router, load_parquet = get_stock_router(app)
backtest_router = get_backtest_router(app, load_parquet)
app.include_router(stock_router)
app.include_router(backtest_router)
app.include_router(backtest2000_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)