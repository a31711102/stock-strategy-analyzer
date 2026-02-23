"""
投資手法の共通ユーティリティ関数

各手法で共通して使用する判定関数を提供
"""
import pandas as pd
import numpy as np
from typing import List


def is_bullish_candle(row: pd.Series) -> bool:
    """
    陽線判定
    
    Args:
        row: OHLCVデータの1行
    
    Returns:
        陽線の場合True
    """
    return row['Close'] > row['Open']


def is_bearish_candle(row: pd.Series) -> bool:
    """
    陰線判定
    
    Args:
        row: OHLCVデータの1行
    
    Returns:
        陰線の場合True
    """
    return row['Close'] < row['Open']


def has_long_lower_shadow(row: pd.Series, threshold: float = 2.0) -> bool:
    """
    下ヒゲが長いか判定
    
    Args:
        row: OHLCVデータの1行
        threshold: ヒゲが実体の何倍以上なら「長い」とするか
    
    Returns:
        下ヒゲが長い場合True
    """
    body = abs(row['Close'] - row['Open'])
    if body == 0:
        body = 0.01  # ゼロ除算回避
    
    lower_shadow = min(row['Close'], row['Open']) - row['Low']
    return lower_shadow > body * threshold


def has_long_upper_shadow(row: pd.Series, threshold: float = 2.0) -> bool:
    """
    上ヒゲが長いか判定
    
    Args:
        row: OHLCVデータの1行
        threshold: ヒゲが実体の何倍以上なら「長い」とするか
    
    Returns:
        上ヒゲが長い場合True
    """
    body = abs(row['Close'] - row['Open'])
    if body == 0:
        body = 0.01  # ゼロ除算回避
    
    upper_shadow = row['High'] - max(row['Close'], row['Open'])
    return upper_shadow > body * threshold


def calculate_divergence_rate(price: float, ma: float) -> float:
    """
    乖離率計算
    
    Args:
        price: 株価
        ma: 移動平均値
    
    Returns:
        乖離率（%）
    """
    if ma == 0:
        return 0.0
    return ((price - ma) / ma) * 100


def is_golden_cross(
    short_ma: float, 
    long_ma: float, 
    prev_short_ma: float, 
    prev_long_ma: float
) -> bool:
    """
    ゴールデンクロス判定
    
    Args:
        short_ma: 現在の短期移動平均
        long_ma: 現在の長期移動平均
        prev_short_ma: 前日の短期移動平均
        prev_long_ma: 前日の長期移動平均
    
    Returns:
        ゴールデンクロスの場合True
    """
    return prev_short_ma <= prev_long_ma and short_ma > long_ma


def is_dead_cross(
    short_ma: float, 
    long_ma: float, 
    prev_short_ma: float, 
    prev_long_ma: float
) -> bool:
    """
    デッドクロス判定
    
    Args:
        short_ma: 現在の短期移動平均
        long_ma: 現在の長期移動平均
        prev_short_ma: 前日の短期移動平均
        prev_long_ma: 前日の長期移動平均
    
    Returns:
        デッドクロスの場合True
    """
    return prev_short_ma >= prev_long_ma and short_ma < long_ma


def check_ma_order(ma_values: List[float], ascending: bool = True) -> bool:
    """
    移動平均線の順序チェック
    
    Args:
        ma_values: 移動平均値のリスト（短期から長期の順）
        ascending: True=昇順（短期>長期）、False=降順（長期>短期）
    
    Returns:
        順序が正しい場合True
    """
    if len(ma_values) < 2:
        return True
    
    # NaNチェック
    if any(pd.isna(val) for val in ma_values):
        return False
    
    if ascending:
        # 短期 > 長期の順序チェック
        return all(ma_values[i] > ma_values[i+1] for i in range(len(ma_values)-1))
    else:
        # 長期 > 短期の順序チェック
        return all(ma_values[i] < ma_values[i+1] for i in range(len(ma_values)-1))


