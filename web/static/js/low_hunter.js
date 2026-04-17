/**
 * Project-low-hunter: 黄金の指値ボード リアクティブ計算
 *
 * 許容損失額 X（万円）を変更すると、
 * Quantity（購入株数）と Capital（必要概算資金）を即座に再計算する。
 *
 * リスク定義（案B）:
 *   R_unit = prev_close - target_price
 *   Qty = floor(riskJpy / (R_unit * unitSize)) * unitSize
 */

(function () {
  'use strict';

  // --- DOM要素 ---
  const riskInput = document.getElementById('lh-risk-input');
  const riskDisplay = document.getElementById('lh-risk-display');
  const unitCheckbox = document.getElementById('lh-unit-checkbox');

  if (!riskInput || !window.LOW_HUNTER_DATA) {
    return;
  }

  const stocks = window.LOW_HUNTER_DATA.stocks || [];

  /**
   * ポジションサイジング計算（案B）
   */
  function calculatePosition(riskJpy, prevClose, targetPrice) {
    const isUnit100 = unitCheckbox ? unitCheckbox.checked : false;
    const unitSize = isUnit100 ? 100 : 1;

    const rUnit = prevClose - targetPrice;
    if (rUnit <= 0) {
      return { quantity: 0, capital: 0 };
    }

    const quantity = Math.floor(riskJpy / (rUnit * unitSize)) * unitSize;
    if (quantity < unitSize) {
      return { quantity: 0, capital: 0 };
    }

    const capital = targetPrice * quantity;
    return { quantity, capital };
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

    if (riskDisplay) {
      riskDisplay.textContent = riskMan.toLocaleString('ja-JP', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
      }) + '万円';
    }

    const rows = document.querySelectorAll('#lh-tbody tr[data-idx]');
    rows.forEach(function (row) {
      const idx = parseInt(row.getAttribute('data-idx'), 10);
      const stock = stocks[idx];
      if (!stock) return;

      const result = calculatePosition(riskJpy, stock.prev_close, stock.target_price);

      const qtyCell = row.querySelector('.js-quantity');
      const capCell = row.querySelector('.js-capital');

      if (qtyCell) {
        if (result.quantity === 0) {
          qtyCell.textContent = '-';
          qtyCell.classList.add('sub-unit');
        } else {
          qtyCell.textContent = result.quantity.toLocaleString();
          qtyCell.classList.remove('sub-unit');
        }
      }

      if (capCell) {
        if (result.quantity === 0) {
          capCell.textContent = '-';
        } else {
          capCell.textContent = '¥' + Math.round(result.capital).toLocaleString();
        }
      }
    });
  }

  // --- ソート機能 ---
  function getCellValue(row, key) {
    const selectorMap = {
      'rank': '.col-rank', 'ticker': '.col-ticker', 'winrate': '.col-winrate',
      'median': '.col-median', 'drop': '.col-drop', 'target': '.col-target',
      'qty': '.col-qty', 'cap': '.col-cap', 'beta': '.col-beta',
      'wins': '.col-wins'
    };
    const cell = row.querySelector(selectorMap[key]);
    if (!cell) return 0;

    const text = cell.textContent.trim();
    if (text === '-' || text === '') return -9999999;

    if (key === 'ticker') return text;

    const num = parseFloat(text.replace(/[¥,%/ ]/g, ''));
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

      if (valA === -9999999 && valB !== -9999999) return 1;
      if (valB === -9999999 && valA !== -9999999) return -1;
      if (valA === -9999999 && valB === -9999999) return 0;

      if (valA < valB) return -1 * sortDir;
      if (valA > valB) return 1 * sortDir;
      return 0;
    });

    rows.forEach(row => tbody.appendChild(row));
  }

  document.querySelectorAll('#lh-table th.sortable').forEach(th => {
    th.addEventListener('click', handleSortClick);
  });

  // --- イベント ---
  riskInput.addEventListener('input', recalculate);
  if (unitCheckbox) {
    unitCheckbox.addEventListener('change', recalculate);
  }

  // 初回計算
  recalculate();
})();
