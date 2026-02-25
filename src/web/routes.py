"""
Web UIルート定義

- / : トップページ（戦略一覧）
- /strategy/<name> : 戦略別ランキング
- /stock/<code> : 銘柄詳細
- /api/search : 銘柄検索API
- /robots.txt : クローラー禁止ファイル
"""
from flask import Flask, render_template, request, jsonify, abort, send_from_directory
from src.batch.result_cache import ResultCache
import time


def register_routes(app: Flask):
    """ルートをFlaskアプリに登録"""
    
    cache = ResultCache(app.config['RESULTS_DIR'])
    
    @app.route('/robots.txt')
    def robots_txt():
        """クローラー禁止ファイルを配信"""
        return send_from_directory(app.static_folder, 'robots.txt')
    
    @app.route('/')
    def index():
        """トップページ - 戦略一覧"""
        start = time.time()
        
        metadata = cache.get_metadata()
        strategies = cache.get_available_strategies()
        
        # 戦略情報を構築（適合度40%以上のみ表示）
        MIN_SCORE_THRESHOLD = 40.0
        strategy_info = []
        for name in strategies:
            # 上位を多めに取得してフィルタリング
            raw_rankings = cache.load_ranking(name, limit=10)
            filtered = [r for r in raw_rankings if r.get('score', 0) >= MIN_SCORE_THRESHOLD]
            top3 = filtered[:3]
            strategy_info.append({
                'name': name,
                'top3': top3
            })
        
        elapsed = time.time() - start
        
        return render_template(
            'index.html',
            strategies=strategy_info,
            metadata=metadata,
            elapsed=f"{elapsed:.3f}"
        )
    
    @app.route('/strategy/<name>')
    def strategy_ranking(name: str):
        """戦略別ランキング"""
        start = time.time()
        
        # ランキング取得（Top 30、適合度40%以上のみ）
        MIN_SCORE_THRESHOLD = 40.0
        raw_rankings = cache.load_ranking(name, limit=100)  # 多めに取得
        rankings = [r for r in raw_rankings if r.get('score', 0) >= MIN_SCORE_THRESHOLD][:30]
        
        if not rankings:
            abort(404, description=f"戦略「{name}」が見つかりません")
        
        # 利用可能な戦略一覧（ナビ用）
        strategies = cache.get_available_strategies()
        
        elapsed = time.time() - start
        
        return render_template(
            'strategy_ranking.html',
            strategy_name=name,
            rankings=rankings,
            strategies=strategies,
            elapsed=f"{elapsed:.3f}"
        )
    
    @app.route('/stock/<code>')
    def stock_detail(code: str):
        """銘柄詳細"""
        start = time.time()
        
        detail = cache.load_detail(code)
        
        if not detail:
            abort(404, description=f"銘柄コード「{code}」が見つかりません")
        
        # 戦略をスコア順にソート
        sorted_strategies = sorted(
            detail.get('strategies', {}).items(),
            key=lambda x: x[1].get('score', 0),
            reverse=True
        )
        
        elapsed = time.time() - start
        
        return render_template(
            'stock_detail.html',
            stock=detail,
            sorted_strategies=sorted_strategies,
            elapsed=f"{elapsed:.3f}"
        )
    
    @app.route('/approaching')
    def approaching_index():
        """接近シグナル一覧"""
        start = time.time()
        
        metadata = cache.get_metadata()
        strategies = cache.get_available_approaching_strategies()
        
        # 戦略情報を構築
        strategy_info = []
        for name in strategies:
            signals = cache.load_approaching_signals(name, limit=3)
            strategy_info.append({
                'name': name,
                'top3': signals
            })
        
        # ランキング戦略も表示用に取得
        ranking_strategies = cache.get_available_strategies()
        
        elapsed = time.time() - start
        
        return render_template(
            'approaching.html',
            strategies=strategy_info,
            ranking_strategies=ranking_strategies,
            metadata=metadata,
            elapsed=f"{elapsed:.3f}"
        )
    
    @app.route('/approaching/<name>')
    def approaching_strategy(name: str):
        """戦略別接近シグナル"""
        start = time.time()
        
        # 接近シグナル取得（Top 50）
        signals = cache.load_approaching_signals(name, limit=50)
        
        # 利用可能な戦略一覧（ナビ用）
        strategies = cache.get_available_approaching_strategies()
        ranking_strategies = cache.get_available_strategies()
        
        elapsed = time.time() - start
        
        return render_template(
            'approaching_strategy.html',
            strategy_name=name,
            signals=signals,
            strategies=strategies,
            ranking_strategies=ranking_strategies,
            elapsed=f"{elapsed:.3f}"
        )
    
    @app.route('/api/search')
    def search_stocks():
        """銘柄検索API"""
        query = request.args.get('q', '').strip()
        
        if not query:
            return jsonify({'results': []})
        
        # キャッシュ済み銘柄から検索
        codes = cache.get_cached_codes()
        results = []
        
        for code in codes:
            if query in code:
                detail = cache.load_detail(code)
                if detail:
                    results.append({
                        'code': code,
                        'name': detail.get('name', '')
                    })
            if len(results) >= 10:
                break
        
        return jsonify({'results': results})
    
    @app.errorhandler(404)
    def not_found(error):
        """404エラーページ"""
        return render_template(
            'error.html',
            error_code=404,
            message=str(error.description)
        ), 404