def is_near_high(df: pd.DataFrame, index: int, lookback: int = 60, threshold_pct: float = 5.0) -> bool:
    """
    「そろそろ新高値」判定
    
    以前の最高値と現在株価を比較し、以下の条件を満たす場合に「そろそろ新高値」と判定:
    - 現在株価が前回高値より低い（まだ更新していない）
    - かつ、差が指定%以内
    
    Args:
        df: データフレーム
        index: チェックする行のインデックス
        lookback: 何日間の高値と比較するか
        threshold_pct: 高値との差が何%以内なら「そろそろ」とするか（デフォルト: 5.0%）
    
    Returns:
        そろそろ新高値の場合True
    """
    if index < lookback:
        return False
    
    recent_high = df['High'].iloc[max(0, index - lookback):index].max()
    current_price = df['Close'].iloc[index]
    
    if recent_high == 0:
        return False
    
    # 現在株価が前回高値以上の場合は「新高値更新」なので「そろそろ」ではない
    if current_price >= recent_high:
        return False
    
    # 差の割合を計算（前回高値 - 現在株価）
    diff_pct = ((recent_high - current_price) / recent_high) * 100
    
    # 差が指定%以内であればTrue
    return diff_pct <= threshold_pct


def is_near_low(df: pd.DataFrame, index: int, lookback: int = 60, threshold_pct: float = 5.0) -> bool:
    """
    「そろそろ新安値」判定
    
    以前の最安値と現在株価を比較し、以下の条件を満たす場合に「そろそろ新安値」と判定:
    - 現在株価が前回安値より高い（まだ更新していない）
    - かつ、差が指定%以内
    
    Args:
        df: データフレーム
        index: チェックする行のインデックス
        lookback: 何日間の安値と比較するか
        threshold_pct: 安値との差が何%以内なら「そろそろ」とするか（デフォルト: 5.0%）
    
    Returns:
        そろそろ新安値の場合True
    """
    if index < lookback:
        return False
    
    recent_low = df['Low'].iloc[max(0, index - lookback):index].min()
    current_price = df['Close'].iloc[index]
    
    if recent_low == 0:
        return False
    
    # 現在株価が前回安値以下の場合は「新安値更新」なので「そろそろ」ではない
    if current_price <= recent_low:
        return False
    
    # 差の割合を計算（現在株価 - 前回安値）
    diff_pct = ((current_price - recent_low) / recent_low) * 100
    
    # 差が指定%以内であればTrue
    return diff_pct <= threshold_pct


def is_peak(df: pd.DataFrame, index: int, window: int = 5) -> bool:
    """
    山の頂点判定
    
    Args:
        df: データフレーム
        index: チェックする行のインデックス
        window: 前後何日間と比較するか
    
    Returns:
        頂点の場合True
    """
    if index < window or index >= len(df) - window:
        return False
    
    current_high = df['High'].iloc[index]
    
    # 前後のウィンドウ内で最高値かチェック
    window_data = df['High'].iloc[index - window:index + window + 1]
    return current_high == window_data.max()


def count_consecutive_candles(df: pd.DataFrame, index: int, candle_type: str = 'bearish') -> int:
    """
    連続陰線/陽線をカウント
    
    Args:
        df: データフレーム
        index: チェックする行のインデックス
        candle_type: 'bearish'（陰線）または 'bullish'（陽線）
    
    Returns:
        連続数
    """
    count = 0
    check_func = is_bearish_candle if candle_type == 'bearish' else is_bullish_candle
    
    for i in range(index, -1, -1):
        if check_func(df.iloc[i]):
            count += 1
        else:
            break
    
    return count


def is_volume_increasing(df: pd.DataFrame, index: int, lookback: int = 1) -> bool:
    """
    出来高が増加しているか判定
    
    Args:
        df: データフレーム
        index: チェックする行のインデックス
        lookback: 何日前と比較するか
    
    Returns:
        出来高が増加している場合True
    """
    if index < lookback:
        return False
    
    current_volume = df['Volume'].iloc[index]
    prev_volume = df['Volume'].iloc[index - lookback]
    
    return current_volume > prev_volume


def get_body_size_ratio(row: pd.Series) -> float:
    """
    ローソク足の実体サイズ比率を計算
    
    Args:
        row: OHLCVデータの1行
    
    Returns:
        実体サイズ / 終値の比率
    """
    body = abs(row['Close'] - row['Open'])
    if row['Close'] == 0:
        return 0.0
    return body / row['Close']


# =============================================================================
# ベクトル化版ヘルパー関数
# =============================================================================

def is_bullish_candle_vectorized(df: pd.DataFrame) -> pd.Series:
    """
    陽線判定（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
    
    Returns:
        各行が陽線かどうかのSeries
    """
    return df['Close'] > df['Open']


def is_bearish_candle_vectorized(df: pd.DataFrame) -> pd.Series:
    """
    陰線判定（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
    
    Returns:
        各行が陰線かどうかのSeries
    """
    return df['Close'] < df['Open']


