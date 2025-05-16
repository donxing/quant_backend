from fastapi import APIRouter, HTTPException, Depends, FastAPI
from schemas import StockResponse, UserOut, StockData
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import StockTradeProcessor
from dependencies import get_current_user, get_db  # Import get_db

def get_stock_router(app: FastAPI):
    """Create and configure stock router with access to FastAPI app"""

    router = APIRouter(prefix="/api/stocks", tags=["Stocks"])

    async def load_data_func(db: AsyncSession = Depends(get_db)):
        """Load stock data from the database."""
        try:
            result = await db.execute(select(StockTradeProcessor))
            stock_data = result.scalars().all()
            return stock_data
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    @router.get("/{stock_code}", response_model=StockResponse)
    async def get_stock_data(
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        current_user: UserOut = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)  # Inject database session
    ):
        """Get stock data for a specific stock code from the database."""
        try:
            query = select(StockTradeProcessor).filter(StockTradeProcessor.code == stock_code)

            if start_date:
                try:
                    start_date_int = int(start_date.replace('-', ''))
                    query = query.filter(StockTradeProcessor.datekey >= str(start_date_int))
                except ValueError:
                    raise HTTPException(status_code=400, detail="start_date 格式错误，应为YYYY-MM-DD")

            if end_date:
                try:
                    end_date_int = int(end_date.replace('-', ''))
                    query = query.filter(StockTradeProcessor.datekey <= str(end_date_int))
                except ValueError:
                    raise HTTPException(status_code=400, detail="end_date 格式错误，应为YYYY-MM-DD")

            result = await db.execute(query)
            stock_data = result.scalars().all()

            if not stock_data:
                raise HTTPException(status_code=404, detail="股票代码不存在")

            # Convert database results to StockData format
            formatted_data: List[StockData] = []
            for item in stock_data:
                formatted_data.append(StockData(
                    date=item.date,  # Assuming date is already in the correct format
                    code=item.code,
                    close=float(item.close) if item.close is not None else None,
                    open=float(item.open) if item.open is not None else None,
                    low=float(item.low) if item.low is not None else None,
                    high=float(item.high) if item.high is not None else None,
                    volume=int(item.volume) if item.volume is not None else None,
                    POWERUP=bool(item.POWERUP) if item.POWERUP is not None else None,
                    ENTRYBUY=bool(item.ENTRYBUY) if item.ENTRYBUY is not None else None,
                    BOTTOMBUY=bool(item.BOTTOMBUY) if item.BOTTOMBUY is not None else None,
                    BOTTOMUPBUY=bool(item.BOTTOMUPBUY) if item.BOTTOMUPBUY is not None else None,
                    POTENTIALBUY=bool(item.POTENTIALBUY) if item.POTENTIALBUY is not None else None,
                    STARK=False, # item.STARK,  # Assuming STARK is not in your model
                    TRENDBUY=bool(item.TRENDBUY) if item.TRENDBUY is not None else None,
                    STRONGBUY=bool(item.STRONGBUY) if item.STRONGBUY is not None else None,
                    POWERDOWNSELL=bool(item.POWERDOWNSELL) if item.POWERDOWNSELL is not None else None,
                    TRENDSELL=bool(item.TRENDSELL) if item.TRENDSELL is not None else None,
                    CLEANSELL=bool(item.CLEANSELL) if item.CLEANSELL is not None else None,
                    STAGESELL=bool(item.STAGESELL) if item.STAGESELL is not None else None,
                    buy_score=float(item.buy_score) if item.buy_score is not None else None,
                    POWERLINE=float(item.POWERLINE) if item.POWERLINE is not None else None
                ))

            return {
                "code": stock_code,
                "data": formatted_data
            }
        except HTTPException as http_exc:
            raise http_exc
        except Exception as e:
            print(f"获取股票数据时发生错误: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/codes", response_model=dict)
    async def get_stock_codes(
        current_user: UserOut = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ):
        """Get list of all stock codes from the database."""
        try:
            result = await db.execute(select(StockTradeProcessor.code).distinct())
            codes = [row.code for row in result.all()]
            return {"codes": sorted(codes)}
        except Exception as e:
            print(f"获取股票代码列表时发生错误: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router, load_data_func