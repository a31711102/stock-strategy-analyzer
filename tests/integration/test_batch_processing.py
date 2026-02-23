"""
I3: バッチ処理の結合テスト

テスト対象: src/batch/daily_batch.py の DailyBatchProcessor

テスト観点:
- process_single_stock: キャッシュ済みデータで1銘柄の全パイプラインが動作すること
- process_single_stock: 結果の構造（code/name/strategies）が正しいこと
- process_single_stock: 存在しない銘柄では None を返すこと
- run(test_mode, limit): 少数銘柄での一括処理が正常完了すること
- load_stock_list: 銘柄リストの読み込みとETF/ETN除外が動作すること
"""
import pytest
import os

from src.batch.daily_batch import DailyBatchProcessor


# data_j.xls が存在しない環境ではスキップ
STOCK_LIST_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'data_j.xls'
)
HAS_STOCK_LIST = os.path.exists(STOCK_LIST_PATH)


@pytest.fixture
def processor():
    """バッチプロセッサ（プロジェクトルートの config.yaml 使用）"""
    return DailyBatchProcessor()


@pytest.mark.integration
class TestProcessSingleStock:
    """process_single_stock の結合テスト"""

    def test_cached_stock_returns_result(self, processor):
        """キャッシュ済み銘柄（9432: NTT）で結果が返ること"""
        code, result, approaching = processor.process_single_stock('9432', 'NTT')
        assert code == '9432'
        assert result is not None
        assert 'strategies' in result

    def test_result_has_all_strategies(self, processor):
        """結果に全8戦略のスコアが含まれること"""
        code, result, approaching = processor.process_single_stock('9432', 'NTT')
        assert result is not None
        strategies = result['strategies']
        assert len(strategies) == 8

    def test_result_structure(self, processor):
        """各戦略の結果に必要なフィールドがあること"""
        code, result, approaching = processor.process_single_stock('9432', 'NTT')
        assert result is not None

        expected_fields = [
            'score', 'win_rate', 'total_return', 'annual_return',
            'num_trades', 'max_drawdown', 'sharpe_ratio', 'profit_factor',
            'reason', 'valid_trades', 'forced_trades', 'excluded_trades',
        ]

        for strategy_name, data in result['strategies'].items():
            for field in expected_fields:
                assert field in data, (
                    f"戦略 '{strategy_name}' にフィールド '{field}' が不足"
                )

    def test_score_range(self, processor):
        """適合度スコアが 0〜100 の範囲にあること"""
        code, result, approaching = processor.process_single_stock('9432', 'NTT')
        assert result is not None

        for strategy_name, data in result['strategies'].items():
            score = data['score']
            assert 0 <= score <= 100, (
                f"戦略 '{strategy_name}' のスコアが範囲外: {score}"
            )

    def test_invalid_code_returns_none(self, processor):
        """存在しない銘柄コードでは result=None"""
        code, result, approaching = processor.process_single_stock('0000', '存在しない銘柄')
        assert result is None

    def test_approaching_signals_structure(self, processor):
        """接近シグナルが返る場合はその構造が正しいこと"""
        code, result, approaching = processor.process_single_stock('9432', 'NTT')
        # approaching は None の場合もある（シグナル接近なし）
        if approaching is not None:
            for strategy_name, signal in approaching.items():
                assert 'code' in signal
                assert 'estimated_days' in signal
                assert 'score' in signal


@pytest.mark.integration
@pytest.mark.skipif(not HAS_STOCK_LIST, reason="data_j.xls が存在しない")
class TestBatchRun:
    """run() メソッドの結合テスト"""

    def test_load_stock_list(self, processor):
        """銘柄リスト読み込みでETF/ETNが除外されること"""
        df = processor.load_stock_list()
        assert len(df) > 0
        # ETF/ETNが含まれていないこと
        market_types = df['市場区分'].str.cat(sep=' ')
        assert 'ETF' not in market_types
        assert 'ETN' not in market_types

    def test_run_test_mode(self, processor, tmp_path):
        """test_mode=True, limit=3 で3銘柄のみ処理"""
        # 結果キャッシュを一時ディレクトリに変更
        from src.batch.result_cache import ResultCache
        processor.result_cache = ResultCache(cache_dir=str(tmp_path))

        stats = processor.run(test_mode=True, limit=3)

        assert stats is not None
        assert 'total_stocks' in stats
        assert 'processed_stocks' in stats
        assert 'failed_stocks' in stats
        # 最大3銘柄処理（一部失敗もありうる）
        assert stats['processed_stocks'] + stats['failed_stocks'] <= 3