def is_volume_increasing_vectorized(df: pd.DataFrame, lookback: int = 1) -> pd.Series:
    """
    出来高が増加しているか判定（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
        lookback: 何日前と比較するか
    
    Returns:
        出来高が増加している行のSeries
    """
    return df['Volume'] > df['Volume'].shift(lookback)


def is_near_high_vectorized(
    df: pd.DataFrame, 
    lookback: int = 60, 
    threshold_pct: float = 5.0
) -> pd.Series:
    """
    「そろそろ新高値」判定（ベクトル化版）
    
    以前の最高値と現在株価を比較し、以下の条件を満たす場合に「そろそろ新高値」と判定:
    - 現在株価が前回高値より低い（まだ更新していない）
    - かつ、差が指定%以内
    
    Args:
        df: OHLCVデータのDataFrame
        lookback: 何日間の高値と比較するか
        threshold_pct: 高値との差が何%以内なら「そろそろ」とするか
    
    Returns:
        そろそろ新高値の行のSeries
    """
    # 過去lookback日間の最高値（当日を含まない）
    recent_high = df['High'].shift(1).rolling(window=lookback, min_periods=1).max()
    current_price = df['Close']
    
    # 差の割合を計算
    diff_pct = ((recent_high - current_price) / recent_high) * 100
    
    # 条件: 現在株価 < 前回高値 かつ 差が閾値以内
    return (current_price < recent_high) & (diff_pct <= threshold_pct) & (diff_pct >= 0)


def is_near_low_vectorized(
    df: pd.DataFrame, 
    lookback: int = 60, 
    threshold_pct: float = 5.0
) -> pd.Series:
    """
    「そろそろ新安値」判定（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
        lookback: 何日間の安値と比較するか
        threshold_pct: 安値との差が何%以内なら「そろそろ」とするか
    
    Returns:
        そろそろ新安値の行のSeries
    """
    # 過去lookback日間の最安値（当日を含まない）
    recent_low = df['Low'].shift(1).rolling(window=lookback, min_periods=1).min()
    current_price = df['Close']
    
    # 差の割合を計算
    diff_pct = ((current_price - recent_low) / recent_low) * 100
    
    # 条件: 現在株価 > 前回安値 かつ 差が閾値以内
    return (current_price > recent_low) & (diff_pct <= threshold_pct) & (diff_pct >= 0)


def check_ma_order_vectorized(
    df: pd.DataFrame, 
    ma_columns: List[str], 
    ascending: bool = True
) -> pd.Series:
    """
    移動平均線の順序チェック（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame（MA列を含む）
        ma_columns: チェックするMA列名のリスト（短期から長期の順）
        ascending: True=昇順（短期>長期）、False=降順（長期>短期）
    
    Returns:
        順序が正しい行のSeries
    """
    if len(ma_columns) < 2:
        return pd.Series(True, index=df.index)
    
    # 全てのMA列が存在するかチェック
    missing_cols = [col for col in ma_columns if col not in df.columns]
    if missing_cols:
        return pd.Series(False, index=df.index)
    
    # 全てのペアで順序をチェック
    result = pd.Series(True, index=df.index)
    
    for i in range(len(ma_columns) - 1):
        col1 = ma_columns[i]
        col2 = ma_columns[i + 1]
        
        if ascending:
            # 短期 > 長期
            result = result & (df[col1] > df[col2])
        else:
            # 短期 < 長期
            result = result & (df[col1] < df[col2])
        
        # NaN行はFalse
        result = result & df[col1].notna() & df[col2].notna()
    
    return result


def is_golden_cross_vectorized(
    short_ma: pd.Series,
    long_ma: pd.Series
) -> pd.Series:
    """
    ゴールデンクロス判定（ベクトル化版）
    
    Args:
        short_ma: 短期移動平均のSeries
        long_ma: 長期移動平均のSeries
    
    Returns:
        ゴールデンクロスが発生した行のSeries
    """
    prev_short = short_ma.shift(1)
    prev_long = long_ma.shift(1)
    
    return (prev_short <= prev_long) & (short_ma > long_ma)


def is_dead_cross_vectorized(
    short_ma: pd.Series,
    long_ma: pd.Series
) -> pd.Series:
    """
    デッドクロス判定（ベクトル化版）
    
    Args:
        short_ma: 短期移動平均のSeries
        long_ma: 長期移動平均のSeries
    
    Returns:
        デッドクロスが発生した行のSeries
    """
    prev_short = short_ma.shift(1)
    prev_long = long_ma.shift(1)
    
    return (prev_short >= prev_long) & (short_ma < long_ma)


