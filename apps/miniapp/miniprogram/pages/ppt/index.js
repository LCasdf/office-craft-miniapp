const { request, uuid } = require("../../utils/api");

const TEMPLATE_ID = "tpl_basic_01";

const AUDIENCE_OPTIONS = ["技术学习者", "面试官", "团队同事", "管理层"];
const STYLE_OPTIONS = [
  { id: "business", label: "简洁商务" },
  { id: "tech", label: "技术分享" },
  { id: "interview", label: "面试答辩" },
];

function enrichPages(pages) {
  return (pages || []).map((p) => {
    const bullets = p.bullets || [];
    return {
      title: p.title || "",
      bullets,
      bulletsText: bullets.join("\n"),
      summary: bullets.slice(0, 2).join(" · ") || "暂无要点，点编辑补充",
      previewBullets: bullets.slice(0, 3).map((b) => "· " + b),
    };
  });
}

function resolveAudience(data) {
  const custom = (data.audienceCustom || "").trim();
  if (custom) return custom;
  return data.audience || "";
}

Page({
  data: {
    topic: "",
    pageCount: 8,
    audience: "技术学习者",
    audienceCustom: "",
    audienceOptions: AUDIENCE_OPTIONS,
    styleId: "tech",
    styleOptions: STYLE_OPTIONS,
    outlineId: "",
    outlineVersion: 0,
    pages: [],
    hasOutline: false,
    expandedIndex: -1,
    previewIndex: 0,
    busy: false,
  },

  onTopic(e) {
    this.setData({ topic: e.detail.value || "" });
  },

  onPageCountDec() {
    const n = Math.max(5, this.data.pageCount - 1);
    this.setData({ pageCount: n });
  },

  onPageCountInc() {
    const n = Math.min(15, this.data.pageCount + 1);
    this.setData({ pageCount: n });
  },

  onPickAudience(e) {
    const value = e.currentTarget.dataset.value || "";
    this.setData({ audience: value, audienceCustom: "" });
  },

  onAudienceCustom(e) {
    const v = e.detail.value || "";
    this.setData({
      audienceCustom: v,
      audience: v.trim() ? "" : this.data.audience || "技术学习者",
    });
  },

  onPickStyle(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    this.setData({ styleId: id });
  },

  onTogglePage(e) {
    const i = Number(e.currentTarget.dataset.i);
    if (!Number.isFinite(i)) return;
    const next = this.data.expandedIndex === i ? -1 : i;
    this.setData({ expandedIndex: next, previewIndex: i });
  },

  onFocusPreview(e) {
    const i = Number(e.currentTarget.dataset.i);
    if (!Number.isFinite(i)) return;
    this.setData({ previewIndex: i, expandedIndex: i });
  },

  onPageTitle(e) {
    const i = e.currentTarget.dataset.i;
    const pages = this.data.pages.slice();
    if (!pages[i]) return;
    pages[i] = Object.assign({}, pages[i], { title: e.detail.value || "" });
    this.setData({ pages });
  },

  onPageBullets(e) {
    const i = e.currentTarget.dataset.i;
    const pages = this.data.pages.slice();
    if (!pages[i]) return;
    const lines = String(e.detail.value || "")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    pages[i] = Object.assign({}, pages[i], {
      bullets: lines,
      bulletsText: lines.join("\n"),
      summary: lines.slice(0, 2).join(" · ") || "暂无要点，点编辑补充",
      previewBullets: lines.slice(0, 3).map((b) => "· " + b),
    });
    this.setData({ pages });
  },

  _styleLabel() {
    const hit = STYLE_OPTIONS.find((s) => s.id === this.data.styleId);
    return (hit && hit.label) || "简洁商务";
  },

  async onCreateOutline() {
    const topic = (this.data.topic || "").trim();
    if (!topic) {
      wx.showToast({ title: "请输入PPT主题", icon: "none" });
      return;
    }
    const audience = resolveAudience(this.data);
    const styleLabel = this._styleLabel();
    const audiencePayload = [styleLabel, audience].filter(Boolean).join(" · ");

    this.setData({ busy: true });
    try {
      const body = await request({
        url: "/v1/ai/ppt/outline",
        method: "POST",
        header: { "Idempotency-Key": uuid() },
        data: {
          topic,
          pageCount: this.data.pageCount,
          templateId: TEMPLATE_ID,
          audience: audiencePayload,
        },
      });
      if (body.code !== 0) {
        wx.showToast({ title: body.user_msg || "生成失败", icon: "none" });
        return;
      }
      const d = body.data || {};
      const pages = enrichPages(d.pages || []);
      this.setData({
        hasOutline: true,
        outlineId: d.outlineId,
        outlineVersion: d.outlineVersion,
        pages,
        expandedIndex: -1,
        previewIndex: 0,
      });
      wx.showToast({ title: "大纲已生成", icon: "success" });
    } catch (e) {
      wx.showToast({ title: "无法连接服务", icon: "none" });
    } finally {
      this.setData({ busy: false });
    }
  },

  async onSaveAndGenerate() {
    const { outlineId, outlineVersion, pages } = this.data;
    if (!outlineId || !pages.length) {
      wx.showToast({ title: "请先生成大纲", icon: "none" });
      return;
    }
    this.setData({ busy: true });
    try {
      const pagesForApi = pages.map((p) => ({
        title: p.title || "",
        bullets: p.bullets || [],
      }));
      const put = await request({
        url: `/v1/ai/ppt/outline/${outlineId}`,
        method: "PUT",
        header: { "If-Match": String(outlineVersion) },
        data: {
          version: outlineVersion,
          pages: pagesForApi,
          templateId: TEMPLATE_ID,
        },
      });
      if (put.code !== 0) {
        wx.showToast({ title: put.user_msg || "保存失败", icon: "none" });
        return;
      }
      const ver = put.data.outlineVersion;
      const finalPages = (put.data.pages || pagesForApi).map((p) => ({
        title: p.title || "",
        bullets: p.bullets || [],
      }));
      this.setData({
        outlineVersion: ver,
        pages: enrichPages(finalPages),
      });

      const gen = await request({
        url: "/v1/ai/ppt/generate",
        method: "POST",
        header: { "Idempotency-Key": uuid() },
        data: {
          outlineId,
          outlineVersion: ver,
          templateId: TEMPLATE_ID,
          pages: finalPages,
        },
      });
      if (gen.code !== 0) {
        wx.showToast({ title: gen.user_msg || "导出失败", icon: "none" });
        return;
      }
      wx.showToast({ title: "已提交导出", icon: "success" });
      setTimeout(() => {
        wx.navigateTo({ url: "/pages/tasks/list/index" });
      }, 450);
    } catch (e) {
      wx.showToast({ title: "网络错误", icon: "none" });
    } finally {
      this.setData({ busy: false });
    }
  },
});
