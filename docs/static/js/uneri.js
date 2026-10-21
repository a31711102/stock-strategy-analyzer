/**
 * うねりチャート底値買い（S/R接近監視リスト）
 * - 4つの状態別タブ切り替え（買い検討・S到達 / 監視開始 / 利確目安 / 下抜け警戒）
 * - 並び順の切り替え（S乖離率順 / 往復数順 / R上昇余地順 / 平均出来高順）
 */
(function () {
  'use strict';

  const tabButtons = document.querySelectorAll('.uneri-tab[data-tab]');
  const tabPanels = document.querySelectorAll('.uneri-tab-panel[data-panel]');
  const sortSelect = document.getElementById('uneri-sort-select');

  if (!tabButtons.length) {
    return;
  }

  function switchTab(targetTab) {
    tabButtons.forEach(function (btn) {
      const isTarget = btn.getAttribute('data-tab') === targetTab;
      btn.classList.toggle('active', isTarget);
      btn.setAttribute('aria-selected', isTarget ? 'true' : 'false');
    });

    tabPanels.forEach(function (panel) {
      const isTarget = panel.getAttribute('data-panel') === targetTab;
      panel.classList.toggle('active', isTarget);
      panel.style.display = isTarget ? '' : 'none';
    });
  }

  function sortAllPanels(sortMode) {
    const tbodies = document.querySelectorAll('.uneri-tbody');
    tbodies.forEach(function (tbody) {
      const rows = Array.from(tbody.querySelectorAll('tr.uneri-row'));
      if (!rows.length) return;

      rows.sort(function (a, b) {
        const sDistA = parseFloat(a.getAttribute('data-s-dist') || '0');
        const sDistB = parseFloat(b.getAttribute('data-s-dist') || '0');
        const cyclesA = parseFloat(a.getAttribute('data-cycles') || '0');
        const cyclesB = parseFloat(b.getAttribute('data-cycles') || '0');
        const rUpsideA = parseFloat(a.getAttribute('data-r-upside') || '0');
        const rUpsideB = parseFloat(b.getAttribute('data-r-upside') || '0');
        const volA = parseFloat(a.getAttribute('data-volume') || '0');
        const volB = parseFloat(b.getAttribute('data-volume') || '0');

        if (sortMode === 'cycles_desc') {
          if (cyclesB !== cyclesA) return cyclesB - cyclesA;
          return sDistA - sDistB;
        }
        if (sortMode === 'r_upside_desc') {
          if (rUpsideB !== rUpsideA) return rUpsideB - rUpsideA;
          return sDistA - sDistB;
        }
        if (sortMode === 'volume_desc') {
          if (volB !== volA) return volB - volA;
          return sDistA - sDistB;
        }
        // デフォルト: S乖離率の小さい順
        if (sDistA !== sDistB) return sDistA - sDistB;
        return cyclesB - cyclesA;
      });

      rows.forEach(function (row) {
        tbody.appendChild(row);
      });
    });
  }

  tabButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      const targetTab = btn.getAttribute('data-tab');
      if (targetTab) {
        switchTab(targetTab);
      }
    });
  });

  if (sortSelect) {
    sortSelect.addEventListener('change', function () {
      sortAllPanels(sortSelect.value);
    });
  }
})();