def has_long_upper_shadow_vectorized(df: pd.DataFrame, threshold: float = 2.0) -> pd.Series:
    """
    上ヒゲが長いか判定（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
        threshold: ヒゲが実体の何倍以上なら「長い」とするか
    
    Returns:
        上ヒゲが長い行のSeries
    """
    body = (df['Close'] - df['Open']).abs()
    body = body.replace(0, 0.01)  # ゼロ除算回避
    
    upper_shadow = df['High'] - df[['Close', 'Open']].max(axis=1)
    return upper_shadow > body * threshold


def has_long_lower_shadow_vectorized(df: pd.DataFrame, threshold: float = 2.0) -> pd.Series:
    """
    下ヒゲが長いか判定（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
        threshold: ヒゲが実体の何倍以上なら「長い」とするか
    
    Returns:
        下ヒゲが長い行のSeries
    """
    body = (df['Close'] - df['Open']).abs()
    body = body.replace(0, 0.01)  # ゼロ除算回避
    
    lower_shadow = df[['Close', 'Open']].min(axis=1) - df['Low']
    return lower_shadow > body * threshold


def calculate_divergence_rate_vectorized(price: pd.Series, ma: pd.Series) -> pd.Series:
    """
    乖離率計算（ベクトル化版）
    
    Args:
        price: 株価のSeries
        ma: 移動平均値のSeries
    
    Returns:
        乖離率（%）のSeries
    """
    ma_safe = ma.replace(0, np.nan)
    return ((price - ma_safe) / ma_safe) * 100


def get_body_size_ratio_vectorized(df: pd.DataFrame) -> pd.Series:
    """
    ローソク足の実体サイズ比率を計算（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
    
    Returns:
        実体サイズ / 終値の比率のSeries
    """
    body = (df['Close'] - df['Open']).abs()
    close_safe = df['Close'].replace(0, np.nan)
    return body / close_safe


def count_consecutive_bearish_vectorized(df: pd.DataFrame, window: int = 3) -> pd.Series:
    """
    連続陰線をカウント（ベクトル化版）
    
    直近window日間で陰線が連続しているかチェック
    
    Args:
        df: OHLCVデータのDataFrame
        window: チェックする日数
    
    Returns:
        陰線がwindow日連続している行のSeries
    """
    is_bearish = df['Close'] < df['Open']
    # 直近window日間全てが陰線かどうか
    return is_bearish.rolling(window=window, min_periods=window).sum() == window


def count_consecutive_bullish_vectorized(df: pd.DataFrame, window: int = 2) -> pd.Series:
    """
    連続陽線をカウント（ベクトル化版）
    
    直近window日間で陽線が連続しているかチェック
    
    Args:
        df: OHLCVデータのDataFrame
        window: チェックする日数
    
    Returns:
        陽線がwindow日連続している行のSeries
    """
    is_bullish = df['Close'] > df['Open']
    # 直近window日間全てが陽線かどうか
    return is_bullish.rolling(window=window, min_periods=window).sum() == window


