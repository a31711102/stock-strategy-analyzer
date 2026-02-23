"""
Flask Web アプリケーション

バックテスト結果をWebブラウザで表示
"""
from flask import Flask
from pathlib import Path
import yaml


def create_app(config_path: str = "config.yaml") -> Flask:
    """Flaskアプリケーションファクトリ"""
    
    # 設定読み込み
    project_root = Path(__file__).parent.parent.parent
    config_file = project_root / config_path
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Flaskアプリ作成
    app = Flask(
        __name__,
        template_folder=str(project_root / 'web' / 'templates'),
        static_folder=str(project_root / 'web' / 'static')
    )
    
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    app.config['RESULTS_DIR'] = str(project_root / 'results')
    app.config['WEB_CONFIG'] = config.get('web', {})
    
    # ルート登録
    from src.web.routes import register_routes
    register_routes(app)
    
    return app


def run_dev_server():
    """開発サーバー起動"""
    project_root = Path(__file__).parent.parent.parent
    config_file = project_root / "config.yaml"
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    web_config = config.get('web', {})
    host = web_config.get('host', '0.0.0.0')
    port = web_config.get('port', 5000)
    debug = web_config.get('debug', True)
    
    app = create_app()
    print(f"Starting development server at http://localhost:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    run_dev_server()
