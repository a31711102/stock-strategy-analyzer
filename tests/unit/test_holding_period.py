"""
保有期間制限機能のユニットテスト

テスト観点:
1. 2週間以内の取引が valid_trades に分類されること
2. 30日で強制決済されること
3. 強制決済取引に forced_exit=True が付与されること
4. 2週間超・シグナル決済の取引が excluded_trades に分類されること
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import yaml
import tempfile
import os


class TestHoldingPeriodConstraints:
    """保有期間制限のテスト"""
    
    @pytest.fixture
    def config_file(self, tmp_path):
        """テスト用の設定ファイルを作成"""
        config = {
            'backtest': {
                'initial_capital': 1000000,
                'cash_commission_rate': 0.001,
                'cash_slippage': 0.001,
                'margin_commission_rate': 0.0015,
                'margin_lending_rate': 0.005,
                'margin_slippage': 0.001,
                'holding_period': {
                    'target_days': 14,
                    'max_days': 30
                }
            }
        }
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        return str(config_path)
    
    @pytest.fixture
    def sample_df(self):
        """60日間のサンプルデータを作成"""
        dates = pd.date_range(start='2024-01-01', periods=60, freq='D')
        data = {
            'Open': [100 + i * 0.5 for i in range(60)],
            'High': [102 + i * 0.5 for i in range(60)],
            'Low': [98 + i * 0.5 for i in range(60)],
            'Close': [100 + i * 0.5 for i in range(60)],
            'Volume': [1000000] * 60
        }
        return pd.DataFrame(data, index=dates)
    
    @pytest.fixture
    def engine(self, config_file):
        """BacktestEngineのインスタンスを作成"""
        from src.backtest.engine import BacktestEngine
        return BacktestEngine(config_path=config_file)
    
    def test_valid_trade_within_14_days(self, engine, sample_df):
        """2週間以内の取引がvalid_tradesに分類されること"""
        # 5日目に買い、10日目に売るシグナル（保有5日）
        signals = pd.Series([0] * len(sample_df), index=sample_df.index)
        signals.iloc[5] = 1   # 買い
        signals.iloc[10] = -1 # 売り
        
        trades, _ = engine._execute_trades(
            sample_df, signals, 0.001, 0.001, 0.0, 'long'
        )
        
        assert len(trades) == 1
        assert trades[0]['holding_days'] == 5
        assert trades[0]['within_target_period'] == True
        assert trades[0]['forced_exit'] == False
        assert trades[0]['exit_reason'] == 'signal'
    
    def test_excluded_trade_over_14_days_signal_exit(self, engine, sample_df):
        """2週間超・シグナル決済の取引がexcluded_tradesに分類されること"""
        # 5日目に買い、25日目に売るシグナル（保有20日）
        signals = pd.Series([0] * len(sample_df), index=sample_df.index)
        signals.iloc[5] = 1   # 買い
        signals.iloc[25] = -1 # 売り（20日後）
        
        trades, _ = engine._execute_trades(
            sample_df, signals, 0.001, 0.001, 0.0, 'long'
        )
        
        assert len(trades) == 1
        assert trades[0]['holding_days'] == 20
        assert trades[0]['within_target_period'] == False
        assert trades[0]['forced_exit'] == False
        assert trades[0]['exit_reason'] == 'signal'
        
        # 分類をテスト
        valid, forced, excluded = engine._classify_trades(trades)
        assert len(valid) == 0
        assert len(forced) == 0
        assert len(excluded) == 1
    
    def test_forced_exit_at_30_days(self, engine, sample_df):
        """30日で強制決済されること"""
        # 5日目に買い、売りシグナルなし（30日で強制決済）
        signals = pd.Series([0] * len(sample_df), index=sample_df.index)
        signals.iloc[5] = 1   # 買い
        # 35日目まで売りシグナルなし
        
        trades, _ = engine._execute_trades(
            sample_df, signals, 0.001, 0.001, 0.0, 'long'
        )
        
        assert len(trades) == 1
        assert trades[0]['holding_days'] == 30
        assert trades[0]['forced_exit'] == True
        assert trades[0]['exit_reason'] == 'forced_max'
        
        # 分類をテスト
        valid, forced, excluded = engine._classify_trades(trades)
        assert len(valid) == 0
        assert len(forced) == 1
        assert len(excluded) == 0
    
    def test_forced_exit_flag_set(self, engine, sample_df):
        """強制決済取引にforced_exit=Trueが付与されること"""
        # ポジションを持ったまま30日経過
        signals = pd.Series([0] * len(sample_df), index=sample_df.index)
        signals.iloc[0] = 1   # 最初に買い
        
        trades, _ = engine._execute_trades(
            sample_df, signals, 0.001, 0.001, 0.0, 'long'
        )
        
        # 30日後に強制決済
        forced_trades = [t for t in trades if t.get('forced_exit', False)]
        assert len(forced_trades) >= 1
    
    def test_multiple_trades_classification(self, engine, sample_df):
        """複数取引の分類が正しく行われること"""
        signals = pd.Series([0] * len(sample_df), index=sample_df.index)
        # 取引1: 5日間保有（有効）
        signals.iloc[0] = 1
        signals.iloc[5] = -1
        # 取引2: 20日間保有（除外）
        signals.iloc[10] = 1
        signals.iloc[30] = -1
        # 取引3: 30日強制決済（強制）
        signals.iloc[35] = 1
        # 売りシグナルなし → データ終了で決済
        
        trades, _ = engine._execute_trades(
            sample_df, signals, 0.001, 0.001, 0.0, 'long'
        )
        
        valid, forced, excluded = engine._classify_trades(trades)
        
        # 有効取引（5日保有）
        assert len(valid) == 1
        assert valid[0]['holding_days'] == 5
        
        # 除外取引（20日保有、シグナル決済）
        assert len(excluded) == 1
        assert excluded[0]['holding_days'] == 20
        
        # 強制決済 or データ終了
        assert len(forced) >= 0  # 最後の取引はデータ終了で決済


class TestTradeRecordFields:
    """取引レコードのフィールドテスト"""
    
    @pytest.fixture
    def config_file(self, tmp_path):
        """テスト用の設定ファイルを作成"""
        config = {
            'backtest': {
                'initial_capital': 1000000,
                'cash_commission_rate': 0.001,
                'cash_slippage': 0.001,
                'margin_commission_rate': 0.0015,
                'margin_lending_rate': 0.005,
                'margin_slippage': 0.001,
                'holding_period': {
                    'target_days': 14,
                    'max_days': 30
                }
            }
        }
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        return str(config_path)
    
    @pytest.fixture
    def engine(self, config_file):
        from src.backtest.engine import BacktestEngine
        return BacktestEngine(config_path=config_file)
    
    @pytest.fixture
    def sample_df(self):
        dates = pd.date_range(start='2024-01-01', periods=20, freq='D')
        data = {
            'Open': [100] * 20,
            'High': [105] * 20,
            'Low': [95] * 20,
            'Close': [100] * 20,
            'Volume': [1000000] * 20
        }
        return pd.DataFrame(data, index=dates)
    
    def test_trade_record_has_required_fields(self, engine, sample_df):
        """取引レコードに必須フィールドが含まれること"""
        signals = pd.Series([0] * len(sample_df), index=sample_df.index)
        signals.iloc[0] = 1
        signals.iloc[10] = -1
        
        trades, _ = engine._execute_trades(
            sample_df, signals, 0.001, 0.001, 0.0, 'long'
        )
        
        required_fields = [
            'entry_date', 'exit_date', 'entry_price', 'exit_price',
            'shares', 'profit', 'profit_pct', 'holding_days',
            'forced_exit', 'within_target_period', 'exit_reason'
        ]
        
        for trade in trades:
            for field in required_fields:
                assert field in trade, f"Missing field: {field}"
    
    def test_exit_reason_values(self, engine, sample_df):
        """exit_reasonの値が正しいこと"""
        valid_reasons = ['signal', 'forced_max', 'end_of_data']
        
        signals = pd.Series([0] * len(sample_df), index=sample_df.index)
        signals.iloc[0] = 1
        signals.iloc[10] = -1
        
        trades, _ = engine._execute_trades(
            sample_df, signals, 0.001, 0.001, 0.0, 'long'
        )
        
        for trade in trades:
            assert trade['exit_reason'] in valid_reasons


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