def is_peak_vectorized(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """
    山の頂点判定（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
        window: 前後何日間と比較するか
    
    Returns:
        頂点の行のSeries
    """
    # ローリング最大値と比較
    rolling_max = df['High'].rolling(window=window*2+1, center=True, min_periods=1).max()
    return df['High'] == rolling_max


def is_volume_ratio_above_vectorized(df: pd.DataFrame, ratio: float = 1.2) -> pd.Series:
    """
    出来高が前日比で指定倍率以上か判定（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
        ratio: 倍率の閾値
    
    Returns:
        出来高が指定倍率以上の行のSeries
    """
    prev_volume = df['Volume'].shift(1)
    return df['Volume'] >= prev_volume * ratio


def is_ma_trending_up_vectorized(ma_series: pd.Series, lookback: int = 10) -> pd.Series:
    """
    移動平均線が上向きか判定（ベクトル化版）
    
    Args:
        ma_series: 移動平均のSeries
        lookback: 何日前と比較するか
    
    Returns:
        上向きの行のSeries
    """
    return ma_series >= ma_series.shift(lookback)


def is_price_near_ma_vectorized(
    price: pd.Series, 
    ma: pd.Series, 
    threshold_pct: float = 2.0
) -> pd.Series:
    """
    株価が移動平均線の近辺にあるか判定（ベクトル化版）
    
    Args:
        price: 株価のSeries
        ma: 移動平均のSeries
        threshold_pct: 近辺と判定する閾値（%）
    
    Returns:
        近辺にある行のSeries
    """
    divergence = calculate_divergence_rate_vectorized(price, ma).abs()
    return divergence <= threshold_pct


def is_price_below_ma_near_vectorized(
    price: pd.Series,
    ma: pd.Series,
    lower_pct: float = -2.0,
    upper_pct: float = 0.0
) -> pd.Series:
    """
    株価が移動平均線のやや下にあるか判定（ベクトル化版）
    
    Args:
        price: 株価のSeries
        ma: 移動平均のSeries
        lower_pct: 下限（%）
        upper_pct: 上限（%）
    
    Returns:
        条件を満たす行のSeries
    """
    divergence = calculate_divergence_rate_vectorized(price, ma)
    return (divergence >= lower_pct) & (divergence <= upper_pct)


def count_bearish_in_window_vectorized(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    直近window日間の陰線数をカウント（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
        window: カウントする日数
    
    Returns:
        陰線数のSeries
    """
    is_bearish = (df['Close'] < df['Open']).astype(int)
    return is_bearish.rolling(window=window, min_periods=1).sum()


def generate_position_signals_vectorized(
    entry_condition: pd.Series,
    exit_condition: pd.Series
) -> pd.Series:
    """
    エントリー/エグジット条件からポジションシグナルを生成（完全ベクトル化版）
    
    [ロジック]
    - エントリー条件成立でシグナル=1（ポジション開始）
    - ポジション保有中はエグジット条件成立までシグナル=1を維持
    - エグジット条件成立時にシグナル=-1（ポジション終了）
    
    [ベクトル化アルゴリズム]
    1. エントリー候補とエグジット候補を特定
    2. 状態遷移をNumPyで計算（ポジションなし→あり→なし）
    3. 累積最大値を使用してポジション保有期間を特定
    
    Args:
        entry_condition: エントリー条件のSeries (bool)
        exit_condition: エグジット条件のSeries (bool)
    
    Returns:
        signals: シグナルのSeries (1=エントリー/保有, -1=エグジット, 0=なし)
    """
    n = len(entry_condition)
    signals = pd.Series(0, index=entry_condition.index)
    
    if n == 0:
        return signals
    
    # NumPy配列に変換（高速化）
    entry_arr = entry_condition.to_numpy().astype(bool)
    exit_arr = exit_condition.to_numpy().astype(bool)
    signal_arr = np.zeros(n, dtype=np.int32)
    
    # エントリーポイントのインデックス
    entry_indices = np.where(entry_arr)[0]
    
    if len(entry_indices) == 0:
        return signals
    
    # エグジットポイントのインデックス
    exit_indices = np.where(exit_arr)[0]
    
    # ポジション状態を効率的に計算
    # 各エントリーポイントから次のエグジットポイントまでを特定
    current_pos = 0  # 現在処理中の位置
    
    for entry_idx in entry_indices:
        if entry_idx < current_pos:
            # まだ前のポジションが終わっていない
            continue
        
        # このエントリー以降のエグジットを探す
        valid_exits = exit_indices[exit_indices > entry_idx]
        
        if len(valid_exits) > 0:
            exit_idx = valid_exits[0]
        else:
            exit_idx = n - 1  # データ終了まで保有
        
        # エントリーからエグジット直前までシグナル=1
        signal_arr[entry_idx:exit_idx] = 1
        
        # エグジットシグナル=-1
        if exit_idx < n and exit_arr[exit_idx]:
            signal_arr[exit_idx] = -1
        
        current_pos = exit_idx + 1
    
    signals = pd.Series(signal_arr, index=entry_condition.index)
    return signals


def count_consecutive_candles_vectorized(df: pd.DataFrame, candle_type: str = 'bearish') -> pd.Series:
    """
    連続陰線/陽線の数をカウント（ベクトル化版）
    
    Args:
        df: OHLCVデータのDataFrame
        candle_type: 'bearish'（陰線）または 'bullish'（陽線）
    
    Returns:
        各時点での連続数のSeries
    """
    if candle_type == 'bearish':
        is_target = df['Close'] < df['Open']
    else:
        is_target = df['Close'] > df['Open']
    
    # グループ番号を付ける（連続が途切れたらインクリメント）
    groups = (~is_target).cumsum()
    
    # 各グループ内での累積カウント
    return is_target.groupby(groups).cumsum()

