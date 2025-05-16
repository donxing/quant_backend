from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import numpy as np
from fastparquet import write
import os
import shutil
import backtrader as bt
from datetime import datetime, timedelta
from dependencies import get_current_user
from schemas import UserOut

def get_backtest_router(app, load_parquet):
    """Create and configure backtest router with access to FastAPI app and parquet loader"""
    router = APIRouter(prefix="/api/backtest", tags=["Backtest"])

    # Output directory for backtest results
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "backtest_results")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    class BacktestRequest(BaseModel):
        stock_code: str
        start_date: str
        end_date: str
        initial_cash: float = 100000.0
        position_size: float = 0.1
        stop_loss_pct: float = 5.0
        max_holding_days: int = 30
        take_profit_pct: float = 10.0
        buy_score_threshold: float = 5.0  # Threshold for buying

    class BacktestResponse(BaseModel):
        result_file: str
        summary: dict

    class FactorPandasData(bt.feeds.PandasData):
        """Custom PandasData feed with buy_score and open price"""
        lines = ('buy_score', 'open')
        params = (
            ('buy_score', 'buy_score'),
            ('open', 'open'),
        )

    class FactorStrategy(bt.Strategy):
        """Backtrader strategy using buy_score with 2-day delay"""
        params = (
            ('position_size', 0.1),
            ('stop_loss_pct', 5.0),
            ('max_holding_days', 30),
            ('take_profit_pct', 10.0),
            ('buy_score_threshold', 5.0),
        )

        def __init__(self):
            self.trades = []
            self.order = None
            self.entry_price = None
            self.entry_date = None
            self.prev_close = None
            self.buy_score = self.data.buy_score
            self.open_price = self.data.open
            self.buy_signal_days = []  # Track days to buy (2-day delay)
            self.sell_signal_days = []  # Track days to sell (2-day delay)
            self.position_size = 0

        def notify_order(self, order):
            if order.status in [order.Completed]:
                if order.isbuy():
                    self.trades.append({
                        'date': self.datas[0].datetime.date(0).isoformat(),
                        'type': 'BUY',
                        'price': order.executed.price,
                        'shares': order.executed.size,
                        'cash': self.broker.getcash(),
                        'position': self.broker.getposition(self.data).size,
                        'portfolio_value': self.broker.getvalue()
                    })
                    self.entry_price = order.executed.price
                    self.entry_date = self.datas[0].datetime.date(0)
                    self.position_size = order.executed.size
                elif order.issell():
                    self.trades.append({
                        'date': self.datas[0].datetime.date(0).isoformat(),
                        'type': 'SELL',
                        'price': order.executed.price,
                        'shares': -order.executed.size,
                        'cash': self.broker.getcash(),
                        'position': self.broker.getposition(self.data).size,
                        'portfolio_value': self.broker.getvalue()
                    })
                    self.entry_price = None
                    self.entry_date = None
                    self.position_size = 0
                self.order = None

        def next(self):
            if self.order:
                return

            current_date = self.datas[0].datetime.date(0)
            current_buy_score = self.buy_score[0]
            current_open = self.open_price[0]
            current_close = self.data.close[0]

            # Check for buy signal (buy_score >= threshold)
            if not self.position and current_buy_score >= self.params.buy_score_threshold:
                self.buy_signal_days.append(current_date)

            # Check for sell signal (buy_score = 0)
            if self.position and current_buy_score == 0:
                self.sell_signal_days.append(current_date)

            # Execute buy on the second day after buy signal
            if self.buy_signal_days and (current_date - self.buy_signal_days[0]).days >= 2:
                cash = self.broker.getcash()
                size = int((cash * self.params.position_size) / current_open)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.buy_signal_days.pop(0)  # Clear the signal after execution

            # Execute sell on the second day after sell signal or other conditions
            elif self.position:
                sell_triggered = False
                if self.sell_signal_days and (current_date - self.sell_signal_days[0]).days >= 2:
                    sell_triggered = True
                elif self.prev_close is not None and current_close < self.prev_close:
                    sell_triggered = True
                elif self.entry_price is not None and current_close <= self.entry_price * (1 - self.params.stop_loss_pct / 100):
                    sell_triggered = True
                elif self.entry_price is not None and current_close >= self.entry_price * (1 + self.params.take_profit_pct / 100):
                    sell_triggered = True
                elif self.entry_date is not None and (current_date - self.entry_date).days >= self.params.max_holding_days:
                    sell_triggered = True

                if sell_triggered:
                    self.order = self.sell(size=self.position.size)
                    if self.sell_signal_days and (current_date - self.sell_signal_days[0]).days >= 2:
                        self.sell_signal_days.pop(0)  # Clear only if sell signal triggered

            self.prev_close = current_close

    def run_backtest(df: pd.DataFrame, params: BacktestRequest) -> tuple[pd.DataFrame, dict]:
        """Execute backtest using Backtrader"""
        df = df[df['code'] == params.stock_code].copy()
        if 'datekey' in df.columns:
            start_date_int = int(params.start_date.replace('-', ''))
            end_date_int = int(params.end_date.replace('-', ''))
            df = df[(df['datekey'] >= start_date_int) & (df['datekey'] <= end_date_int)]

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available for the specified stock and date range")

        df['datetime'] = pd.to_datetime(df['datekey'].astype(str).str[:4] + '-' +
                                       df['datekey'].astype(str).str[4:6] + '-' +
                                       df['datekey'].astype(str).str[6:])
        df = df.set_index('datetime')
        df = df.sort_index()

        # Ensure buy_score and open are in the DataFrame
        if 'buy_score' not in df.columns or 'open' not in df.columns:
            raise HTTPException(status_code=500, detail="buy_score or open column missing in data")

        data = FactorPandasData(
            dataname=df,
            open='open',
            high='high',
            low='low',
            close='close',
            volume='volume',
            datetime=None
        )

        cerebro = bt.Cerebro()
        cerebro.addstrategy(
            FactorStrategy,
            position_size=params.position_size,
            stop_loss_pct=params.stop_loss_pct,
            max_holding_days=params.max_holding_days,
            take_profit_pct=params.take_profit_pct,
            buy_score_threshold=params.buy_score_threshold
        )
        cerebro.adddata(data)
        cerebro.broker.setcash(params.initial_cash)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')

        results = cerebro.run()
        strategy = results[0]

        trades_df = pd.DataFrame(strategy.trades)
        if not trades_df.empty:
            trades_df['date'] = pd.to_datetime(trades_df['date']).dt.strftime('%Y-%m-%d')

        final_value = cerebro.broker.getvalue()
        total_return = (final_value - params.initial_cash) / params.initial_cash * 100
        trade_analyzer = strategy.analyzers.trade_analyzer.get_analysis()
        num_trades = trade_analyzer.get('total', {}).get('total', 0)
        win_trades = trade_analyzer.get('won', {}).get('total', 0)
        win_rate = (win_trades / num_trades * 100) if num_trades > 0 else 0

        summary = {
            'initial_cash': params.initial_cash,
            'final_value': round(final_value, 2),
            'total_return_pct': round(total_return, 2),
            'number_of_trades': num_trades,
            'win_rate_pct': round(win_rate, 2)
        }

        return trades_df, summary

    @router.post("/", response_model=BacktestResponse)
    async def run_backtest_task(
        params: BacktestRequest,
        current_user: UserOut = Depends(get_current_user)
    ):
        """Run asynchronous backtest task"""
        try:
            df = app.state.df
            if df is None:
                raise HTTPException(status_code=500, detail="Backend data not loaded")

            shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
            os.makedirs(OUTPUT_DIR, exist_ok=True)

            trades_df, summary = run_backtest(df, params)

            result_file = os.path.join(OUTPUT_DIR, "backtest.parquet")
            if not trades_df.empty:
                write(result_file, trades_df)

            result_url = "/backtest_results/backtest.parquet"

            return {
                "result_file": result_url,
                "summary": summary
            }
        except HTTPException as http_exc:
            raise http_exc
        except Exception as e:
            print(f"Error running backtest: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/results")
    async def get_backtest_results(current_user: UserOut = Depends(get_current_user)):
        """Return contents of backtest.parquet as JSON"""
        try:
            result_file = os.path.join(OUTPUT_DIR, "backtest.parquet")
            if not os.path.exists(result_file):
                raise HTTPException(status_code=404, detail="No backtest results found")
            df = pd.read_parquet(result_file)
            return df.to_dict(orient="records")
        except Exception as e:
            print(f"Error reading backtest results: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router