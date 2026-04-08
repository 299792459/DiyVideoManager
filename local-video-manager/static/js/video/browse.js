import { state } from "../core/state.js";
import { renderVideos } from "../ui/video-grid.js";
import { renderTagFilterBar } from "../tags/filter.js";
import { setVideoStatus } from "../ui/status.js";
import { setSettingsStatus } from "../ui/status.js";
import { loadStatsSummary } from "../settings/stats.js";

export function updatePaginationUI(data) {
  const total = data.total != null ? data.total : (data.videos && data.videos.length) || 0;
  const page = data.page != null ? data.page : 1;
  const tp = data.total_pages != null ? data.total_pages : 1;
  const pageInfo = document.getElementById("pageInfo");
  const prevBtn = document.getElementById("prevPageBtn");
  const nextBtn = document.getElementById("nextPageBtn");
  if (pageInfo) pageInfo.textContent = `第 ${page} / ${tp} 页（共 ${total} 条）`;
  if (prevBtn) prevBtn.disabled = page <= 1;
  if (nextBtn) nextBtn.disabled = page >= tp;
}

export async function queryVideos(page) {
  const tagFilterEl = document.getElementById("tagFilter");
  if (!tagFilterEl) return;

  state.listMode = "browse";
  if (page != null && page >= 1) state.currentPage = page;
  const q = document.getElementById("searchInput")?.value.trim() ?? "";
  const sort = document.getElementById("sortSelect")?.value ?? "modified_at";
  const order = document.getElementById("orderSelect")?.value ?? "desc";
  const perPage = Number(document.getElementById("perPageSelect")?.value);
  const showR = document.getElementById("showRecycleCheck")?.checked ?? false;
  const params = new URLSearchParams({
    search: q,
    sort,
    order,
    page: String(state.currentPage),
    per_page: String(perPage),
    recycled: showR ? "1" : "0",
  });
  state.selectedTagFilters.forEach(t => params.append("tags", t));
  const r = await fetch(`/api/videos?${params.toString()}`);
  const data = await r.json();
  tagFilterEl.innerHTML =
    `<option value="">（下拉添加标签）</option>` +
    (data.tags || [])
      .map(t => `<option value="${t.name.replace(/"/g, "&quot;")}">${t.name}${t.is_auto ? " (自动)" : ""}</option>`)
      .join("");
  if (data.page != null) state.currentPage = data.page;
  renderVideos(data.videos || []);
  renderTagFilterBar();
  updatePaginationUI(data);
  const total = data.total != null ? data.total : (data.videos || []).length;
  const rb = data.recycled_view ? "（回收站）" : "";
  const tf = state.selectedTagFilters.length > 0 ? ` | 标签AND ${state.selectedTagFilters.length} 个` : "";
  setVideoStatus(
    `已加载 第 ${state.currentPage} 页，本页 ${(data.videos || []).length} 条，合计 ${total} 条${rb}${tf}`
  );
}

export async function scanVideos() {
  setSettingsStatus("正在扫描视频（仅索引，不生成封面）...");
  const r = await fetch("/api/scan", { method: "POST" });
  const data = await r.json();
  if (data.ok) {
    let msg = `扫描完成：新增 ${data.created}，更新 ${data.updated}，跳过 ${data.skipped}`;
    if (data.moved_invalid_to_recycle) {
      msg += `，无效路径已入回收站 ${data.moved_invalid_to_recycle}`;
    }
    setSettingsStatus(msg);
    const viewSettings = document.getElementById("viewSettings");
    if (viewSettings && !viewSettings.classList.contains("hidden")) loadStatsSummary();
    state.listMode = "browse";
    await queryVideos(1);
  } else setSettingsStatus("扫描失败", true);
}

export async function refreshCovers(onlyMissing) {
  setSettingsStatus(onlyMissing ? "正在批量刷新（跳过已有封面）..." : "正在批量强制刷新全部封面...");
  const r = await fetch("/api/covers/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ only_missing: onlyMissing }),
  });
  const data = await r.json();
  if (!data.ok) {
    setSettingsStatus("刷新封面失败", true);
    return;
  }
  let msg = `封面：成功 ${data.success}，失败 ${data.failed}`;
  if (data.sample_errors && data.sample_errors.length) {
    msg += " | 示例: " + data.sample_errors.join("；");
  }
  setSettingsStatus(msg, data.failed > 0);
}
