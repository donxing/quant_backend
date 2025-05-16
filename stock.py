from fastapi import APIRouter, HTTPException, Depends
from schemas import StockResponse, UserOut
from typing import Optional
import pandas as pd
from fastparquet import ParquetFile
import numpy as np
from dependencies import get_current_user
import os

# Parquet File Path
PARQUET_PATH = os.path.join(os.path.dirname(__file__), "data", "trade_indicators.parquet")

def get_stock_router(app):
    """Create and configure stock router with access to FastAPI app"""
    router = APIRouter(prefix="/api/stocks", tags=["Stocks"])

    def load_parquet():
        """Load and cache Parquet file"""
        print(f"Checking for parquet file at: {PARQUET_PATH}")
        if not os.path.exists(PARQUET_PATH):
            raise FileNotFoundError(f"股票数据文件不存在: {PARQUET_PATH}")

        # Fix _ARRAY_API error
        import fastparquet.schema
        if not hasattr(fastparquet.schema, '_ARRAY_API'):
            fastparquet.schema._ARRAY_API = np

        pf = ParquetFile(PARQUET_PATH)
        df = pf.to_pandas()

        # Reset index to make 'date' a regular column
        df = df.reset_index()

        # Convert datekey to integer
        if 'datekey' in df.columns:
            df['datekey'] = pd.to_numeric(df['datekey'], errors='coerce').astype('Int64')

        return convert_bool_fields(df)

    def convert_bool_fields(df):
        """Convert boolean fields in DataFrame"""
        bool_cols = {
            'POWERUP': bool,
            'BOTTOMBUY': bool,
            'BOTTOMUPBUY': bool,
            'POTENTIALBUY': bool,
            'STARK': bool,
            'ENTRYBUY':bool,
            'STRONGBUY': bool,
            'TRENDBUY': bool,
            'TRENDSELL': bool,
            'POWERDOWNSELL': bool,
            'CLEANSELL': bool,
            'STAGESELL': bool                      
        }

        for col, dtype in bool_cols.items():
            if col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].astype(bool)
                elif pd.api.types.is_object_dtype(df[col]):
                    df[col] = df[col].str.lower().map({'true': True, 'false': False})
                elif pd.api.types.is_bool_dtype(df[col]):
                    df[col] = df[col].astype(bool)

        return df

    @router.get("/{stock_code}", response_model=StockResponse)
    async def get_stock_data(
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        current_user: UserOut = Depends(get_current_user)
    ):
        """Get stock data for a specific stock code"""
        try:
            df = app.state.df
            if df is None:
                raise HTTPException(status_code=500, detail="后端数据未加载")

            # Filter by stock code
            filtered_df = df[df['code'] == stock_code].copy()

            if filtered_df.empty:
                raise HTTPException(status_code=404, detail="股票代码不存在")

            # Date filtering (using datekey, format YYYYMMDD as integer)
            if 'datekey' in filtered_df.columns:
                if start_date:
                    try:
                        start_date_int = int(start_date.replace('-', ''))
                        filtered_df = filtered_df[filtered_df['datekey'] >= start_date_int]
                    except ValueError:
                        raise HTTPException(status_code=400, detail="start_date 格式错误，应为YYYY-MM-DD")
                if end_date:
                    try:
                        end_date_int = int(end_date.replace('-', ''))
                        filtered_df = filtered_df[filtered_df['datekey'] <= end_date_int]
                    except ValueError:
                        raise HTTPException(status_code=400, detail="end_date 格式错误，应为YYYY-MM-DD")

                # Convert datekey to YYYY-MM-DD for response
                filtered_df['date'] = filtered_df['datekey'].astype(str).str[:4] + '-' + \
                                     filtered_df['datekey'].astype(str).str[4:6] + '-' + \
                                     filtered_df['datekey'].astype(str).str[6:]

                # Ensure 'date' column is string
                filtered_df['date'] = filtered_df['date'].astype(str)
            else:
                raise HTTPException(status_code=500, detail="Parquet 文件中缺少 datekey 列")

            # Final formatting
            filtered_df = filtered_df.sort_values('date')
            filtered_df.replace({np.nan: None}, inplace=True)

            return {
                "code": stock_code,
                "data": filtered_df.to_dict('records')
            }

        except HTTPException as http_exc:
            raise http_exc
        except Exception as e:
            print(f"获取股票数据时发生错误: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/codes", response_model=dict)
    async def get_stock_codes(current_user: UserOut = Depends(get_current_user)):
        """Get list of all stock codes"""
        try:
            df = app.state.df
            if df is None:
                raise HTTPException(status_code=500, detail="后端数据未加载")
            codes = df['code'].unique().tolist()
            return {"codes": sorted(codes)}
        except HTTPException as http_exc:
            raise http_exc
        except Exception as e:
            print(f"获取股票代码列表时发生错误: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router, load_parquet