import { state } from "../core/state.js";
import { escHtml } from "../core/format.js";
import { setTagManageStatus } from "../ui/status.js";
import { queryVideos } from "../video/browse.js";
import { renderTagFilterBar, saveTagFiltersToStorage } from "./filter.js";

export async function loadTagsCatalog() {
  setTagManageStatus("正在加载…");
  const r = await fetch("/api/tags/catalog");
  const data = await r.json();
  if (!data.ok) {
    setTagManageStatus("加载失败", true);
    return;
  }
  state.tagCatalogList = data.tags || [];
  renderTagManageTable();
  setTagManageStatus(`共 ${state.tagCatalogList.length} 个标签`);
}

export function renderTagManageTable() {
  const tbody = document.getElementById("tagManageBody");
  const emptyEl = document.getElementById("tagManageEmpty");
  if (!tbody || !emptyEl) return;
  tbody.innerHTML = "";
  if (!state.tagCatalogList.length) {
    emptyEl.classList.remove("hidden");
    return;
  }
  emptyEl.classList.add("hidden");
  state.tagCatalogList.forEach(t => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
          <td><strong>${escHtml(t.name)}</strong></td>
          <td>${t.is_auto ? "自动" : "手动"}</td>
          <td>${t.video_count}</td>
          <td class="tag-manage-actions">
            <button type="button" data-tag-op="rename" data-tag-id="${t.id}">重命名</button>
            <button type="button" data-tag-op="delete" data-tag-id="${t.id}" class="btn-danger">删除</button>
          </td>
        `;
    tbody.appendChild(tr);
  });
}

export async function renameTagGlobal(tagId) {
  const t = state.tagCatalogList.find(x => x.id === tagId);
  if (!t) return;
  const nn = prompt("新的标签名称", t.name);
  if (nn === null) return;
  const name = nn.trim();
  if (!name) {
    setTagManageStatus("名称不能为空", true);
    return;
  }
  setTagManageStatus("正在保存…");
  const r = await fetch(`/api/tags/${tagId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await r.json();
  if (!data.ok) {
    setTagManageStatus(
      data.error === "name already exists" ? "已存在同名标签" : data.error || "重命名失败",
      true
    );
    return;
  }
  setTagManageStatus("已重命名");
  await loadTagsCatalog();
  const viewVideos = document.getElementById("viewVideos");
  if (viewVideos && !viewVideos.classList.contains("hidden")) await queryVideos(state.currentPage);
}

export async function deleteTagGlobal(tagId) {
  const t = state.tagCatalogList.find(x => x.id === tagId);
  if (!t) return;
  if (!confirm(`确定删除标签「${t.name}」？将解除 ${t.video_count} 个视频上的该标签，且不可恢复。`)) return;
  setTagManageStatus("正在删除…");
  const r = await fetch(`/api/tags/${tagId}`, { method: "DELETE" });
  const data = await r.json();
  if (!data.ok) {
    setTagManageStatus(data.error || "删除失败", true);
    return;
  }
  setTagManageStatus(`已删除，影响 ${data.affected_videos ?? 0} 个视频`);
  await loadTagsCatalog();
  state.selectedTagFilters = state.selectedTagFilters.filter(n => n !== t.name);
  saveTagFiltersToStorage();
  renderTagFilterBar();
  const viewVideos = document.getElementById("viewVideos");
  if (viewVideos && !viewVideos.classList.contains("hidden")) await queryVideos(state.currentPage);
}
