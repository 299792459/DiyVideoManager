import { state } from "../core/state.js";
import { renderVideos } from "../ui/video-grid.js";
import { setVideoStatus } from "../ui/status.js";

export function updatePaginationUIForAi() {
  const perPage = Number(document.getElementById("perPageSelect")?.value);
  const total = state.aiFullVideos.length;
  const totalPages = Math.max(1, Math.ceil(total / perPage) || 1);
  if (state.currentPage > totalPages) state.currentPage = totalPages;
  if (state.currentPage < 1) state.currentPage = 1;
  const pageInfo = document.getElementById("pageInfo");
  const prevBtn = document.getElementById("prevPageBtn");
  const nextBtn = document.getElementById("nextPageBtn");
  if (pageInfo) {
    pageInfo.textContent = `第 ${state.currentPage} / ${totalPages} 页（共 ${total} 条，AI 结果）`;
  }
  if (prevBtn) prevBtn.disabled = state.currentPage <= 1;
  if (nextBtn) nextBtn.disabled = state.currentPage >= totalPages;
}

export function renderAiPage() {
  if (!state.aiFullVideos.length) {
    renderVideos([]);
    const pageInfo = document.getElementById("pageInfo");
    const prevBtn = document.getElementById("prevPageBtn");
    const nextBtn = document.getElementById("nextPageBtn");
    if (pageInfo) pageInfo.textContent = "第 1 / 1 页（共 0 条，AI 结果）";
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    setVideoStatus("AI 无匹配结果");
    return;
  }
  const perPage = Number(document.getElementById("perPageSelect")?.value);
  const total = state.aiFullVideos.length;
  const totalPages = Math.max(1, Math.ceil(total / perPage) || 1);
  if (state.currentPage > totalPages) state.currentPage = totalPages;
  if (state.currentPage < 1) state.currentPage = 1;
  const start = (state.currentPage - 1) * perPage;
  const slice = state.aiFullVideos.slice(start, start + perPage);
  renderVideos(slice);
  updatePaginationUIForAi();
  setVideoStatus(`本页 ${slice.length} 条（AI 结果）`);
}

export async function aiSearchVideos() {
  const question = document.getElementById("aiQuestionInput")?.value.trim() ?? "";
  const topK = Number(document.getElementById("aiTopKInput")?.value || 30);
  if (!question) {
    setVideoStatus("请输入 AI 搜索问题", true);
    return;
  }
  setVideoStatus("正在调用模型检索...");
  const r = await fetch("/api/ai/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, top_k: topK }),
  });
  const data = await r.json();
  if (!data.ok) {
    setVideoStatus(data.error || "AI 搜索失败", true);
    return;
  }
  state.aiFullVideos = data.videos || [];
  state.listMode = "ai";
  state.currentPage = 1;
  const aiReason = document.getElementById("aiReason");
  if (aiReason) aiReason.textContent = `来源: ${data.source} | ${data.reason || ""}`;
  renderAiPage();
}
