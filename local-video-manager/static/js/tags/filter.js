import { LS_TAG_FILTERS } from "../core/constants.js";
import { state } from "../core/state.js";
import { escHtml } from "../core/format.js";

export function saveTagFiltersToStorage() {
  try {
    localStorage.setItem(LS_TAG_FILTERS, JSON.stringify(state.selectedTagFilters));
  } catch (e) {}
}

export function renderTagFilterBar() {
  const box = document.getElementById("tagFilterBar");
  if (!box) return;
  if (!state.selectedTagFilters.length) {
    box.innerHTML =
      "<span class=\"muted small\">标签筛选：点击卡片上的标签可多选（<strong>同时满足</strong>）；同一标签再点一次可取消。亦可从下方下拉添加。</span>";
    return;
  }
  const chips = state.selectedTagFilters
    .map(t => {
      const enc = encodeURIComponent(t);
      return `<button type="button" class="tag-chip" data-chip-tag="${enc}">${escHtml(t)} ×</button>`;
    })
    .join("");
  box.innerHTML = `<span class="tag-bar-h">已选 ${state.selectedTagFilters.length} 个（AND）</span>${chips}<button type="button" class="btn-link" id="tagFilterClearAll">清空</button>`;
}
