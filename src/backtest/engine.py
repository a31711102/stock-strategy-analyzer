"""
バックテストエンジン

投資手法のシグナルに基づいて仮想取引を実行し、パフォーマンスを評価

保有期間制限:
- 原則: 2週間以内の取引を有効とする
- 最大: 1か月で強制決済
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import logging
import yaml

from .metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """バックテスト結果"""
    stock_code: str
    strategy_name: str
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    num_trades: int
    trades: List[Dict]              # 全取引
    equity_curve: pd.Series
    signals: pd.Series
    # 保有期間による分類
    valid_trades: List[Dict] = field(default_factory=list)     # 有効取引（2週間以内）
    forced_trades: List[Dict] = field(default_factory=list)    # 強制決済取引
    excluded_trades: List[Dict] = field(default_factory=list)  # 除外取引（2週間超・シグナル決済、参考情報）


class BacktestEngine:
    """バックテストエンジン"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Args:
            config_path: 設定ファイルのパス
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        self.initial_capital = config['backtest']['initial_capital']
        self.cash_commission = config['backtest']['cash_commission_rate']
        self.cash_slippage = config['backtest']['cash_slippage']
        self.margin_commission = config['backtest']['margin_commission_rate']
        self.margin_lending_rate = config['backtest']['margin_lending_rate']
        self.margin_slippage = config['backtest']['margin_slippage']
        
        # 高速化: データ期間制限
        self.max_years = config['backtest'].get('max_years')
        
        # 保有期間制限
        holding_period = config['backtest'].get('holding_period', {})
        self.target_holding_days = holding_period.get('target_days', 14)  # 原則2週間
        self.max_holding_days = holding_period.get('max_days', 30)        # 最大1か月
        
        # トレーリングストップ設定
        trailing_stop = config['backtest'].get('trailing_stop', {})
        self.trailing_stop_enabled = trailing_stop.get('enabled', True)
        self.trailing_stop_long = trailing_stop.get('long_threshold', 0.10)   # ロング: -10%
        self.trailing_stop_short = trailing_stop.get('short_threshold', 0.10) # ショート: +10%
        
        # 高速化: ベクトル化版を使用するか（デフォルト: True）
        self.use_vectorized = config['backtest'].get('use_vectorized', True)
    
    def run_backtest(
        self,
        df: pd.DataFrame,
        strategy,
        stock_code: str
    ) -> BacktestResult:
        """
        バックテストを実行
        
        Args:
            df: テクニカル指標を含むOHLCVデータ
            strategy: 投資手法インスタンス
            stock_code: 銘柄コード
        
        Returns:
            バックテスト結果
        """
        logger.info(f"Running backtest for {stock_code} with {strategy.name()}")
        
        # 高速化: データ期間制限
        if self.max_years:
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=365 * self.max_years)
            original_len = len(df)
            df = df[df.index >= cutoff_date]
            logger.info(f"Data limited to last {self.max_years} years: {original_len} -> {len(df)} rows")
        
        # シグナル生成
        signals = strategy.generate_signals(df)
        
        # 手法タイプに応じた手数料設定
        if strategy.strategy_type() == 'long':
            commission = self.cash_commission
            slippage = self.cash_slippage
            lending_rate = 0.0
        else:  # short
            commission = self.margin_commission
            slippage = self.margin_slippage
            lending_rate = self.margin_lending_rate
        
        # 取引実行
        # [高速化] use_vectorized=True の場合、ベクトル化版を使用
        if self.use_vectorized:
            trades, equity_curve = self._execute_trades_vectorized(
                df, 
                signals, 
                commission, 
                slippage,
                lending_rate,
                strategy.strategy_type()
            )
        else:
            # 従来版（互換性維持用）
            trades, equity_curve = self._execute_trades(
                df, 
                signals, 
                commission, 
                slippage,
                lending_rate,
                strategy.strategy_type()
            )
        
        # 取引を保有期間で分類
        valid_trades, forced_trades, excluded_trades = self._classify_trades(trades)
        
        # リターン計算（有効取引ベースの資産推移を再計算）
        valid_equity_curve = self._calculate_valid_equity_curve(
            df, valid_trades, commission, slippage, lending_rate, strategy.strategy_type()
        )
        returns = valid_equity_curve.pct_change().fillna(0)
        
        # パフォーマンス指標計算（有効取引のみで計算）
        metrics = PerformanceMetrics.calculate_all_metrics(
            valid_equity_curve,
            returns,
            valid_trades,
            len(df)
        )
        
        result = BacktestResult(
            stock_code=stock_code,
            strategy_name=strategy.name(),
            total_return=metrics['total_return'],
            annual_return=metrics['annual_return'],
            sharpe_ratio=metrics['sharpe_ratio'],
            max_drawdown=metrics['max_drawdown'],
            win_rate=metrics['win_rate'],
            profit_factor=metrics['profit_factor'],
            num_trades=metrics['num_trades'],
            trades=trades,
            equity_curve=equity_curve,
            signals=signals,
            valid_trades=valid_trades,
            forced_trades=forced_trades,
            excluded_trades=excluded_trades
        )
        
        logger.info(f"Backtest completed: {len(valid_trades)} valid trades, "
                   f"{len(forced_trades)} forced, {len(excluded_trades)} excluded, "
                   f"{metrics['total_return']:.2f}% return")
        
        return result
    
    def _classify_trades(self, trades: List[Dict]) -> tuple:
        """
        取引を保有期間で分類（ベクトル化版）
        
        Args:
            trades: 全取引リスト
        
        Returns:
            (valid_trades, forced_trades, excluded_trades)
        """
        if not trades:
            return [], [], []
        
        # [ベクトル化] Dict ListをDataFrameに変換
        df_trades = pd.DataFrame(trades)
        
        holding_days = df_trades['holding_days'].to_numpy()
        forced_exit = df_trades['forced_exit'].to_numpy()
        
        # [ベクトル化] 条件判定をNumPy演算で一括実行
        valid_mask = holding_days <= self.target_holding_days
        forced_mask = ~valid_mask & forced_exit
        excluded_mask = ~valid_mask & ~forced_exit
        
        # マスクで分類してリストに戻す
        valid_trades = df_trades[valid_mask].to_dict('records')
        forced_trades = df_trades[forced_mask].to_dict('records')
        excluded_trades = df_trades[excluded_mask].to_dict('records')
        
        return valid_trades, forced_trades, excluded_trades
    
    def _calculate_valid_equity_curve(
        self,
        df: pd.DataFrame,
        valid_trades: List[Dict],
        commission: float,
        slippage: float,
        lending_rate: float,
        strategy_type: str
    ) -> pd.Series:
        """
        有効取引のみで資産推移を計算（ベクトル化版）
        
        Args:
            df: OHLCVデータ
            valid_trades: 有効取引リスト
            commission: 手数料率
            slippage: スリッページ率
            lending_rate: 貸株料率
            strategy_type: 'long' or 'short'
        
        Returns:
            資産推移
        """
        n = len(df)
        if not valid_trades:
            # 有効取引がない場合は初期資本を維持
            return pd.Series(np.full(n, self.initial_capital), index=df.index)
        
        # [ベクトル化] 初期化
        equity = np.full(n, self.initial_capital, dtype=float)
        prices = df['Close'].to_numpy()
        dates = df.index
        
        # 取引をentry_dateでソート
        sorted_trades = sorted(valid_trades, key=lambda x: x['entry_date'])
        
        # [ベクトル化] 各取引のインデックスを事前計算
        cash = self.initial_capital
        
        for trade in sorted_trades:
            entry_date = trade['entry_date']
            exit_date = trade['exit_date']
            entry_price = trade['entry_price']
            exit_price = trade['exit_price']
            position = trade['shares']
            holding_days = trade['holding_days']
            
            # [ベクトル化] searchsortedで高速インデックス検索
            entry_idx = dates.searchsorted(entry_date)
            exit_idx = dates.searchsorted(exit_date)
            
            # エントリー前の現金を設定
            if entry_idx > 0:
                equity[:entry_idx] = np.where(
                    equity[:entry_idx] == self.initial_capital,
                    cash,
                    equity[:entry_idx]
                )
            
            # コスト計算
            cost = position * entry_price
            entry_commission = cost * commission
            cash_after_entry = cash - cost - entry_commission
            
            # [ベクトル化] 取引期間中の含み損益をスライス代入
            trade_end = min(exit_idx + 1, n)
            if entry_idx < trade_end:
                trade_prices = prices[entry_idx:trade_end]
                if strategy_type == 'long':
                    equity[entry_idx:trade_end] = cash_after_entry + position * trade_prices
                else:
                    # short: 含み損益 = position * (entry_price - current_price)
                    equity[entry_idx:trade_end] = cash_after_entry + position * (entry_price - trade_prices)
            
            # 決済後の現金を計算
            proceeds = position * exit_price
            exit_commission = proceeds * commission
            if strategy_type == 'short':
                lending_cost = position * entry_price * lending_rate * (holding_days / 365)
            else:
                lending_cost = 0
            
            cash = cash_after_entry + proceeds - exit_commission - lending_cost
            
            # [ベクトル化] 取引終了後の現金を設定
            if exit_idx + 1 < n:
                equity[exit_idx + 1:] = cash
        
        return pd.Series(equity, index=df.index)
    
    def _execute_trades(
        self,
        df: pd.DataFrame,
        signals: pd.Series,
        commission: float,
        slippage: float,
        lending_rate: float,
        strategy_type: str
    ) -> tuple:
        """
        取引を実行
        
        Args:
            df: OHLCVデータ
            signals: 売買シグナル
            commission: 手数料率
            slippage: スリッページ率
            lending_rate: 貸株料率（年率、空売りのみ）
            strategy_type: 'long' or 'short'
        
        Returns:
            (取引履歴, 資産推移)
        """
        cash = self.initial_capital
        position = 0  # 保有株数
        entry_price = 0
        entry_date = None
        trades = []
        equity = []
        
        for i in range(len(df)):
            date = df.index[i]
            price = df['Close'].iloc[i]
            signal = signals.iloc[i]
            
            # 現在の資産価値
            if position == 0:
                current_equity = cash
            else:
                if strategy_type == 'long':
                    current_equity = cash + position * price
                else:  # short
                    # 空売りの場合、借りた株の価値変動を考慮
                    profit_loss = position * (entry_price - price)
                    current_equity = cash + profit_loss
            
            equity.append(current_equity)
            
            # ポジションがある場合、保有期間をチェック
            force_exit = False
            if position > 0 and entry_date is not None:
                holding_days = (date - entry_date).days
                if holding_days >= self.max_holding_days:
                    force_exit = True
            
            # 買いシグナル（ロング）または売りシグナル（ショート）
            if signal == 1 and position == 0:
                # エントリー
                entry_price = price * (1 + slippage)  # スリッページ考慮
                position = int(cash / entry_price)
                
                if position > 0:
                    cost = position * entry_price
                    commission_cost = cost * commission
                    cash -= (cost + commission_cost)
                    entry_date = date
                    
                    logger.debug(f"Entry at {date}: {position} shares @ {entry_price:.2f}")
            
            # 決済シグナル または 強制決済
            elif (signal == -1 or force_exit) and position > 0:
                # エグジット
                exit_price = price * (1 - slippage)  # スリッページ考慮
                proceeds = position * exit_price
                commission_cost = proceeds * commission
                
                # 空売りの場合、貸株料を計算
                if strategy_type == 'short' and entry_date is not None:
                    holding_days = (date - entry_date).days
                    lending_cost = position * entry_price * lending_rate * (holding_days / 365)
                else:
                    holding_days = (date - entry_date).days if entry_date else 0
                    lending_cost = 0
                
                cash += (proceeds - commission_cost - lending_cost)
                
                # 損益計算
                if strategy_type == 'long':
                    profit = (exit_price - entry_price) * position - commission_cost * 2
                else:  # short
                    profit = (entry_price - exit_price) * position - commission_cost * 2 - lending_cost
                
                profit_pct = (profit / (position * entry_price)) * 100
                
                # 決済理由を判定
                if force_exit:
                    exit_reason = 'forced_max'
                    forced_exit_flag = True
                else:
                    exit_reason = 'signal'
                    forced_exit_flag = False
                
                within_target = holding_days <= self.target_holding_days
                
                trades.append({
                    'entry_date': entry_date,
                    'exit_date': date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'shares': position,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'holding_days': holding_days,
                    'forced_exit': forced_exit_flag,
                    'within_target_period': within_target,
                    'exit_reason': exit_reason
                })
                
                logger.debug(f"Exit at {date}: {position} shares @ {exit_price:.2f}, "
                           f"profit: {profit:.2f} ({profit_pct:.2f}%), reason: {exit_reason}")
                
                position = 0
                entry_date = None
        
        # 最終的にポジションが残っている場合は強制決済
        if position > 0:
            final_price = df['Close'].iloc[-1]
            proceeds = position * final_price
            commission_cost = proceeds * commission
            
            if strategy_type == 'short' and entry_date is not None:
                holding_days = (df.index[-1] - entry_date).days
                lending_cost = position * entry_price * lending_rate * (holding_days / 365)
            else:
                holding_days = (df.index[-1] - entry_date).days if entry_date else 0
                lending_cost = 0
            
            cash += (proceeds - commission_cost - lending_cost)
            
            if strategy_type == 'long':
                profit = (final_price - entry_price) * position - commission_cost * 2
            else:
                profit = (entry_price - final_price) * position - commission_cost * 2 - lending_cost
            
            profit_pct = (profit / (position * entry_price)) * 100
            
            within_target = holding_days <= self.target_holding_days
            
            trades.append({
                'entry_date': entry_date,
                'exit_date': df.index[-1],
                'entry_price': entry_price,
                'exit_price': final_price,
                'shares': position,
                'profit': profit,
                'profit_pct': profit_pct,
                'holding_days': holding_days,
                'forced_exit': True,  # データ終了による強制決済
                'within_target_period': within_target,
                'exit_reason': 'end_of_data'
            })
        
        equity_curve = pd.Series(equity, index=df.index)
        
        return trades, equity_curve
    
    def _execute_trades_vectorized(
        self,
        df: pd.DataFrame,
        signals: pd.Series,
        commission: float,
        slippage: float,
        lending_rate: float,
        strategy_type: str
    ) -> tuple:
        """
        取引を実行（ベクトル化版・高速）
        
        [処理概要]
        1. シグナル変化点を検出してエントリー/エグジット候補を特定
        2. 保有期間制限（30日）による強制決済を追加
        3. 取引ペアを作成し、損益を一括計算
        4. 資産推移を計算
        
        Args:
            df: OHLCVデータ
            signals: 売買シグナル (1=エントリー, -1=エグジット, 0=なし)
            commission: 手数料率
            slippage: スリッページ率
            lending_rate: 貸株料率（年率、空売りのみ）
            strategy_type: 'long' or 'short'
        
        Returns:
            (取引履歴, 資産推移)
        """
        n = len(df)
        if n == 0:
            return [], pd.Series([], dtype=float)
        
        # [ベクトル化・事前計算] ループ外で配列を一度だけ取得
        dates = df.index.to_numpy()
        prices = df['Close'].to_numpy()
        signals_arr = signals.to_numpy()
        
        # High/Low配列の事前取得（トレーリングストップ用）
        highs = df['High'].to_numpy() if 'High' in df.columns else prices
        lows = df['Low'].to_numpy() if 'Low' in df.columns else prices
        
        # [ベクトル化] DateTimeIndexをint64（ナノ秒）に変換して高速日数計算
        dates_ns = df.index.view('int64')
        ns_per_day = 86400 * 1_000_000_000
        
        # ステップ1: エントリーシグナル(1)のインデックスを取得
        # [ベクトル化] np.whereで条件に合うインデックスを一括取得
        entry_candidates = np.where(signals_arr == 1)[0]
        
        # ステップ2: エグジットシグナル(-1)のインデックスを取得
        exit_candidates = np.where(signals_arr == -1)[0]
        
        trades = []
        cash = self.initial_capital
        
        # ステップ3: 取引ペアを作成
        # [最小ループ] エントリー候補ごとに対応するエグジットを見つける
        # 完全なベクトル化は困難（前の取引が終わるまで次の取引開始不可のため）
        current_pos = 0  # 現在の走査位置
        
        for entry_idx in entry_candidates:
            if entry_idx < current_pos:
                # 前の取引が終わっていない期間はスキップ
                continue
            
            entry_date = dates[entry_idx]
            entry_price = prices[entry_idx] * (1 + slippage)
            
            # ステップ4: エグジット候補からこのエントリー以降のものを見つける
            # [ベクトル化] searchsortedで高速検索
            exit_search_idx = np.searchsorted(exit_candidates, entry_idx, side='right')
            valid_exits = exit_candidates[exit_search_idx:]
            
            # ステップ5: 強制決済日を計算（保有期間30日制限）
            forced_exit_idx = None
            trailing_stop_idx = None
            
            # エントリー後の最高値/最安値を追跡（トレーリングストップ用）
            # [ベクトル化] NumPyの累積最大/最小値を使用
            if self.trailing_stop_enabled and entry_idx + 1 < n:
                if strategy_type == 'long':
                    # ロング: 最高値から-X%で決済
                    # [ベクトル化] 累積最大値を一括計算（事前取得済みのhighs配列を使用）
                    cummax = np.maximum.accumulate(np.maximum(highs[entry_idx+1:], entry_price))
                    trailing_stop_prices = cummax * (1 - self.trailing_stop_long)
                    # トレーリングストップに引っかかる最初のインデックスを検索
                    hit_mask = prices[entry_idx+1:] < trailing_stop_prices
                    if hit_mask.any():
                        trailing_stop_idx = entry_idx + 1 + np.argmax(hit_mask)
                else:
                    # ショート: 最安値から+X%で決済
                    # [ベクトル化] 累積最小値を一括計算（事前取得済みのlows配列を使用）
                    cummin = np.minimum.accumulate(np.minimum(lows[entry_idx+1:], entry_price))
                    trailing_stop_prices = cummin * (1 + self.trailing_stop_short)
                    # トレーリングストップに引っかかる最初のインデックスを検索
                    hit_mask = prices[entry_idx+1:] > trailing_stop_prices
                    if hit_mask.any():
                        trailing_stop_idx = entry_idx + 1 + np.argmax(hit_mask)
            
            # [ベクトル化] 強制決済日計算 - int64演算で高速日数計算
            search_end = min(entry_idx + self.max_holding_days + 2, n)
            if entry_idx + 1 < search_end:
                entry_ns = dates_ns[entry_idx]
                days_held_arr = (dates_ns[entry_idx+1:search_end] - entry_ns) // ns_per_day
                forced_mask = days_held_arr >= self.max_holding_days
                if forced_mask.any():
                    forced_exit_idx = entry_idx + 1 + np.argmax(forced_mask)


            
            # エグジットインデックスを決定（シグナル or トレーリングストップ or 強制決済 or データ終了）
            if len(valid_exits) > 0:
                signal_exit_idx = valid_exits[0]
            else:
                signal_exit_idx = n - 1  # データ終了
            
            # 優先順位: 最も早いエグジット条件を採用
            exit_idx = signal_exit_idx
            forced_exit = False
            exit_reason = 'signal'
            
            # トレーリングストップが最も早い場合
            if trailing_stop_idx is not None and trailing_stop_idx < exit_idx:
                exit_idx = trailing_stop_idx
                forced_exit = False
                exit_reason = 'trailing_stop'
            
            # 強制決済（保有期間超過）が最も早い場合
            if forced_exit_idx is not None and forced_exit_idx < exit_idx:
                exit_idx = forced_exit_idx
                forced_exit = True
                exit_reason = 'forced_max'
            
            # データ終了の場合
            if exit_idx == n - 1 and exit_reason == 'signal' and (len(valid_exits) == 0 or valid_exits[0] == n - 1):
                forced_exit = True
                exit_reason = 'end_of_data'
            
            exit_date = dates[exit_idx]
            exit_price = prices[exit_idx] * (1 - slippage)
            
            # 保有日数計算
            if hasattr(exit_date, 'days'):
                holding_days = (exit_date - entry_date).days
            else:
                holding_days = (pd.Timestamp(exit_date) - pd.Timestamp(entry_date)).days
            
            # 株数計算（現金でいくつ買えるか）
            position = int(cash / entry_price) if entry_price > 0 else 0
            if position == 0:
                current_pos = exit_idx + 1
                continue
            
            # コスト計算
            cost = position * entry_price
            entry_commission = cost * commission
            proceeds = position * exit_price
            exit_commission = proceeds * commission
            
            # 貸株料（空売りのみ）
            if strategy_type == 'short':
                lending_cost = position * entry_price * lending_rate * (holding_days / 365)
            else:
                lending_cost = 0
            
            # 損益計算
            if strategy_type == 'long':
                profit = (exit_price - entry_price) * position - (entry_commission + exit_commission)
            else:
                profit = (entry_price - exit_price) * position - (entry_commission + exit_commission) - lending_cost
            
            profit_pct = (profit / cost) * 100 if cost > 0 else 0
            within_target = holding_days <= self.target_holding_days
            
            # 取引記録
            trades.append({
                'entry_date': pd.Timestamp(entry_date),
                'exit_date': pd.Timestamp(exit_date),
                'entry_price': entry_price,
                'exit_price': exit_price,
                'shares': position,
                'profit': profit,
                'profit_pct': profit_pct,
                'holding_days': holding_days,
                'forced_exit': forced_exit,
                'within_target_period': within_target,
                'exit_reason': exit_reason
            })
            
            # 現金更新
            cash = cash - cost - entry_commission + proceeds - exit_commission - lending_cost
            current_pos = exit_idx + 1
        
        # ステップ6: 資産推移を計算（ベクトル化）
        # [ベクトル化] 取引がない日は初期資本、取引中は含み損益を計算
        equity = self._calculate_equity_from_trades_vectorized(
            df, trades, strategy_type
        )
        
        return trades, equity
    
    def _calculate_equity_from_trades_vectorized(
        self,
        df: pd.DataFrame,
        trades: List[Dict],
        strategy_type: str
    ) -> pd.Series:
        """
        取引リストから資産推移を計算（ベクトル化版・高速）
        
        [処理概要]
        - 取引期間ごとに含み損益を計算
        - 非取引期間は直前の現金残高を維持
        """
        n = len(df)
        equity = np.full(n, self.initial_capital, dtype=float)
        
        if not trades:
            return pd.Series(equity, index=df.index)
        
        dates = df.index
        prices = df['Close'].to_numpy()
        
        # 現金残高の推移を計算
        cash = self.initial_capital
        
        for trade in trades:
            entry_date = trade['entry_date']
            exit_date = trade['exit_date']
            entry_price = trade['entry_price']
            position = trade['shares']
            
            # [ベクトル化] searchsortedで高速インデックス検索
            entry_idx = dates.searchsorted(entry_date)
            exit_idx = dates.searchsorted(exit_date)
            
            # 取引開始前は現金のまま
            if entry_idx > 0:
                equity[:entry_idx] = cash
            
            # [ベクトル化] 取引期間中の含み損益をスライス代入で一括計算
            trade_end = min(exit_idx + 1, n)
            if entry_idx < trade_end:
                trade_prices = prices[entry_idx:trade_end]
                if strategy_type == 'long':
                    equity[entry_idx:trade_end] = cash - position * entry_price + position * trade_prices
                else:
                    # short: 含み損益 = position * (entry_price - current_price)
                    equity[entry_idx:trade_end] = cash + position * (entry_price - trade_prices)
            
            # 取引終了後、現金を更新
            cash = cash + trade['profit']
            
            # 取引終了後～次の取引まで
            if exit_idx < n - 1:
                equity[exit_idx + 1:] = cash
        
        return pd.Series(equity, index=df.index)
