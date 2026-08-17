/**
 * pairs_hunter.js - ペアトレード・ボード
 * フィルター制御・ロット計算・テーブルソート
 */
document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  // --- データ取得 ---
  // window.PAIRS_DATA はペアオブジェクトの配列（HTMLに埋め込み済み）
  var pairs = window.PAIRS_DATA;
  if (!Array.isArray(pairs)) {
    pairs = [];
  }

  // --- DOM要素 ---
  var filterSelect  = document.getElementById('ph-filter-select');
  var countDisplay   = document.getElementById('ph-count-display');
  var noMatchBox     = document.getElementById('ph-no-match');
  var riskInput      = document.getElementById('ph-risk-input');
  var unitCheckbox   = document.getElementById('ph-unit-checkbox');

  // =====================================================
  //  フィルター機能
  // =====================================================
  function applyFilter() {
    var filterValue = filterSelect ? filterSelect.value : '2sigma';
    var rows = document.querySelectorAll('#ph-tbody tr.ph-row');
    var visibleCount = 0;
    var totalCount = rows.length;

    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var zStr = row.getAttribute('data-zscore');
      var z = parseFloat(zStr);

      if (isNaN(z)) {
        row.classList.add('ph-hidden');
        continue;
      }

      var absZ = Math.abs(z);
      var show = false;

      if (filterValue === '3sigma') {
        show = (absZ >= 3.0);
      } else if (filterValue === '2sigma') {
        show = (absZ >= 2.0);
      } else {
        show = true; // 全件表示
      }

      if (show) {
        row.classList.remove('ph-hidden');
        visibleCount++;
        var rankCell = row.querySelector('.col-rank');
        if (rankCell) rankCell.textContent = visibleCount;
      } else {
        row.classList.add('ph-hidden');
      }
    }

    // 件数表示
    if (countDisplay) {
      countDisplay.textContent = '表示: ' + visibleCount + ' 件 / 全 ' + totalCount + ' ペア';
    }

    // 0件メッセージ
    if (noMatchBox) {
      noMatchBox.style.display = (visibleCount === 0 && totalCount > 0) ? 'block' : 'none';
    }
  }

  // フィルターのchangeイベント
  if (filterSelect) {
    filterSelect.addEventListener('change', applyFilter);
  }

  // 初回フィルター適用
  applyFilter();

  // =====================================================
  //  ポジションサイジング計算
  // =====================================================
  function calculatePosition(riskJpy, priceA, priceB, ratioSigma) {
    var isUnit100 = unitCheckbox ? unitCheckbox.checked : false;
    var unitSize = isUnit100 ? 100 : 1;

    if (priceB <= 0 || ratioSigma <= 0) {
      return { qtyA: 0, qtyB: 0, capital: 0 };
    }

    var qtyA = riskJpy / (priceB * ratioSigma);
    qtyA = Math.floor(qtyA / unitSize) * unitSize;
    if (qtyA < unitSize) return { qtyA: 0, qtyB: 0, capital: 0 };

    var qtyB = qtyA * (priceA / priceB);
    qtyB = Math.floor(qtyB / unitSize) * unitSize;
    if (qtyB < unitSize) return { qtyA: 0, qtyB: 0, capital: 0 };

    return { qtyA: qtyA, qtyB: qtyB, capital: qtyA * priceA };
  }

  function recalculate() {
    if (!riskInput) return;
    var riskMan = parseFloat(riskInput.value);
    if (isNaN(riskMan) || riskMan <= 0) return;

    var riskJpy = riskMan * 10000;

    var rows = document.querySelectorAll('#ph-tbody tr.ph-row');
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var idx = parseInt(row.getAttribute('data-idx'), 10);
      var pair = pairs[idx];
      if (!pair) continue;

      var result = calculatePosition(riskJpy, pair.stock_a.price, pair.stock_b.price, pair.ratio_sigma);

      var qtyACell  = row.querySelector('.js-qty-a');
      var qtyBCell  = row.querySelector('.js-qty-b');
      var capCell   = row.querySelector('.js-capital');
      var ratioCell = row.querySelector('.js-ratio');

      if (qtyACell) {
        if (result.qtyA === 0) { qtyACell.textContent = '単元未満'; qtyACell.classList.add('sub-unit'); }
        else { qtyACell.textContent = result.qtyA.toLocaleString() + '株'; qtyACell.classList.remove('sub-unit'); }
      }
      if (qtyBCell) {
        if (result.qtyB === 0) { qtyBCell.textContent = '単元未満'; qtyBCell.classList.add('sub-unit'); }
        else { qtyBCell.textContent = result.qtyB.toLocaleString() + '株'; qtyBCell.classList.remove('sub-unit'); }
      }
      if (capCell) {
        capCell.textContent = (result.qtyA === 0 || result.qtyB === 0) ? '—' : '¥' + Math.round(result.capital).toLocaleString();
      }
      if (ratioCell) {
        ratioCell.textContent = (result.qtyA === 0 || result.qtyB === 0) ? '—' : (result.qtyA / result.qtyB).toFixed(3);
      }
    }
  }

  if (riskInput) riskInput.addEventListener('input', recalculate);
  if (unitCheckbox) unitCheckbox.addEventListener('change', recalculate);
  recalculate();

  // =====================================================
  //  テーブルソート
  // =====================================================
  function getCellValue(row, key) {
    var map = {
      'rank': '.col-rank', 'correlation': '.col-correlation',
      'pvalue': '.col-pvalue', 'zscore': '.col-zscore',
      'qty_a': '.js-qty-a', 'qty_b': '.js-qty-b',
      'capital': '.js-capital', 'ratio': '.js-ratio'
    };
    var cell = row.querySelector(map[key]);
    if (!cell) return 0;
    var text = cell.textContent.trim();
    if (text === '-' || text === '—' || text === '' || text === '単元未満') return -9999999;
    var num = parseFloat(text.replace(/[¥,%/\s株σ+]/g, ''));
    return isNaN(num) ? text : num;
  }

  function handleSortClick(e) {
    var th = e.currentTarget;
    var table = th.closest('table');
    var tbody = table.querySelector('tbody');
    var key = th.getAttribute('data-sort-key');
    if (!key) return;

    var isAsc = th.classList.contains('asc');
    table.querySelectorAll('th.sortable').forEach(function (el) { el.classList.remove('asc', 'desc'); });
    th.classList.add(isAsc ? 'desc' : 'asc');
    var sortDir = isAsc ? -1 : 1;

    var rows = Array.from(tbody.querySelectorAll('tr.ph-row'));
    rows.sort(function (a, b) {
      var valA = getCellValue(a, key);
      var valB = getCellValue(b, key);
      if (valA === -9999999 && valB !== -9999999) return 1;
      if (valB === -9999999 && valA !== -9999999) return -1;
      if (valA === -9999999 && valB === -9999999) return 0;
      if (valA < valB) return -1 * sortDir;
      if (valA > valB) return 1 * sortDir;
      return 0;
    });
    rows.forEach(function (row) { tbody.appendChild(row); });
  }

  document.querySelectorAll('#ph-table th.sortable').forEach(function (th) {
    th.addEventListener('click', handleSortClick);
  });
});
