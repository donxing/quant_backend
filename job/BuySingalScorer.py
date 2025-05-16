import pandas as pd
import numpy as np
from fastparquet import write
import os

class BuySignalScorer:
    """Class to calculate buy signal scores and update trade_indicators.parquet"""
    
    def __init__(self, parquet_path):
        self.parquet_path = parquet_path
        self.df = None
        self.buy_signals = ['TRENDBUY', 'BOTTOMBUY', 'BOTTOMUPBUY', 'POTENTIALBUY', 'ENTRYBUY']
        self.sell_signals = ['TRENDSELL', 'CLEANSELL', 'STAGESELL','POWERDOWNSELL']
        
    def load_data(self):
        """Load the parquet file into a DataFrame"""
        if not os.path.exists(self.parquet_path):
            raise FileNotFoundError(f"Parquet file not found at: {self.parquet_path}")
        self.df = pd.read_parquet(self.parquet_path)
        return self.df
    
    def calculate_scores(self):
        """Calculate buy signal scores for each stock code"""
        if self.df is None:
            self.load_data()
            
        # Ensure required columns exist
        required_cols = self.buy_signals + self.sell_signals + ['ddx', 'POWERUP']
        missing_cols = [col for col in required_cols if col not in self.df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
            
        # Group by stock code to process each stock independently
        self.df = self.df.sort_values(['code', 'datekey'])
        result_dfs = []
        
        for code, group in self.df.groupby('code'):
            group = group.copy()
            group['buy_score'] = 0.0
            scoring_active = False
            current_score = 0.0
            
            for idx in group.index:
                # Check if any buy signal is present to start scoring
                if not scoring_active and any(group.loc[idx, signal] for signal in self.buy_signals):
                    scoring_active = True
                    current_score = 0.0
                
                # If scoring is active, calculate the score
                if scoring_active:
                    # Check for sell signals to reset score
                    if any(group.loc[idx, signal] for signal in self.sell_signals):
                        current_score = 0.0
                        scoring_active = False
                    else:
                        # Add points for positive conditions
                        if group.loc[idx, 'ddx'] > 0:
                            current_score += 1.0
                        if group.loc[idx, 'POWERUP']:
                            current_score += 1.0
                        if any(group.loc[idx, signal] for signal in self.buy_signals):
                            current_score += 1.0
                            
                        # Subtract points for negative conditions
                        if group.loc[idx, 'ddx'] < 0:
                            current_score -= 1.0
                        if not group.loc[idx, 'POWERUP']:
                            current_score -= 1.0
                            
                        # Ensure score doesn't go negative
                        current_score = max(0.0, current_score)
                
                group.loc[idx, 'buy_score'] = current_score
            
            result_dfs.append(group)
        
        # Combine results and update the DataFrame
        self.df = pd.concat(result_dfs, ignore_index=True)
        # Add 'date' column in yyyy-mm-dd format
        self.df['date'] = self.df['datekey'].astype(str).str[:4] + '-' + \
                          self.df['datekey'].astype(str).str[4:6] + '-' + \
                          self.df['datekey'].astype(str).str[6:]
        return self.df
    
    def save_data(self):
        """Save the updated DataFrame back to parquet"""
        if self.df is None:
            raise ValueError("No data to save. Run calculate_scores() first.")
        write(self.parquet_path, self.df, compression='SNAPPY')
        
def process_buy_scores(parquet_path):
    """Main function to process buy scores and update parquet file"""
    scorer = BuySignalScorer(parquet_path)
    scorer.load_data()
    scorer.calculate_scores()
    scorer.save_data()
    return scorer.df

# Example usage:
if __name__ == "__main__":
    PARQUET_PATH = os.path.join(os.path.dirname(__file__), "data", "trade_indicators.parquet")
    updated_df = process_buy_scores(PARQUET_PATH)
    print(updated_df[['code', 'datekey', 'buy_score']].head())