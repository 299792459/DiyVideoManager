import { state } from "../core/state.js";
import { LS_CARD } from "../core/constants.js";
import { escHtml, fmtDuration, fmtSize, fmtTime } from "../core/format.js";

export function applyCardSize(px) {
  const w = Math.max(160, Math.min(480, Number(px) || 280));
  document.documentElement.style.setProperty("--grid-card-min", w + "px");
  const range = document.getElementById("cardSizeRange");
  const label = document.getElementById("cardSizeLabel");
  if (range) range.value = String(w);
  if (label) label.textContent = w + "px";
  try {
    localStorage.setItem(LS_CARD, String(w));
  } catch (e) {}
}

export function closeAllCardMoreMenus() {
  document.querySelectorAll("#videoGrid .card-more-pop").forEach(p => {
    p.classList.add("hidden");
    p.setAttribute("aria-hidden", "true");
  });
}

/**
 * @param {unknown[]} videos
 */
export function renderVideos(videos) {
  const gridEl = document.getElementById("videoGrid");
  if (!gridEl) return;

  state.currentVideos = videos;
  gridEl.innerHTML = "";
  const inRecycle = document.getElementById("showRecycleCheck")?.checked;
  if (!videos.length) {
    gridEl.innerHTML = inRecycle
      ? "<div class='empty'>回收站为空</div>"
      : "<div class='empty'>暂无视频，请先在设置中扫描目录。</div>";
    return;
  }
  videos.forEach(v => {
    const card = document.createElement("article");
    card.className = "card" + (v.recycled ? " card-recycled" : "");
    const items = v.tag_items && v.tag_items.length
      ? v.tag_items
      : (v.tags || []).map(name => ({ id: null, name }));
    const tagBlocks = items.map(item => {
      const enc = encodeURIComponent(item.name);
      const active = state.selectedTagFilters.includes(item.name) ? " tag-filter-active" : "";
      return `<button type="button" class="tag tag-filter${active}" data-filter-tag="${enc}" title="点击加入/移出筛选（多选为同时满足）">${escHtml(item.name)}</button>`;
    }).join("");
    const tagsHtml = tagBlocks || "<span class=\"tags-empty-hint muted\">暂无标签</span>";
    const tagListForMenu = items.length
      ? items
          .map(item => {
            if (item.id != null) {
              return `<div class="card-more-tag-row">
            <span class="card-more-tag-label" title="${escHtml(item.name)}">${escHtml(item.name)}</span>
            <span class="card-more-tag-btns">
              <button type="button" class="btn-mini" data-act="edit-tag" data-vid="${v.id}" data-tag-id="${item.id}">改名</button>
              <button type="button" class="btn-mini btn-mini-danger" data-act="remove-tag" data-vid="${v.id}" data-tag-id="${item.id}">移除</button>
            </span>
          </div>`;
            }
            return `<div class="card-more-tag-row card-more-tag-row-idless">
            <span class="card-more-tag-label">${escHtml(item.name)}</span>
            <span class="muted tiny">仅可筛选</span>
          </div>`;
          })
          .join("")
      : `<p class="card-more-empty muted">暂无标签</p>`;
    const extPlay = state.externalPlayerConfigured
      ? `<button type="button" data-act="external-play" data-id="${v.id}">外部播放</button>`
      : "";
    const delOrRestore = v.recycled
      ? `<button type="button" data-act="restore" data-id="${v.id}">恢复</button>`
      : `<button type="button" data-act="recycle" data-id="${v.id}">删除</button>`;
    card.innerHTML = `
          <div class="cover">
            ${v.cover_url ? `<img src="${v.cover_url}" alt="${v.filename}" />` : "<div class='no-cover'>无封面</div>"}
          </div>
          <div class="content">
            <h3 title="${v.filename}">${v.recycled ? "<span class='muted'>[回收站]</span> " : ""}${v.filename}</h3>
            <p class="meta">
              观看: <b>${v.watch_count}</b> 次 |
              时长: <b>${fmtDuration(v.duration_sec)}</b> |
              大小: <b>${fmtSize(v.size_bytes)}</b>
            </p>
            <p class="meta">修改时间: ${fmtTime(v.modified_at)}</p>
            <div class="tags tags-editable tags-row-compact">${tagsHtml}</div>
            <div class="actions actions-main">
              <button type="button" data-act="play" data-id="${v.id}">播放</button>
              <div class="card-more-wrap">
                <button type="button" class="btn-more" data-act="more-menu" title="更多操作">更多 ▾</button>
                <div class="card-more-pop hidden" role="menu" aria-hidden="true">
                  <div class="card-more-section-title">标签</div>
                  <div class="card-more-tag-list">${tagListForMenu}</div>
                  <div class="card-more-actions-inline">
                    <button type="button" data-act="add-tag" data-id="${v.id}">加标签</button>
                    <button type="button" data-act="clear-tags" data-id="${v.id}" title="移除该视频的全部标签">清标签</button>
                  </div>
                  <div class="card-more-section-title">文件</div>
                  <div class="card-more-btns">
                    ${extPlay}
                    <button type="button" data-act="reveal" data-id="${v.id}">打开位置</button>
                  </div>
                  <div class="card-more-section-title">封面</div>
                  <div class="card-more-btns">
                    <button type="button" data-act="refresh-cover" data-id="${v.id}" title="无封面时生成；已有封面则跳过">刷新封面</button>
                    <button type="button" data-act="refresh-cover-force" data-id="${v.id}" title="无论是否已有封面都重新生成">强刷封面</button>
                    <button type="button" data-act="cover" data-id="${v.id}">换封面</button>
                  </div>
                  <div class="card-more-section-title">条目</div>
                  <div class="card-more-btns">${delOrRestore}</div>
                </div>
              </div>
            </div>
          </div>
        `;
    gridEl.appendChild(card);
  });
}
