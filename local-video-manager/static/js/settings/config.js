import { state } from "../core/state.js";
import { setSettingsStatus } from "../ui/status.js";

export async function loadConfig() {
  const r = await fetch("/api/config");
  const data = await r.json();
  const dataDir = document.getElementById("dataDir");
  const libraryDirs = document.getElementById("libraryDirs");
  if (dataDir) dataDir.value = data.data_dir || "";
  if (libraryDirs) libraryDirs.value = (data.library_dirs || []).join(";");
  const llm = data.llm || {};
  const llmBaseUrl = document.getElementById("llmBaseUrl");
  const llmModel = document.getElementById("llmModel");
  const llmApiKey = document.getElementById("llmApiKey");
  const llmMaxCandidates = document.getElementById("llmMaxCandidates");
  const llmEnabled = document.getElementById("llmEnabled");
  if (llmBaseUrl) llmBaseUrl.value = llm.base_url || "";
  if (llmModel) llmModel.value = llm.model || "";
  if (llmApiKey) llmApiKey.value = llm.api_key || "";
  if (llmMaxCandidates) llmMaxCandidates.value = Number(llm.max_candidates || 120);
  if (llmEnabled) llmEnabled.checked = !!llm.enabled;
  const st = data.stats || {};
  const statsSamplingEnabled = document.getElementById("statsSamplingEnabled");
  const statsSampleSize = document.getElementById("statsSampleSize");
  if (statsSamplingEnabled) statsSamplingEnabled.checked = !!st.performance_sampling_enabled;
  if (statsSampleSize) statsSampleSize.value = Number(st.sample_size || 30);
  const pl = data.player || {};
  const externalPlayerPath = document.getElementById("externalPlayerPath");
  if (externalPlayerPath) externalPlayerPath.value = pl.external_path || "";
  state.externalPlayerConfigured = !!(pl.external_path && String(pl.external_path).trim());
  const intent = data.intent || {};
  const intentEnabled = document.getElementById("intentEnabled");
  const intentModel = document.getElementById("intentModel");
  const intentLexicalBlend = document.getElementById("intentLexicalBlend");
  const intentMinSem = document.getElementById("intentMinSem");
  if (intentEnabled) intentEnabled.checked = !!intent.enabled;
  if (intentModel) intentModel.value = intent.model || "BAAI/bge-small-zh-v1.5";
  if (intentLexicalBlend) {
    intentLexicalBlend.value = intent.lexical_blend != null ? intent.lexical_blend : 0.42;
  }
  if (intentMinSem) {
    intentMinSem.value = intent.min_semantic != null ? intent.min_semantic : 0.18;
  }
}

export async function saveConfig() {
  const dataDir = document.getElementById("dataDir")?.value.trim() ?? "";
  const libraryDirs = (document.getElementById("libraryDirs")?.value ?? "")
    .split(";")
    .map(x => x.trim())
    .filter(Boolean);
  const llm = {
    base_url: document.getElementById("llmBaseUrl")?.value.trim() ?? "",
    model: document.getElementById("llmModel")?.value.trim() ?? "",
    api_key: document.getElementById("llmApiKey")?.value.trim() ?? "",
    max_candidates: Number(document.getElementById("llmMaxCandidates")?.value || 120),
    enabled: document.getElementById("llmEnabled")?.checked ?? false,
  };
  const stats = {
    performance_sampling_enabled: document.getElementById("statsSamplingEnabled")?.checked ?? false,
    sample_size: Number(document.getElementById("statsSampleSize")?.value || 30),
  };
  const player = {
    external_path: document.getElementById("externalPlayerPath")?.value.trim() ?? "",
  };
  state.externalPlayerConfigured = !!player.external_path;
  const intent = {
    enabled: document.getElementById("intentEnabled")?.checked ?? false,
    model: document.getElementById("intentModel")?.value.trim() ?? "",
    lexical_blend: Number(document.getElementById("intentLexicalBlend")?.value || 0.42),
    min_semantic: Number(document.getElementById("intentMinSem")?.value || 0.18),
    query_prefix: "",
  };
  const r = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data_dir: dataDir, library_dirs: libraryDirs, llm, stats, player, intent }),
  });
  const data = await r.json();
  if (data.ok) setSettingsStatus("配置已保存");
  else setSettingsStatus("配置保存失败", true);
}
