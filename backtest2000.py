import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
from pathlib import Path
import akshare as ak
import logging
import requests
from io import BytesIO
from dependencies import get_current_user
import csi_data as csi_data

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BacktestRequest(BaseModel):
    stock_code: str | None = None  # Ignored in CSI2000 strategy
    start_date: str
    end_date: str
    initial_cash: float
    position_size: float
    stop_loss_pct: float
    max_holding_days: int
    take_profit_pct: float
    buy_score_threshold: float = 5.0  # Threshold for buying
    max_daily_buys: int = 5  # Maximum number of stocks to buy daily at full position

def get_csi2000_stock_codes(data_path: str = "data") -> list[str]:
    """
    从本地 Excel 文件获取中证2000指数的成分股代码
    :param data_path: Excel 文件所在的路径，默认为 "data"
    :return: list[str]
    """
    try:
        file_path = Path(data_path) / "932000closeweight.xls"
        if not file_path.exists():
            logger.info("本地无中证2000成分股数据， 开始下载")
            df = csi_data.get_zz2000_constituents_with_weight(data_path)  # 先下载并保存
        else:
            df = pd.read_excel(file_path)
            logger.info(f"从本地文件读取中证2000成分股数据: {file_path}")
        if not df.empty:
            codes = df['成份券代码Constituent Code'].astype(str).str.zfill(6).tolist()
            logger.info(f"Successfully loaded {len(codes)} CSI2000 stock codes")
            return codes
        else:
            logger.error("获取中证2000成分股信息失败: 空数据")
            return []
    except FileNotFoundError:
        logger.error(f"找不到中证2000成分股数据文件: {file_path}")
        return []
    except ValueError as e:
        logger.error(f"读取Excel文件失败: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"获取中证2000成分股失败: {str(e)}")
        return []

def run_csi2000_backtest(
    start_date: str,
    end_date: str,
    initial_cash: float,
    position_size: float,
    stop_loss_pct: float,
    max_holding_days: int,
    take_profit_pct: float,
    buy_score_threshold: float,
    max_daily_buys: int
) -> tuple[dict, pd.DataFrame]:
    """Run backtest on CSI2000 stocks with dynamic portfolio selection using buy_score"""
    # Resolve parquet file path
    base_dir = Path(__file__).parent
    parquet_path = base_dir / 'data' / 'trade_indicators.parquet'

    # Load trade indicators
    try:
        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet file not found at: {parquet_path}")
        raw_df = pd.read_parquet(parquet_path)
        logger.info(f"Successfully loaded trade_indicators.parquet from {parquet_path}")
    except FileNotFoundError as e:
        logger.error(f"读取trade_indicators.parquet失败: {str(e)}")
        raise ValueError(f"无法读取交易指标数据: {str(e)}")
    except Exception as e:
        logger.error(f"读取trade_indicators.parquet失败: {str(e)}")
        raise ValueError(f"无法读取交易指标数据: {str(e)}")

    # Clean stock codes
    raw_df['code'] = raw_df['code'].str.split('.').str[0]
    logger.info(f"Parquet stock codes (first 5): {raw_df['code'].unique()[:5].tolist()}")

    # Ensure date column
    if 'date' not in raw_df.columns:
        if raw_df.index.name == 'date':
            raw_df = raw_df.reset_index()
        else:
            date_col = [c for c in raw_df.columns if 'date' in c.lower()]
            if date_col:
                raw_df = raw_df.rename(columns={date_col[0]: 'date'})
            else:
                raise ValueError("数据中未找到时间列")

    raw_df['date'] = pd.to_datetime(raw_df['date'])
    raw_df = raw_df.sort_values(['code', 'date']).reset_index(drop=True)

    # Filter CSI2000 stocks
    csi2000_codes = get_csi2000_stock_codes()
    if not csi2000_codes:
        raise ValueError("无法获取中证2000成分股列表")
    csi2000_df = raw_df[raw_df['code'].isin(csi2000_codes)].copy()
    if csi2000_df.empty:
        logger.error(f"No CSI2000 stocks found in parquet data. Available codes: {raw_df['code'].unique()[:5].tolist()}")
        raise ValueError("没有找到中证2000成分股的交易数据")

    # Exclude stocks starting with "301" or "688"
    csi2000_df = csi2000_df[
        ~csi2000_df['code'].str.startswith('301') &
        ~csi2000_df['code'].str.startswith('688')
    ].copy()
    if csi2000_df.empty:
        logger.error("After excluding stocks starting with '301' or '688', no stocks remain for backtesting.")
        raise ValueError("排除代码以'301'或'688'开头的股票后，没有剩余股票可用于回测")

    # Load weights from Excel file
    try:
        file_path = Path("data") / "932000closeweight.xls"
        if not file_path.exists():
            logger.info("本地无中证2000成分股数据， 开始下载")
            weights_df = csi_data.get_zz2000_constituents_with_weight("data")  # 先下载并保存
        else:
            weights_df = pd.read_excel(file_path)
            logger.info(f"从本地文件读取中证2000成分股数据: {file_path}")
        if weights_df.empty:
            raise ValueError("中证2000成分股数据为空")
        
        # Clean and prepare weights data
        weights_df['成份券代码Constituent Code'] = weights_df['成份券代码Constituent Code'].astype(str).str.zfill(6)
        weights_df = weights_df[['成份券代码Constituent Code', '权重(%)weight']].rename(columns={
            '成份券代码Constituent Code': 'code',
            '权重(%)weight': 'weight'
        })
        
        # Exclude stocks starting with "301" or "688" from weights
        weights_df = weights_df[
            ~weights_df['code'].str.startswith('301') &
            ~weights_df['code'].str.startswith('688')
        ]
        
        # Merge weights with csi2000_df
        csi2000_df = csi2000_df.merge(weights_df, on='code', how='left')
        if csi2000_df['weight'].isna().all():
            raise ValueError("无法将权重数据与交易数据匹配")
    except Exception as e:
        logger.error(f"加载权重数据失败: {str(e)}")
        raise ValueError(f"无法加载权重数据: {str(e)}")

    # Filter by date range
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    csi2000_df = csi2000_df[
        (csi2000_df['date'] >= start_date) &
        (csi2000_df['date'] <= end_date)
    ].copy()
    if csi2000_df.empty:
        raise ValueError("指定日期范围内没有数据")

    # Verify buy_score and open columns exist
    if 'buy_score' not in csi2000_df.columns or 'open' not in csi2000_df.columns:
        raise ValueError("Data must contain 'buy_score' and 'open' columns")

    # Calculate daily sum(buy_score) for position sizing
    daily_buy_score = csi2000_df.groupby('date')['buy_score'].sum().reset_index()
    daily_buy_score_dict = dict(zip(daily_buy_score['date'], daily_buy_score['buy_score']))

    # Initialize portfolio
    cash = initial_cash
    holdings = {}  # {code: {'shares': int, 'buy_price': float, 'buy_date': datetime}}
    trades = []
    portfolio_values = []

    # Get trading days
    trading_days = sorted(csi2000_df['date'].unique())

    # Track pending trades with signal dates for 2-day delay
    pending_buys = []  # List of dicts: {'code': code, 'shares': shares, 'signal_date': date}
    pending_sells = []  # List of dicts: {'code': code, 'shares': shares, 'signal_date': date}

    for i, day in enumerate(trading_days):
        day_str = day.strftime('%Y-%m-%d')
        day_data = csi2000_df[csi2000_df['date'] == day].copy()

        # Calculate position scaling based on sum(buy_score)
        sum_buy_score = daily_buy_score_dict.get(day, 0)
        if sum_buy_score < 5000:
            position_scale = 0.0  # Empty position
            adjusted_max_daily_buys = 0
        elif 5000 <= sum_buy_score < 10000:
            position_scale = 0.2  # 20% position
            adjusted_max_daily_buys = max(1, int(max_daily_buys * 0.2))
        elif 10000 <= sum_buy_score < 20000:
            position_scale = 0.3  # 30% position
            adjusted_max_daily_buys = max(1, int(max_daily_buys * 0.3))
        elif 20000 <= sum_buy_score < 30000:
            position_scale = 0.6  # 60% position
            adjusted_max_daily_buys = max(1, int(max_daily_buys * 0.6))
        elif 30000 <= sum_buy_score < 40000:
            position_scale = 0.8  # 80% position
            adjusted_max_daily_buys = max(1, int(max_daily_buys * 0.8))
        else:  # >= 40000
            position_scale = 1.0  # Full position
            adjusted_max_daily_buys = max_daily_buys

        # Step 1: Execute pending trades if 2 days have passed since the signal
        if i >= 2:  # Need at least 2 days of data to execute trades
            # Execute pending sells
            for sell in pending_sells[:]:
                signal_date = sell['signal_date']
                if (day - signal_date).days >= 2:
                    code = sell['code']
                    shares = sell['shares']
                    stock_data = day_data[day_data['code'] == code]
                    if stock_data.empty:
                        continue
                    stock_data = stock_data.iloc[0]
                    sell_price = stock_data['open']  # Use open price
                    # Calculate profit: (sell_price - buy_price) * shares
                    buy_price = holdings.get(code, {}).get('buy_price', 0)
                    profit = (sell_price - buy_price) * shares
                    cash += shares * sell_price
                    trades.append({
                        'date': day_str,
                        'type': 'SELL',
                        'code': code,
                        'price': sell_price,
                        'shares': shares,
                        'cash': cash,
                        'position': 0,
                        'portfolio_value': cash,
                        'profit': profit  # Add profit to the trade record
                    })
                    if code in holdings:
                        del holdings[code]
                    pending_sells.remove(sell)

            # Execute pending buys
            for buy in pending_buys[:]:
                signal_date = buy['signal_date']
                if (day - buy['signal_date']).days >= 2:
                    code = buy['code']
                    shares = buy['shares']
                    stock_data = day_data[day_data['code'] == code]
                    if stock_data.empty:
                        continue
                    stock_data = stock_data.iloc[0]
                    buy_price = stock_data['open']  # Use open price
                    cost = shares * buy_price
                    if cost <= cash:
                        cash -= cost
                        holdings[code] = {
                            'shares': shares,
                            'buy_price': buy_price,
                            'buy_date': day
                        }
                        trades.append({
                            'date': day_str,
                            'type': 'BUY',
                            'code': code,
                            'price': buy_price,
                            'shares': shares,
                            'cash': cash,
                            'position': shares,
                            'portfolio_value': cash,
                            'profit': 0  # No profit for BUY trades
                        })
                    pending_buys.remove(buy)

        # Step 2: Check for sell-all signal (sum_buy_score < 5000) for next day
        if sum_buy_score < 5000 and holdings:
            for code in list(holdings.keys()):
                shares = holdings[code]['shares']
                pending_sells.append({
                    'code': code,
                    'shares': shares,
                    'signal_date': day + timedelta(days=1)  # Sell next day
                })
                del holdings[code]

        # Step 3: Check for new sell signals on the current day (based on buy_score = 0)
        for code in list(holdings.keys()):
            stock_data = day_data[day_data['code'] == code]
            if stock_data.empty:
                continue
            stock_data = stock_data.iloc[0]
            current_price = stock_data['close']  # Use close for stop-loss/take-profit checks
            buy_price = holdings[code]['buy_price']
            buy_date = holdings[code]['buy_date']
            shares = holdings[code]['shares']
            current_buy_score = stock_data['buy_score']

            # Skip if already scheduled to sell
            if any(sell['code'] == code for sell in pending_sells):
                continue

            # Sell conditions
            should_sell = False
            if current_buy_score == 0:
                should_sell = True
            elif current_price <= buy_price * (1 - stop_loss_pct / 100):
                should_sell = True
            elif current_price >= buy_price * (1 + take_profit_pct / 100):
                should_sell = True
            elif (day - buy_date).days >= max_holding_days:
                should_sell = True

            if should_sell:
                pending_sells.append({
                    'code': code,
                    'shares': shares,
                    'signal_date': day
                })

        # Step 4: Check for new buy signals only if sum_buy_score >= 5000
        if sum_buy_score >= 5000:
            buy_candidates = day_data[
                day_data['buy_score'] >= buy_score_threshold
            ][['code', 'close', 'weight']].copy()
            buy_candidates = buy_candidates.sort_values('weight', ascending=True)

            # Queue up to adjusted_max_daily_buys stocks for buying
            stocks_to_buy = []
            current_holdings = len(holdings) + sum(1 for buy in pending_buys if (day - buy['signal_date']).days < 2)
            available_position_cash = cash * position_size * position_scale
            for _, candidate in buy_candidates.iterrows():
                if current_holdings >= adjusted_max_daily_buys:
                    break
                code = candidate['code']
                if code in holdings or any(buy['code'] == code for buy in pending_buys):
                    continue
                price = candidate['close']  # Temporary price for share calculation
                min_cost = price * 100  # Minimum cost for 100 shares
                if min_cost > available_position_cash:
                    continue  # Skip if 100 shares cost more than available position cash
                stocks_to_buy.append(candidate)
                current_holdings += 1

            for candidate in stocks_to_buy:
                code = candidate['code']
                price = candidate['close']  # Temporary price for share calculation
                shares = int((cash * position_size * position_scale) / price)
                shares = max(100, ((shares + 99) // 100) * 100)  # Round up to nearest 100, minimum 100
                if shares > 0:
                    pending_buys.append({
                        'code': code,
                        'shares': shares,
                        'signal_date': day
                    })

        # Step 5: Calculate portfolio value at the end of the current day
        portfolio_value = cash
        for code in holdings:
            stock_data = day_data[day_data['code'] == code]
            if not stock_data.empty:
                portfolio_value += holdings[code]['shares'] * stock_data.iloc[0]['close']
        portfolio_values.append({'date': day_str, 'portfolio_value': portfolio_value})

        # Update portfolio_value in trades
        for trade in trades:
            if trade['date'] == day_str:
                trade['portfolio_value'] = portfolio_value

    # Finalize trades
    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        raise ValueError("回测未生成任何交易")

    # Calculate summary
    final_value = portfolio_values[-1]['portfolio_value'] if portfolio_values else initial_cash
    total_return_pct = ((final_value - initial_cash) / initial_cash) * 100
    buy_trades = trades_df[trades_df['type'] == 'BUY'].set_index('date')
    sell_trades = trades_df[trades_df['type'] == 'SELL'].set_index('date')
    
    wins = []
    for _, sell in sell_trades.iterrows():
        code = sell['code']
        sell_price = sell['price']
        # Find the most recent buy for the same code before the sell date
        relevant_buys = buy_trades[buy_trades['code'] == code]
        if not relevant_buys.empty:
            latest_buy = relevant_buys[relevant_buys.index <= sell.name].iloc[-1]
            buy_price = latest_buy['price']
            wins.append(sell_price > buy_price)
    
    win_rate_pct = (sum(wins) / len(wins) * 100) if wins else 0

    summary = {
        'initial_cash': initial_cash,
        'final_value': final_value,
        'total_return_pct': total_return_pct,
        'number_of_trades': len(trades_df),
        'win_rate_pct': win_rate_pct
    }

    # Save results
    output_dir = Path('data') / 'backtest_results'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / 'backtest2000.parquet'
    trades_df.to_parquet(output_path)

    return summary, trades_df

@router.post("/api/backtest2000/")
async def run_backtest2000(request: BacktestRequest, current_user: str = Depends(get_current_user)):
    try:
        summary, trades_df = run_csi2000_backtest(
            start_date=request.start_date,
            end_date=request.end_date,
            initial_cash=request.initial_cash,
            position_size=request.position_size,
            stop_loss_pct=request.stop_loss_pct,
            max_holding_days=request.max_holding_days,
            take_profit_pct=request.take_profit_pct,
            buy_score_threshold=request.buy_score_threshold,
            max_daily_buys=request.max_daily_buys
        )
        return {
            "summary": summary,
            "result_file": "/backtest_results/backtest2000.parquet"
        }
    except Exception as e:
        logger.error(f"CSI2000回测失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/backtest2000/results")
async def get_backtest2000_results(current_user: str = Depends(get_current_user)):
    try:
        output_path = Path("data") / "backtest_results" / 'backtest2000.parquet'
        if not output_path.exists():
            raise HTTPException(status_code=404, detail="CSI2000回测结果文件不存在")
        df = pd.read_parquet(output_path)
        return df.to_dict(orient='records')
    except Exception as e:
        logger.error(f"获取CSI2000回测结果失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))