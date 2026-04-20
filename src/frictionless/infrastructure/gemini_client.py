import json
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class GeminiClient:
    """
    LLMエージェント通信クラス
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        # TODO: 実際の組み込み時は google-generativeai 等を初期化
    
    def generate_summary(self, prompt: str) -> Dict[str, str]:
        """
        推奨銘柄の情報を受け取って、定性サマリー（140字）などを生成する。
        フェイルソフト：エラー時は「要約なし」を返すことで後続のバッチを死なせない。
        """
        if not self.api_key:
            logger.warning("Gemini API key is not set. Using fallback.")
            return self._fallback_response()
            
        try:
            # 実際の実装: response = genai.generate_content(...)
            # 今回はダミー通信
            is_mock_error = False 
            if is_mock_error:
                raise ValueError("JSON parse error from LLM")
                
            return {
                "summary": "AIによる最新の要約結果ダミーテキストです。",
                "risk_comment": "特に連続したリスクは見当たりません。"
            }
            
        except Exception as e:
            logger.error(f"Gemini API Error: {e}")
            return self._fallback_response()
            
    def _fallback_response(self) -> Dict[str, str]:
        return {
            "summary": "⚠️AI要約なし（取得エラーまたはタイムアウト）",
            "risk_comment": "データなし"
        }
