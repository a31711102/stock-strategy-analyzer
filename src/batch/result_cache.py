"""
結果キャッシュモジュール

バックテスト結果をJSONL形式で保存・読み込み
WebUIでの高速表示（< 0.5秒）を実現
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class ResultCache:
    """バックテスト結果のキャッシュ管理"""
    
    def __init__(self, cache_dir: str = "./results"):
        """
        Args:
            cache_dir: キャッシュディレクトリ
        """
        self.cache_dir = Path(cache_dir)
        self.rankings_dir = self.cache_dir / "rankings"
        self.details_dir = self.cache_dir / "details"
        self.approaching_dir = self.cache_dir / "approaching"
        
        # ディレクトリ作成
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rankings_dir.mkdir(parents=True, exist_ok=True)
        self.details_dir.mkdir(parents=True, exist_ok=True)
        self.approaching_dir.mkdir(parents=True, exist_ok=True)
    
    # ==================== メタデータ ====================
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        メタデータを取得
        
        Returns:
            メタデータ辞書（存在しない場合は空辞書）
        """
        metadata_path = self.cache_dir / "metadata.json"
        if not metadata_path.exists():
            return {}
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"メタデータ読み込みエラー: {e}")
            return {}
    
    def update_metadata(self, stats: Dict[str, Any]) -> bool:
        """
        メタデータを更新
        
        Args:
            stats: 更新する統計情報
            
        Returns:
            成功時True
        """
        metadata_path = self.cache_dir / "metadata.json"
        
        # 既存のメタデータを読み込み
        metadata = self.get_metadata()
        
        # 更新
        metadata.update(stats)
        metadata['last_updated'] = datetime.now().isoformat()
        metadata['version'] = '1.0.0'
        
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"メタデータ保存エラー: {e}")
            return False
    
    # ==================== 戦略別ランキング ====================
    
    def save_ranking(self, strategy: str, rankings: List[Dict]) -> bool:
        """
        戦略別ランキングを保存（JSONL形式）
        
        Args:
            strategy: 戦略名（例: 'breakout_new_high_long'）
            rankings: ランキングデータ（スコア降順）
            
        Returns:
            成功時True
        """
        ranking_path = self.rankings_dir / f"{strategy}.jsonl"
        
        try:
            with open(ranking_path, 'w', encoding='utf-8') as f:
                for i, item in enumerate(rankings, 1):
                    item['rank'] = i
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
            
            logger.info(f"ランキング保存完了: {strategy} ({len(rankings)}件)")
            return True
        except Exception as e:
            logger.error(f"ランキング保存エラー ({strategy}): {e}")
            return False
    
    def load_ranking(
        self, 
        strategy: str, 
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict]:
        """
        戦略別ランキングを読み込み
        
        Args:
            strategy: 戦略名
            limit: 取得件数（Noneで全件）
            offset: オフセット
            
        Returns:
            ランキングデータのリスト
        """
        ranking_path = self.rankings_dir / f"{strategy}.jsonl"
        
        if not ranking_path.exists():
            logger.warning(f"ランキングファイルなし: {strategy}")
            return []
        
        rankings = []
        try:
            with open(ranking_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i < offset:
                        continue
                    if limit is not None and len(rankings) >= limit:
                        break
                    rankings.append(json.loads(line.strip()))
            
            return rankings
        except Exception as e:
            logger.error(f"ランキング読み込みエラー ({strategy}): {e}")
            return []
    
    def get_available_strategies(self) -> List[str]:
        """
        利用可能な戦略一覧を取得
        
        Returns:
            戦略名のリスト
        """
        strategies = []
        for path in self.rankings_dir.glob("*.jsonl"):
            strategies.append(path.stem)
        return sorted(strategies)
    
    # ==================== 銘柄別詳細 ====================
    
    def save_detail(self, code: str, detail: Dict) -> bool:
        """
        銘柄別詳細を保存
        
        Args:
            code: 銘柄コード
            detail: 詳細データ
            
        Returns:
            成功時True
        """
        # コードを正規化（.JPを除去）
        clean_code = str(code).replace('.JP', '').strip()
        detail_path = self.details_dir / f"{clean_code}.json"
        
        try:
            detail['updated'] = datetime.now().isoformat()
            with open(detail_path, 'w', encoding='utf-8') as f:
                json.dump(detail, ensure_ascii=False, fp=f, indent=2)
            return True
        except Exception as e:
            logger.error(f"詳細保存エラー ({code}): {e}")
            return False
    
    def load_detail(self, code: str) -> Optional[Dict]:
        """
        銘柄別詳細を読み込み
        
        Args:
            code: 銘柄コード
            
        Returns:
            詳細データ（存在しない場合はNone）
        """
        clean_code = str(code).replace('.JP', '').strip()
        detail_path = self.details_dir / f"{clean_code}.json"
        
        if not detail_path.exists():
            return None
        
        try:
            with open(detail_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"詳細読み込みエラー ({code}): {e}")
            return None
    
    def get_cached_codes(self) -> List[str]:
        """
        キャッシュ済み銘柄コード一覧を取得
        
        Returns:
            銘柄コードのリスト
        """
        codes = []
        for path in self.details_dir.glob("*.json"):
            codes.append(path.stem)
        return sorted(codes)
    
    # ==================== 進捗管理 ====================
    
    def save_progress(self, processed_codes: List[str], failed_codes: List[str]) -> bool:
        """
        バッチ処理の進捗を保存（中断再開用）
        
        Args:
            processed_codes: 処理済み銘柄コード
            failed_codes: 失敗した銘柄コード
            
        Returns:
            成功時True
        """
        progress_path = self.cache_dir / "progress.json"
        
        progress = {
            'timestamp': datetime.now().isoformat(),
            'processed_count': len(processed_codes),
            'failed_count': len(failed_codes),
            'processed_codes': processed_codes,
            'failed_codes': failed_codes
        }
        
        try:
            with open(progress_path, 'w', encoding='utf-8') as f:
                json.dump(progress, ensure_ascii=False, fp=f, indent=2)
            return True
        except Exception as e:
            logger.error(f"進捗保存エラー: {e}")
            return False
    
    def load_progress(self) -> Optional[Dict]:
        """
        バッチ処理の進捗を読み込み
        
        Returns:
            進捗データ（存在しない場合はNone）
        """
        progress_path = self.cache_dir / "progress.json"
        
        if not progress_path.exists():
            return None
        
        try:
            with open(progress_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"進捗読み込みエラー: {e}")
            return None
    
    def clear_progress(self) -> bool:
        """
        進捗ファイルを削除
        
        Returns:
            成功時True
        """
        progress_path = self.cache_dir / "progress.json"
        
        if progress_path.exists():
            try:
                progress_path.unlink()
                return True
            except Exception as e:
                logger.error(f"進捗削除エラー: {e}")
                return False
        return True
    
    # ==================== ユーティリティ ====================
    
    def clear_all(self) -> bool:
        """
        全キャッシュをクリア
        
        Returns:
            成功時True
        """
        try:
            # ランキングファイル削除
            for path in self.rankings_dir.glob("*.jsonl"):
                path.unlink()
            
            # 詳細ファイル削除
            for path in self.details_dir.glob("*.json"):
                path.unlink()
            
            # メタデータ削除
            metadata_path = self.cache_dir / "metadata.json"
            if metadata_path.exists():
                metadata_path.unlink()
            
            # 進捗削除
            self.clear_progress()
            
            logger.info("全キャッシュをクリアしました")
            return True
        except Exception as e:
            logger.error(f"キャッシュクリアエラー: {e}")
            return False
    
    # ==================== 接近シグナル ====================
    
    def save_approaching_signals(self, strategy: str, signals: List[Dict]) -> bool:
        """
        戦略別接近シグナルを保存（JSONL形式）
        
        Args:
            strategy: 戦略名
            signals: 接近シグナルデータ（スコア降順）
            
        Returns:
            成功時True
        """
        approaching_path = self.approaching_dir / f"{strategy}.jsonl"
        
        try:
            with open(approaching_path, 'w', encoding='utf-8') as f:
                for i, item in enumerate(signals, 1):
                    item['rank'] = i
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
            
            logger.info(f"接近シグナル保存完了: {strategy} ({len(signals)}件)")
            return True
        except Exception as e:
            logger.error(f"接近シグナル保存エラー ({strategy}): {e}")
            return False
    
    def load_approaching_signals(
        self, 
        strategy: str, 
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict]:
        """
        戦略別接近シグナルを読み込み
        
        Args:
            strategy: 戦略名
            limit: 取得件数（Noneで全件）
            offset: オフセット
            
        Returns:
            接近シグナルデータのリスト
        """
        approaching_path = self.approaching_dir / f"{strategy}.jsonl"
        
        if not approaching_path.exists():
            return []
        
        signals = []
        try:
            with open(approaching_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i < offset:
                        continue
                    if limit is not None and len(signals) >= limit:
                        break
                    signals.append(json.loads(line.strip()))
            
            return signals
        except Exception as e:
            logger.error(f"接近シグナル読み込みエラー ({strategy}): {e}")
            return []
    
    def get_available_approaching_strategies(self) -> List[str]:
        """
        接近シグナルが存在する戦略一覧を取得
        
        Returns:
            戦略名のリスト
        """
        strategies = []
        for path in self.approaching_dir.glob("*.jsonl"):
            strategies.append(path.stem)
        return sorted(strategies)

