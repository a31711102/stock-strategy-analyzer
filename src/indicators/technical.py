"""
テクニカル指標計算モジュール

pandasとnumpyを使用して各種テクニカル指標を計算
将来的なロジック変更を容易にするため、各指標の計算方法を明確に記述
"""
import pandas as pd
import numpy as np
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """テクニカル指標計算クラス"""
    
    @staticmethod
    def calculate_ma(
        df: pd.DataFrame, 
        timeframe: str = 'daily'
    ) -> pd.DataFrame:
        """
        移動平均を計算
        
        【計算方法】
        - SMA (Simple Moving Average): 単純移動平均
          → 指定期間の終値の平均値
        - EMA (Exponential Moving Average): 指数移動平均
          → 直近の価格に重みを置いた移動平均
        
        Args:
            df: OHLCVデータ
            timeframe: 時間足（'daily', 'weekly', 'monthly'）
        
        Returns:
            移動平均を追加したデータフレーム
        """
        # 時間足に応じた期間設定
        periods = {
            'daily': [5, 25, 75, 200],      # 日足: 1週間、1ヶ月、3ヶ月、10ヶ月
            'weekly': [13, 26, 52],         # 週足: 3ヶ月、6ヶ月、1年
            'monthly': [6, 12, 36]          # 月足: 半年、1年、3年
        }
        
        ma_periods = periods.get(timeframe, periods['daily'])
        
        for period in ma_periods:
            # SMA計算: 指定期間の終値の単純平均
            df[f'SMA_{period}'] = df['Close'].rolling(window=period).mean()
            
            # EMA計算: 指数移動平均（直近の価格に重みを置く）
            # span=期間で、α=2/(span+1)の重み付け
            df[f'EMA_{period}'] = df['Close'].ewm(span=period, adjust=False).mean()
        
        logger.debug(f"Calculated MA for {timeframe} timeframe")
        return df
    
    @staticmethod
    def calculate_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.DataFrame:
        """
        MACD (Moving Average Convergence Divergence) を計算
        
        【計算方法】
        1. MACD Line = 短期EMA(12) - 長期EMA(26)
        2. Signal Line = MACD Lineの9日EMA
        3. Histogram = MACD Line - Signal Line
        
        【解釈】
        - MACD > Signal: 買いシグナル（ゴールデンクロス）
        - MACD < Signal: 売りシグナル（デッドクロス）
        
        Args:
            df: OHLCVデータ
            fast: 短期EMA期間（デフォルト: 12）
            slow: 長期EMA期間（デフォルト: 26）
            signal: シグナルライン期間（デフォルト: 9）
        
        Returns:
            MACDを追加したデータフレーム
        """
        # 短期EMAと長期EMAを計算
        exp1 = df['Close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['Close'].ewm(span=slow, adjust=False).mean()
        
        # MACD Line = 短期EMA - 長期EMA
        df[f'MACD_{fast}_{slow}_{signal}'] = exp1 - exp2
        
        # Signal Line = MACD Lineの移動平均
        df[f'MACDs_{fast}_{slow}_{signal}'] = df[f'MACD_{fast}_{slow}_{signal}'].ewm(span=signal, adjust=False).mean()
        
        # Histogram = MACD Line - Signal Line
        df[f'MACDh_{fast}_{slow}_{signal}'] = df[f'MACD_{fast}_{slow}_{signal}'] - df[f'MACDs_{fast}_{slow}_{signal}']
        
        logger.debug("Calculated MACD")
        return df
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        RSI (Relative Strength Index) を計算
        
        【計算方法】
        1. 価格変動 = 当日終値 - 前日終値
        2. 上昇幅の平均 = 上昇した日の変動幅の平均
        3. 下落幅の平均 = 下落した日の変動幅の平均
        4. RS = 上昇幅の平均 / 下落幅の平均
        5. RSI = 100 - (100 / (1 + RS))
        
        【解釈】
        - RSI > 70: 買われすぎ（売りシグナル）
        - RSI < 30: 売られすぎ（買いシグナル）
        
        Args:
            df: OHLCVデータ
            period: RSI期間（デフォルト: 14日）
        
        Returns:
            RSIを追加したデータフレーム
        """
        # 前日比の価格変動を計算
        delta = df['Close'].diff()
        
        # 上昇幅（正の変動のみ）の移動平均
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        
        # 下落幅（負の変動のみ、絶対値）の移動平均
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # RS (Relative Strength) = 上昇幅 / 下落幅
        rs = gain / loss
        
        # RSI計算: 0-100の範囲に正規化
        df[f'RSI_{period}'] = 100 - (100 / (1 + rs))
        
        logger.debug(f"Calculated RSI_{period}")
        return df
    
    @staticmethod
    def calculate_rci(df: pd.DataFrame, period: int = 9) -> pd.DataFrame:
        """
        RCI (Rank Correlation Index) を計算（ベクトル化版）
        
        【計算方法】
        1. 日付順位: 新しい日ほど大きい（1, 2, 3, ...）
        2. 価格順位: 高い価格ほど大きい
        3. 順位差の二乗和 = Σ(日付順位 - 価格順位)²
        4. RCI = (1 - 6×順位差の二乗和 / (期間×(期間²-1))) × 100
        
        【解釈】
        - RCI > +80: 買われすぎ
        - RCI < -80: 売られすぎ
        - RCIのゴールデンクロス/デッドクロス: トレンド転換
        
        Args:
            df: OHLCVデータ
            period: RCI期間（デフォルト: 9日）
        
        Returns:
            RCIを追加したデータフレーム
        """
        from scipy.stats import rankdata
        
        def rci_single_window(window_values):
            """単一ウィンドウのRCI計算"""
            n = len(window_values)
            if n < period:
                return np.nan
            
            # 日付順位（1, 2, 3, ..., period）- 新しい方が大きい
            date_rank = np.arange(1, period + 1)
            
            # 価格順位（高い方が大きい）
            price_rank = rankdata(window_values, method='ordinal')
            
            # 順位差の二乗和を計算
            d_squared_sum = np.sum((date_rank - price_rank) ** 2)
            
            # RCI計算式: スピアマンの順位相関係数を-100～+100に変換
            rci_value = (1 - (6 * d_squared_sum) / (period * (period ** 2 - 1))) * 100
            return rci_value
        
        # rolling.applyでベクトル化
        df[f'RCI_{period}'] = df['Close'].rolling(
            window=period, 
            min_periods=period
        ).apply(rci_single_window, raw=True)
        
        logger.debug(f"Calculated RCI_{period}")
        return df
    
    @staticmethod
    def calculate_bollinger_bands(
        df: pd.DataFrame, 
        period: int = 20, 
        std: float = 2.0
    ) -> pd.DataFrame:
        """
        ボリンジャーバンド (Bollinger Bands) を計算
        
        【計算方法】
        1. 中心線 (BBM) = 期間の単純移動平均 (SMA)
        2. 上限線 (BBU) = 中心線 + (標準偏差 × σ倍数)
        3. 下限線 (BBL) = 中心線 - (標準偏差 × σ倍数)
        
        【解釈】
        - 価格が上限線に接触: 買われすぎ
        - 価格が下限線に接触: 売られすぎ
        - バンド幅の拡大: ボラティリティ増加
        - バンド幅の縮小: ボラティリティ減少
        
        Args:
            df: OHLCVデータ
            period: 期間（デフォルト: 20日）
            std: 標準偏差の倍数（デフォルト: 2σ、3σで99.7%をカバー）
        
        Returns:
            ボリンジャーバンドを追加したデータフレーム
        """
        # 中心線: 単純移動平均
        sma = df['Close'].rolling(window=period).mean()
        
        # 標準偏差を計算
        rolling_std = df['Close'].rolling(window=period).std()
        
        # 下限線 = 中心線 - (標準偏差 × σ倍数)
        df[f'BBL_{period}_{std}'] = sma - (rolling_std * std)
        
        # 中心線
        df[f'BBM_{period}_{std}'] = sma
        
        # 上限線 = 中心線 + (標準偏差 × σ倍数)
        df[f'BBU_{period}_{std}'] = sma + (rolling_std * std)
        
        logger.debug(f"Calculated Bollinger Bands (period={period}, std={std})")
        return df
    
    @staticmethod
    def calculate_volume_ma(df: pd.DataFrame, period: int = 25) -> pd.DataFrame:
        """
        出来高移動平均を計算
        
        【計算方法】
        出来高の単純移動平均
        
        【解釈】
        - 出来高 > 出来高MA: 取引活発（トレンド継続の可能性）
        - 出来高 < 出来高MA: 取引低調（トレンド転換の可能性）
        
        Args:
            df: OHLCVデータ
            period: 期間（デフォルト: 25日）
        
        Returns:
            出来高移動平均を追加したデータフレーム
        """
        # 出来高の単純移動平均
        df[f'Volume_MA_{period}'] = df['Volume'].rolling(window=period).mean()
        
        logger.debug(f"Calculated Volume MA_{period}")
        return df
    
    @staticmethod
    def calculate_all_indicators(
        df: pd.DataFrame, 
        timeframe: str = 'daily'
    ) -> pd.DataFrame:
        """
        全てのテクニカル指標を一括計算
        
        【計算する指標】
        1. 移動平均 (SMA, EMA): トレンド判定
        2. MACD: トレンド転換シグナル
        3. RSI: 買われすぎ/売られすぎ判定
        4. RCI (短期・長期): トレンド強度と転換
        5. ボリンジャーバンド (3σ): ボラティリティとレンジ
        6. 出来高移動平均: 取引活発度
        
        Args:
            df: OHLCVデータ
            timeframe: 時間足（'daily', 'weekly', 'monthly'）
        
        Returns:
            全指標を追加したデータフレーム
        """
        # 移動平均（時間足に応じた期間）
        df = TechnicalIndicators.calculate_ma(df, timeframe)
        
        # MACD（12-26-9が標準）
        df = TechnicalIndicators.calculate_macd(df)
        
        # RSI（14日が標準）
        df = TechnicalIndicators.calculate_rsi(df, period=14)
        
        # RCI（短期9日、長期26日）
        df = TechnicalIndicators.calculate_rci(df, period=9)
        df = TechnicalIndicators.calculate_rci(df, period=26)
        
        # ボリンジャーバンド（20日、3σで99.7%カバー）
        df = TechnicalIndicators.calculate_bollinger_bands(df, period=20, std=3.0)
        
        # 出来高移動平均（25日）
        df = TechnicalIndicators.calculate_volume_ma(df, period=25)
        
        logger.info(f"Calculated all indicators for {timeframe} timeframe")
        return df
