"""
ランキング再生成スクリプト

銘柄詳細データ（results/details/*.json）からランキングデータを再生成する。
シグナル接近データには手を加えない。
"""
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List


def regenerate_rankings():
    """銘柄詳細データからランキングを再生成"""
    details_dir = Path("results/details")
    rankings_dir = Path("results/rankings")
    
    if not details_dir.exists():
        print("詳細データディレクトリが見つかりません")
        return
    
    # 戦略別にデータを集計
    strategy_results: Dict[str, List[Dict]] = defaultdict(list)
    
    # すべての銘柄詳細を読み込み
    detail_files = list(details_dir.glob("*.json"))
    print(f"読み込み中: {len(detail_files)}銘柄")
    
    for detail_path in detail_files:
        try:
            with open(detail_path, 'r', encoding='utf-8') as f:
                detail = json.load(f)
            
            code = detail.get('code', detail_path.stem)
            name = detail.get('name', '')
            strategies = detail.get('strategies', {})
            
            for strategy_name, strategy_data in strategies.items():
                score = strategy_data.get('score', 0)
                strategy_results[strategy_name].append({
                    'code': code,
                    'name': name,
                    'score': score,
                    'win_rate': strategy_data.get('win_rate', 0),
                    'return': strategy_data.get('total_return', 0),
                    'trades': strategy_data.get('num_trades', 0),
                    'reason': strategy_data.get('reason', '')
                })
        except Exception as e:
            print(f"読み込みエラー ({detail_path.stem}): {e}")
    
    # 戦略別にランキングを保存
    rankings_dir.mkdir(parents=True, exist_ok=True)
    
    for strategy_name, results in strategy_results.items():
        # スコア降順でソート
        sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
        
        # ランキングファイルに保存
        ranking_path = rankings_dir / f"{strategy_name}.jsonl"
        with open(ranking_path, 'w', encoding='utf-8') as f:
            for i, item in enumerate(sorted_results, 1):
                item['rank'] = i
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        # 上位5件のスコアを確認表示
        top5_scores = [f"{r['code']}:{r['score']:.1f}%" for r in sorted_results[:5]]
        print(f"  {strategy_name}: {len(sorted_results)}件 (Top5: {', '.join(top5_scores)})")
    
    print(f"\n完了: {len(strategy_results)}戦略のランキングを再生成しました")


if __name__ == '__main__':
    regenerate_rankings()
