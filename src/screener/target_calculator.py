"""
第三段階: ターゲット価格・ポジションサイジング計算

責務:
- ケルトナーチャネルベースの買い指値価格（P_buy）計算
- 損切り価格（P_stop）計算
- 等リスク配分による購入株数（Qty）計算
- 必要概算資金（Capital）計算
- Proximity（現在値からの近接度）計算

やらないこと:
- 銘柄の選定（Stage1/Stage2 が担当）
- トレンド判定（TrendJudge が担当）
"""
import math
import pandas as pd
import logging
from typing import Optional
from dataclasses import dataclass

from src.screener import config
from src.screener.volatility_evaluator import VolatilityScore

logger = logging.getLogger(__name__)


@dataclass
class ScreenerResult:
    """1銘柄分のスクリーナー最終結果"""
    rank: int
    ticker: str
    name: str

    # ボラティリティ指標
    rvr: float        # 相対ボラ比 (ATR_10 / ATR_100)
    norm_atr: float   # 正規化ATR (%)

    # ターゲット価格
    target_buy: float    # 買い指値価格
    stop_loss: float     # 損切り価格
    current_price: float

    # 近接度
    proximity_pct: float   # |Close - P_buy| / Close × 100
    is_proximity_alert: bool  # proximity_pct ≦ 1.0%

    # ポジションサイジング（パラメータ依存、JSで再計算可能）
    quantity: int          # 購入株数（100株単位）
    is_sub_unit: bool      # 100株未満（未満株）フラグ
    capital: float         # 必要概算資金 (target_buy × quantity)

    # メタデータ
    atr_10: float
    sma_25: float
    avg_volume_5d: float
    status: str     # トレンド判定結果（Up/Down/Range/Sideways）

    def to_dict(self) -> dict:
        """JSON シリアライズ用辞書"""
        return {
            'rank': self.rank,
            'ticker': self.ticker,
            'name': self.name,
            'rvr': self.rvr,
            'norm_atr': self.norm_atr,
            'target_buy': self.target_buy,
            'stop_loss': self.stop_loss,
            'current_price': self.current_price,
            'proximity_pct': self.proximity_pct,
            'is_proximity_alert': self.is_proximity_alert,
            'quantity': self.quantity,
            'is_sub_unit': self.is_sub_unit,
            'capital': self.capital,
            'atr_10': self.atr_10,
            'sma_25': self.sma_25,
            'avg_volume_5d': self.avg_volume_5d,
            'status': self.status,
        }


class TargetCalculator:
    """
    ケルトナーチャネルに基づくターゲット価格と
    等リスク配分によるポジションサイジングを計算する。
    """

    def __init__(
        self,
        risk_jpy: int = config.DEFAULT_RISK_JPY,
        keltner_multiplier: float = config.KELTNER_MULTIPLIER,
        unit_shares: int = config.UNIT_SHARES,
        proximity_alert_pct: float = config.PROXIMITY_ALERT_PCT,
    ):
        self.risk_jpy = risk_jpy
        self.keltner_multiplier = keltner_multiplier
        self.unit_shares = unit_shares
        self.proximity_alert_pct = proximity_alert_pct

    def calculate(
        self,
        vol_score: VolatilityScore,
        df: pd.DataFrame,
        name: str,
        rank: int,
        status: str = "",
    ) -> Optional[ScreenerResult]:
        """
        1銘柄のターゲット計算を実行

        Args:
            vol_score: Stage2で算出済みのボラティリティスコア
            df: 指標計算済みDataFrame
            name: 銘柄名
            rank: ランキング順位
            status: トレンドステータス（TrendJudge から取得）

        Returns:
            ScreenerResult。計算不可の場合はNone。
        """
        last = df.iloc[-1]

        # SMA_25 の取得
        sma_25 = last.get('SMA_25')
        if sma_25 is None or pd.isna(sma_25):
            return None
        sma_25 = float(sma_25)

        atr_10 = vol_score.atr_10
        current_price = vol_score.close

        # --- 動的ケルトナー乗数計算 ---
        # 基準となるNorm_ATR（%）を2.0とし、案A（平方根型の減衰）を適用
        base_norm_atr = 2.0
        safe_norm_atr = max(vol_score.norm_atr, 0.1)  # 0除算防止
        dynamic_k = self.keltner_multiplier * math.sqrt(base_norm_atr / safe_norm_atr)

        # --- ケルトナーロジック ---
        # 買い指値: MA_25 - (ATR_10 × 動的乗数)
        target_buy = sma_25 - (atr_10 * dynamic_k)
        # 損切り: P_buy - (ATR_10 × 動的乗数)
        stop_loss = target_buy - (atr_10 * dynamic_k)

        # 負の価格は無効
        if target_buy <= 0 or stop_loss <= 0:
            return None

        # --- Proximity ---
        proximity_pct = abs(current_price - target_buy) / current_price * 100
        is_alert = proximity_pct <= self.proximity_alert_pct

        # --- ポジションサイジング ---
        quantity, is_sub_unit = self._calculate_quantity(atr_10, dynamic_k)
        capital = target_buy * quantity if quantity > 0 else 0.0

        # --- 出来高 ---
        vol_ma_5 = last.get('Volume_MA_5')
        avg_volume_5d = float(vol_ma_5) if vol_ma_5 is not None and pd.notna(vol_ma_5) else 0.0

        return ScreenerResult(
            rank=rank,
            ticker=vol_score.code,
            name=name,
            rvr=vol_score.rvr,
            norm_atr=vol_score.norm_atr,
            target_buy=round(target_buy, 1),
            stop_loss=round(stop_loss, 1),
            current_price=current_price,
            proximity_pct=round(proximity_pct, 2),
            is_proximity_alert=is_alert,
            quantity=quantity,
            is_sub_unit=is_sub_unit,
            capital=round(capital, 0),
            atr_10=atr_10,
            sma_25=round(sma_25, 1),
            avg_volume_5d=round(avg_volume_5d, 0),
            status=status,
        )

    def _calculate_quantity(self, atr_10: float, dynamic_k: float) -> tuple[int, bool]:
        """
        等リスク配分による株数算出

        Qty = floor(risk_jpy / (R_unit × UNIT_SHARES)) × UNIT_SHARES
        R_unit = ATR_10 × 動的乗数（1株あたりリスク額）

        Args:
            atr_10: ATR(10) の値
            dynamic_k: 動的ケルトナー乗数

        Returns:
            (株数, 未満株フラグ) のタプル。
            株数が100未満の場合は (0, True) を返す。
        """
        r_unit = atr_10 * dynamic_k
        if r_unit <= 0:
            return (0, True)

        # floor(risk_jpy / (R_unit × 100)) × 100
        lots = math.floor(self.risk_jpy / (r_unit * self.unit_shares))
        quantity = lots * self.unit_shares

        if quantity < self.unit_shares:
            return (0, True)  # 未満株

        return (quantity, False)
