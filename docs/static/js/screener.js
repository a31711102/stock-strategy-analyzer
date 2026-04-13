/**
 * ボラティリティ乖離スクリーナー: リアルタイム再計算
 *
 * 許容損失額 X（万円）を変更すると、
 * Quantity（購入株数）と Capital（必要概算資金）を即座に再計算する。
 *
 * 将来拡張: ATR乗数K変更時の Stop_Loss / Quantity 連動再計算
 */

(function () {
  'use strict';

  // --- DOM要素 ---
  const riskInput = document.getElementById('risk-input');
  const riskDisplay = document.getElementById('risk-display');
  const subunitCheckbox = document.getElementById('subunit-checkbox');
  if (!riskInput || !window.SCREENER_DATA) {
    return;
  }

  const stocksDynamic = window.SCREENER_DATA.stocks_dynamic || [];
  const stocksLargeCap = window.SCREENER_DATA.stocks_large_cap || [];
  const keltnerMultiplier = window.SCREENER_DATA.keltner_multiplier || 2.0;
  const UNIT_SHARES = 100;

  /**
   * 許容損失額からポジションサイズを計算
   * @param {number} riskJpy - 許容損失額（円）
   * @param {number} atr10 - ATR(10)
   * @returns {{ quantity: number, isSubUnit: boolean, capital: number }}
   */
  function calculatePosition(riskJpy, atr10, targetBuy) {
    const isSubunitAllowed = subunitCheckbox ? subunitCheckbox.checked : false;
    const currentUnit = isSubunitAllowed ? 1 : 100;
    const rUnit = atr10 * keltnerMultiplier;
    
    if (rUnit <= 0) {
      return { quantity: 0, isSubUnit: true, capital: 0 };
    }

    const lots = Math.floor(riskJpy / (rUnit * currentUnit));
    const quantity = lots * currentUnit;

    if (quantity < currentUnit) {
      return { quantity: 0, isSubUnit: true, capital: 0 };
    }

    const capital = targetBuy * quantity;
    return { quantity, isSubUnit: false, capital };
  }

  /**
   * テーブル全行を再計算
   */
  function recalculate() {
    const riskMan = parseFloat(riskInput.value);
    if (isNaN(riskMan) || riskMan <= 0) {
      return;
    }

    const riskJpy = riskMan * 10000;

    // 表示更新
    if (riskDisplay) {
      riskDisplay.textContent = riskMan.toLocaleString('ja-JP', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
      }) + '万円';
    }

    const rows = document.querySelectorAll('.screener-table tr[data-table-id][data-idx]');
    rows.forEach(function (row) {
      const tableId = row.getAttribute('data-table-id');
      const idx = parseInt(row.getAttribute('data-idx'), 10);
      
      let stock = null;
      if (tableId === 'dynamic') {
          stock = stocksDynamic[idx];
      } else if (tableId === 'large_cap') {
          stock = stocksLargeCap[idx];
      }
      if (!stock) return;

      const result = calculatePosition(riskJpy, stock.atr_10, stock.target_buy);

      const qtyCell = row.querySelector('.js-quantity');
      const capCell = row.querySelector('.js-capital');

      if (qtyCell) {
        if (result.isSubUnit) {
          qtyCell.textContent = '未満株';
          qtyCell.classList.add('sub-unit');
        } else {
          qtyCell.textContent = result.quantity.toLocaleString();
          qtyCell.classList.remove('sub-unit');
        }
      }

      if (capCell) {
        if (result.isSubUnit || result.capital === 0) {
          capCell.textContent = '-';
        } else {
          capCell.textContent = '¥' + Math.round(result.capital).toLocaleString();
        }
      }
    });
  }

  // --- イベント ---
  riskInput.addEventListener('input', recalculate);
  if (subunitCheckbox) {
      subunitCheckbox.addEventListener('change', recalculate);
  }

  // --- ソート機能 ---
  function getCellValue(row, key) {
    const selectorMap = {
      'rank': '.col-rank', 'ticker': '.col-ticker', 'rvr': '.col-rvr',
      'natr': '.col-natr', 'price': '.col-price', 'target': '.col-target',
      'prox': '.col-prox', 'qty': '.col-qty', 'stop': '.col-stop',
      'cap': '.col-cap', 'status': '.col-status'
    };
    const cell = row.querySelector(selectorMap[key]);
    if (!cell) return 0;
    
    const text = cell.textContent.trim();
    if (text === '-' || text.includes('未満株') || text === '') return -9999999;
    
    if (key === 'ticker' || key === 'status') return text;
    
    const num = parseFloat(text.replace(/[¥,% ]/g, ''));
    return isNaN(num) ? text : num;
  }

  function handleSortClick(e) {
    const th = e.currentTarget;
    const table = th.closest('table');
    const tbody = table.querySelector('tbody');
    const key = th.getAttribute('data-sort-key');
    if (!key) return;

    const isAsc = th.classList.contains('asc');
    
    table.querySelectorAll('th.sortable').forEach(el => {
      el.classList.remove('asc', 'desc');
    });

    th.classList.add(isAsc ? 'desc' : 'asc');
    const sortDir = isAsc ? -1 : 1;

    const rows = Array.from(tbody.querySelectorAll('tr[data-idx]'));
    
    rows.sort((a, b) => {
      const valA = getCellValue(a, key);
      const valB = getCellValue(b, key);
      
      // 不正値（-表示や未満株）は常に下部に流す
      if (valA === -9999999 && valB !== -9999999) return 1;
      if (valB === -9999999 && valA !== -9999999) return -1;
      if (valA === -9999999 && valB === -9999999) return 0;

      if (valA < valB) return -1 * sortDir;
      if (valA > valB) return 1 * sortDir;
      return 0;
    });

    rows.forEach(row => tbody.appendChild(row));
  }

  document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', handleSortClick);
  });

  // 初回計算
  recalculate();
})();
