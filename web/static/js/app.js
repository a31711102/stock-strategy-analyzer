/**
 * Stock Strategy Analyzer - Frontend JavaScript
 */

document.addEventListener('DOMContentLoaded', function () {
    initSearchForm();
});

/**
 * 検索フォームの初期化
 */
function initSearchForm() {
    const form = document.getElementById('search-form');
    const input = document.getElementById('stock-search');

    if (!form || !input) return;

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        const code = input.value.trim();

        if (code) {
            // 銘柄詳細ページへ遷移
            window.location.href = `/stock/${encodeURIComponent(code)}`;
        }
    });

    // キー入力時のオートコンプリート（将来拡張用の準備）
    let debounceTimer;
    input.addEventListener('input', function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const query = input.value.trim();
            if (query.length >= 2) {
                searchStocks(query);
            }
        }, 300);
    });
}

/**
 * 銘柄検索API呼び出し
 * @param {string} query - 検索クエリ
 */
async function searchStocks(query) {
    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();

        // TODO: オートコンプリートUIを実装
        console.log('Search results:', data.results);
    } catch (error) {
        console.error('Search error:', error);
    }
}

/**
 * スムーズスクロール
 * @param {string} selector - スクロール先の要素セレクタ
 */
function scrollTo(selector) {
    const element = document.querySelector(selector);
    if (element) {
        element.scrollIntoView({ behavior: 'smooth' });
    }
}
