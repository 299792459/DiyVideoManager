/**
 * 本地视频管理 SPA 入口：注册事件并启动初始化。
 * 业务逻辑按目录拆分：core / ui / video / tags / settings。
 */
import { state } from "./core/state.js";
import { LS_CARD, LS_PER_PAGE, LS_SHOW_RECYCLE, LS_TAG_FILTERS } from "./core/constants.js";
import { applyCardSize, closeAllCardMoreMenus } from "./ui/video-grid.js";
import { showView } from "./ui/nav.js";
import { setVideoStatus } from "./ui/status.js";
import { saveConfig, loadConfig } from "./settings/config.js";
import { loadStatsSummary, runStatsSample } from "./settings/stats.js";
import {
  importTagsFromFile,
  importCrawlerResult,
  probeIntentModel,
  runCrawlerPipeline,
} from "./settings/workflows.js";
import { renderTagFilterBar, saveTagFiltersToStorage } from "./tags/filter.js";
import { loadTagsCatalog, renameTagGlobal, deleteTagGlobal } from "./tags/manage.js";
import { queryVideos, scanVideos, refreshCovers } from "./video/browse.js";
import { aiSearchVideos, renderAiPage } from "./video/ai.js";
import {
  playVideo,
  exportAiData,
  refreshOneCover,
  autoGenerateTags,
  clearVideoTags,
  removeSingleTagFromVideo,
  editSingleTagOnVideo,
  addTag,
  uploadCover,
  recycleVideo,
  restoreVideo,
  openExternalPlay,
  revealVideoPath,
  purgeRecycleBin,
} from "./video/ops.js";

function attachGridHandlers(gridEl) {
  gridEl.addEventListener("click", async e => {
    const moreBtn = e.target.closest('[data-act="more-menu"]');
    if (moreBtn && gridEl.contains(moreBtn)) {
      e.stopPropagation();
      const wrap = moreBtn.closest(".card-more-wrap");
      const pop = wrap && wrap.querySelector(".card-more-pop");
      if (!pop) return;
      const wasHidden = pop.classList.contains("hidden");
      closeAllCardMoreMenus();
      if (wasHidden) {
        pop.classList.remove("hidden");
        pop.setAttribute("aria-hidden", "false");
      }
      return;
    }
    const rmTag = e.target.closest('[data-act="remove-tag"]');
    if (rmTag && gridEl.contains(rmTag)) {
      e.stopPropagation();
      const vid = Number(rmTag.getAttribute("data-vid"));
      const tid = Number(rmTag.getAttribute("data-tag-id"));
      if (vid && tid) await removeSingleTagFromVideo(vid, tid);
      return;
    }
    const edTag = e.target.closest('[data-act="edit-tag"]');
    if (edTag && gridEl.contains(edTag)) {
      e.stopPropagation();
      const vid = Number(edTag.getAttribute("data-vid"));
      const tid = Number(edTag.getAttribute("data-tag-id"));
      if (vid && tid) await editSingleTagOnVideo(vid, tid);
      return;
    }
    const tagBtn = e.target.closest("button.tag-filter");
    if (tagBtn && gridEl.contains(tagBtn)) {
      const raw = tagBtn.getAttribute("data-filter-tag");
      if (raw) {
        try {
          const tagName = decodeURIComponent(raw);
          const idx = state.selectedTagFilters.indexOf(tagName);
          if (idx >= 0) state.selectedTagFilters.splice(idx, 1);
          else state.selectedTagFilters.push(tagName);
          saveTagFiltersToStorage();
          renderTagFilterBar();
          state.currentPage = 1;
          await queryVideos(1);
          setVideoStatus(
            state.selectedTagFilters.length
              ? `标签筛选（AND）：${state.selectedTagFilters.join("、")}`
              : "已取消该标签或清空相关筛选"
          );
        } catch (err) {
          setVideoStatus("标签解析失败", true);
        }
      }
      return;
    }
    const btn = e.target.closest("button");
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const act = btn.dataset.act;
    if (act === "play") await playVideo(id);
    if (act === "external-play") await openExternalPlay(id);
    if (act === "reveal") await revealVideoPath(id);
    if (act === "recycle") {
      if (!confirm("将本条移入回收站？磁盘上的视频文件不会删除。")) return;
      await recycleVideo(id);
    }
    if (act === "restore") await restoreVideo(id);
    if (act === "add-tag") await addTag(id);
    if (act === "clear-tags") await clearVideoTags(id);
    if (act === "refresh-cover") await refreshOneCover(id, false);
    if (act === "refresh-cover-force") await refreshOneCover(id, true);
    if (act === "cover") await uploadCover(id);
  });
}

