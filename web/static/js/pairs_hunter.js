/**
 * Project-pairs-hunter: ペアトレード・ボード リアクティブロット計算 & テーブルソート
 */

(function () {
  'use strict';

  // --- DOM要素 ---
  const riskInput = document.getElementById('ph-risk-input');
  const riskDisplay = document.getElementById('ph-risk-display');
  const unitCheckbox = document.getElementById('ph-unit-checkbox');

  if (!riskInput || !window.PAIRS_HUNTER_DATA) {
    return;
  }

  const pairs = window.PAIRS_HUNTER_DATA.pairs || [];

  /**
   * ポジションサイジング計算（動的金額算出モデル）
   * 
   * A社の株数: Q_A = R / (Price_B * 1sigma_ratio)
   * B社の株数: Q_B = Q_A * (Price_A / Price_B)
   * 必要資金: Capital = Q_A * Price_A
   */
  function calculatePosition(riskJpy, priceA, priceB, ratioSigma) {
    const isUnit100 = unitCheckbox ? unitCheckbox.checked : false;
    const unitSize = isUnit100 ? 100 : 1;

    if (priceB <= 0 || ratioSigma <= 0) {
      return { qtyA: 0, qtyB: 0, capital: 0 };
    }

    // A社の株数（生値）
    let qtyA = riskJpy / (priceB * ratioSigma);
    
    // 単元で丸め（切り捨て）
    qtyA = Math.floor(qtyA / unitSize) * unitSize;

    if (qtyA < unitSize) {
      return { qtyA: 0, qtyB: 0, capital: 0 };
    }

    // B社の株数（生値）
    let qtyB = qtyA * (priceA / priceB);
    
    // 単元で丸め（切り捨て）
    qtyB = Math.floor(qtyB / unitSize) * unitSize;

    if (qtyB < unitSize) {
      return { qtyA: 0, qtyB: 0, capital: 0 };
    }

    // 1レッグあたりの必要資金（A社の投資額で代表）
    const capital = qtyA * priceA;

    return { qtyA, qtyB, capital };
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

    const rows = document.querySelectorAll('#ph-tbody tr[data-idx]');
    rows.forEach(function (row) {
      const idx = parseInt(row.getAttribute('data-idx'), 10);
      const pair = pairs[idx];
      if (!pair) return;

      const result = calculatePosition(
        riskJpy,
        pair.stock_a.price,
        pair.stock_b.price,
        pair.ratio_sigma
      );

      const qtyACell = row.querySelector('.js-qty-a');
      const qtyBCell = row.querySelector('.js-qty-b');
      const capCell = row.querySelector('.js-capital');
      const ratioCell = row.querySelector('.js-ratio');

      if (qtyACell) {
        if (result.qtyA === 0) {
          qtyACell.textContent = '単元未満';
          qtyACell.classList.add('sub-unit');
        } else {
          qtyACell.textContent = result.qtyA.toLocaleString() + '株';
          qtyACell.classList.remove('sub-unit');
        }
      }

      if (qtyBCell) {
        if (result.qtyB === 0) {
          qtyBCell.textContent = '単元未満';
          qtyBCell.classList.add('sub-unit');
        } else {
          qtyBCell.textContent = result.qtyB.toLocaleString() + '株';
          qtyBCell.classList.remove('sub-unit');
        }
      }

      if (capCell) {
        if (result.qtyA === 0 || result.qtyB === 0) {
          capCell.textContent = '—';
        } else {
          capCell.textContent = '¥' + Math.round(result.capital).toLocaleString();
        }
      }

      if (ratioCell) {
        if (result.qtyA === 0 || result.qtyB === 0) {
          ratioCell.textContent = '—';
        } else {
          // 実質比率 Q_A / Q_B
          const realRatio = result.qtyA / result.qtyB;
          ratioCell.textContent = realRatio.toFixed(3);
        }
      }
    });
  }

  // --- ソート機能 ---
  function getCellValue(row, key) {
    const selectorMap = {
      'rank': '.col-rank',
      'correlation': '.col-correlation',
      'pvalue': '.col-pvalue',
      'zscore': '.col-zscore',
      'qty_a': '.js-qty-a',
      'qty_b': '.js-qty-b',
      'capital': '.js-capital',
      'ratio': '.js-ratio'
    };
    const cell = row.querySelector(selectorMap[key]);
    if (!cell) return 0;

    const text = cell.textContent.trim();
    if (text === '-' || text === '—' || text === '' || text === '単元未満') {
      return -9999999;
    }

    const num = parseFloat(text.replace(/[¥,%/\s株σ+]/g, ''));
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

  document.querySelectorAll('#ph-table th.sortable').forEach(th => {
    th.addEventListener('click', handleSortClick);
  });

  // --- イベントリスナー登録 ---
  riskInput.addEventListener('input', recalculate);
  if (unitCheckbox) {
    unitCheckbox.addEventListener('change', recalculate);
  }

  // 初回計算の実行
  recalculate();
})();
