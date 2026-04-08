/** 跨模块共享的可变状态（单页应用内单例） */
export const state = {
  currentVideos: [],
  /** browse：服务端分页；ai：前端对 aiFullVideos 分页 */
  listMode: "browse",
  aiFullVideos: [],
  currentPage: 1,
  /** 多选标签筛选（AND）；顺序为点击顺序 */
  selectedTagFilters: [],
  externalPlayerConfigured: false,
  tagCatalogList: [],
};