function bindGlobalListeners() {
  document.addEventListener("mousedown", e => {
    if (e.target.closest("#videoGrid .card-more-wrap")) return;
    closeAllCardMoreMenus();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeAllCardMoreMenus();
  });
}

function bindNavigation() {
  document.getElementById("navVideos")?.addEventListener("click", () => showView("videos"));
  document.getElementById("navTags")?.addEventListener("click", () => showView("tags"));
  document.getElementById("navSettings")?.addEventListener("click", () => showView("settings"));
}

function bindVideoPage() {
  document.getElementById("purgeRecycleBtn")?.addEventListener("click", purgeRecycleBin);

  document.getElementById("showRecycleCheck")?.addEventListener("change", () => {
    try {
      localStorage.setItem(LS_SHOW_RECYCLE, document.getElementById("showRecycleCheck").checked ? "1" : "0");
    } catch (e) {}
    state.currentPage = 1;
    queryVideos(1);
  });

  document.getElementById("exportTagsBtn")?.addEventListener("click", () => {
    window.open("/api/tags/export", "_blank");
  });
  document.getElementById("exportTagsReadmeBtn")?.addEventListener("click", () => {
    window.open("/api/tags/export-readme", "_blank");
  });
  document.getElementById("tagsImportPickBtn")?.addEventListener("click", () => {
    document.getElementById("tagsImportFile")?.click();
  });
  document.getElementById("tagsImportFile")?.addEventListener("change", e => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (f) importTagsFromFile(f);
  });

  document.getElementById("crawlerRunPickBtn")?.addEventListener("click", () => {
    document.getElementById("crawlerRunFile")?.click();
  });
  document.getElementById("crawlerRunFile")?.addEventListener("change", async e => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    await runCrawlerPipeline(f);
  });

  document.getElementById("crawlerImportPickBtn")?.addEventListener("click", () => {
    document.getElementById("crawlerImportFile")?.click();
  });
  document.getElementById("crawlerImportFile")?.addEventListener("change", e => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (f) importCrawlerResult(f);
  });

  document.getElementById("intentProbeBtn")?.addEventListener("click", probeIntentModel);

  document.getElementById("tagFilterBar")?.addEventListener("click", e => {
    const chip = e.target.closest("[data-chip-tag]");
    if (chip) {
      const name = decodeURIComponent(chip.getAttribute("data-chip-tag"));
      const i = state.selectedTagFilters.indexOf(name);
      if (i >= 0) state.selectedTagFilters.splice(i, 1);
      saveTagFiltersToStorage();
      renderTagFilterBar();
      state.currentPage = 1;
      queryVideos(1);
      return;
    }
    if (e.target.id === "tagFilterClearAll") {
      state.selectedTagFilters = [];
      saveTagFiltersToStorage();
      renderTagFilterBar();
      state.currentPage = 1;
      queryVideos(1);
    }
  });

  document.getElementById("tagFilter")?.addEventListener("change", () => {
    const tagFilterEl = document.getElementById("tagFilter");
    if (!tagFilterEl) return;
    const v = tagFilterEl.value;
    if (!v) return;
    if (!state.selectedTagFilters.includes(v)) state.selectedTagFilters.push(v);
    tagFilterEl.value = "";
    saveTagFiltersToStorage();
    renderTagFilterBar();
    state.currentPage = 1;
    queryVideos(1);
  });

  document.getElementById("saveConfigBtn")?.addEventListener("click", saveConfig);
  document.getElementById("scanBtn")?.addEventListener("click", scanVideos);
  document.getElementById("refreshCoversMissingBtn")?.addEventListener("click", () => refreshCovers(true));
  document.getElementById("refreshCoversAllBtn")?.addEventListener("click", () => {
    if (!confirm("将强制为库中全部（非回收站）视频重新生成封面，无论当前是否已有封面。确定？")) return;
    refreshCovers(false);
  });
  document.getElementById("autoTagBtn")?.addEventListener("click", autoGenerateTags);
  document.getElementById("exportAiDataBtn")?.addEventListener("click", exportAiData);
  document.getElementById("queryBtn")?.addEventListener("click", () => queryVideos(1));
  document.getElementById("prevPageBtn")?.addEventListener("click", () => {
    if (state.listMode === "ai") {
      if (state.currentPage > 1) {
        state.currentPage--;
        renderAiPage();
      }
    } else if (state.currentPage > 1) {
      queryVideos(state.currentPage - 1);
    }
  });
  document.getElementById("nextPageBtn")?.addEventListener("click", () => {
    if (state.listMode === "ai") {
      const perPage = Number(document.getElementById("perPageSelect").value);
      const totalPages = Math.max(1, Math.ceil(state.aiFullVideos.length / perPage) || 1);
      if (state.currentPage < totalPages) {
        state.currentPage++;
        renderAiPage();
      }
    } else {
      queryVideos(state.currentPage + 1);
    }
  });
  document.getElementById("perPageSelect")?.addEventListener("change", () => {
    try {
      localStorage.setItem(LS_PER_PAGE, document.getElementById("perPageSelect").value);
    } catch (e) {}
    state.currentPage = 1;
    if (state.listMode === "ai") renderAiPage();
    else queryVideos(1);
  });
  document.getElementById("cardSizeRange")?.addEventListener("input", e => {
    applyCardSize(Number(e.target.value));
  });
  document.getElementById("aiSearchBtn")?.addEventListener("click", aiSearchVideos);
  document.getElementById("statsRefreshSummaryBtn")?.addEventListener("click", loadStatsSummary);
  document.getElementById("statsRunSampleBtn")?.addEventListener("click", async () => {
    await saveConfig();
    await runStatsSample();
  });
  document.getElementById("statsSamplingEnabled")?.addEventListener("change", async () => {
    await saveConfig();
    if (document.getElementById("statsSamplingEnabled").checked) {
      await runStatsSample();
    }
  });

  document.getElementById("searchInput")?.addEventListener("keydown", e => {
    if (e.key === "Enter") queryVideos(1);
  });
  document.getElementById("aiQuestionInput")?.addEventListener("keydown", e => {
    if (e.key === "Enter") aiSearchVideos();
  });
  document.getElementById("tagManageTable")?.addEventListener("click", async e => {
    const btn = e.target.closest("button[data-tag-op]");
    if (!btn) return;
    const tid = Number(btn.getAttribute("data-tag-id"));
    const op = btn.getAttribute("data-tag-op");
    if (op === "rename") await renameTagGlobal(tid);
    if (op === "delete") await deleteTagGlobal(tid);
  });
  document.getElementById("tagCatalogRefreshBtn")?.addEventListener("click", () => loadTagsCatalog());

  document.getElementById("closePlayerBtn")?.addEventListener("click", () => {
    const player = document.getElementById("player");
    const playerDialog = document.getElementById("playerDialog");
    if (player) {
      player.pause();
      player.src = "";
    }
    playerDialog?.close();
  });
}

async function init() {
  try {
    const pp = localStorage.getItem(LS_PER_PAGE);
    if (pp) document.getElementById("perPageSelect").value = pp;
  } catch (e) {}
  try {
    const sr = localStorage.getItem(LS_SHOW_RECYCLE);
    if (sr === "1") document.getElementById("showRecycleCheck").checked = true;
  } catch (e) {}
  try {
    const c = localStorage.getItem(LS_CARD);
    if (c) applyCardSize(c);
    else applyCardSize(280);
  } catch (e) {
    applyCardSize(280);
  }
  await loadConfig();
  try {
    const raw = localStorage.getItem(LS_TAG_FILTERS);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) {
        state.selectedTagFilters = arr.filter(x => typeof x === "string" && x.trim());
      }
    }
  } catch (e) {}
  renderTagFilterBar();
  await queryVideos(1);
}

const gridEl = document.getElementById("videoGrid");
if (gridEl) attachGridHandlers(gridEl);
bindGlobalListeners();
bindNavigation();
bindVideoPage();
init();
