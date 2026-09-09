/** Shared create/edit — 文字描述 → 生成角色立绘图片（核心产出）。 */
const { request, uuid: reqUuid } = require("../../../utils/api");
const {
  emptyForm,
  getCard,
  upsertCard,
  uuid,
  persistCardImage,
} = require("../../../utils/roleCards");

const SECTIONS = [
  { id: "basic", title: "基础信息", open: true },
  { id: "look", title: "形象外貌", open: true },
  { id: "personality", title: "性格特质", open: false },
  { id: "story", title: "背景故事", open: false },
  { id: "power", title: "能力与弱点", open: false },
  { id: "remark", title: "备注", open: false },
];

function cloneSections() {
  return SECTIONS.map((s) => ({
    id: s.id,
    title: s.title,
    open: s.open,
  }));
}

function downloadToLocal(url, cardId) {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url,
      success: (res) => {
        if (res.statusCode !== 200 || !res.tempFilePath) {
          reject(new Error("download failed"));
          return;
        }
        persistCardImage(res.tempFilePath, cardId).then(resolve).catch(reject);
      },
      fail: reject,
    });
  });
}

/**
 * @param {"create"|"edit"} mode
 */
function buildEditorPage(mode) {
  return {
    data: {
      mode,
      form: emptyForm(),
      cardImagePath: "",
      aiBusy: false,
      imagineBusy: false,
      saveBusy: false,
      sections: cloneSections(),
    },
    onLoad(query) {
      if (mode === "edit") {
        const id = query && query.id;
        if (!id) {
          wx.showToast({ title: "缺少角色 id", icon: "none" });
          setTimeout(
            () =>
              wx.navigateBack({
                fail: () =>
                  wx.redirectTo({ url: "/pages/rolecard/list/index" }),
              }),
            400
          );
          return;
        }
        const card = getCard(id);
        if (!card) {
          wx.showToast({ title: "角色不存在", icon: "none" });
          setTimeout(
            () =>
              wx.navigateBack({
                fail: () =>
                  wx.redirectTo({ url: "/pages/rolecard/list/index" }),
              }),
            400
          );
          return;
        }
        const form = Object.assign({}, emptyForm(), card, {
          prompt: card.prompt || "",
        });
        this.setData({
          form,
          cardImagePath: card.cardImagePath || "",
        });
        return;
      }
      const form = emptyForm();
      form.id = uuid();
      this.setData({ form, cardImagePath: "", sections: cloneSections() });
    },
    onPrompt(e) {
      this.setData({ "form.prompt": e.detail.value || "" });
    },
    onField(e) {
      const key = e.currentTarget.dataset.key;
      if (!key) return;
      this.setData({ ["form." + key]: e.detail.value || "" });
    },
    toggleSection(e) {
      const id = e.currentTarget.dataset.id;
      const sections = this.data.sections.map((s) =>
        s.id === id ? Object.assign({}, s, { open: !s.open }) : s
      );
      this.setData({ sections });
    },
    onPickAvatar() {
      wx.chooseMedia({
        count: 1,
        mediaType: ["image"],
        sourceType: ["album", "camera"],
        success: (res) => {
          const f = (res.tempFiles || [])[0];
          if (!f || !f.tempFilePath) return;
          this.setData({ "form.avatarPath": f.tempFilePath });
        },
      });
    },
    async onAiGenerate() {
      const prompt = (this.data.form.prompt || "").trim();
      if (!prompt) {
        wx.showToast({ title: "请先描述角色", icon: "none" });
        return;
      }
      this.setData({ aiBusy: true });
      try {
        const body = await request({
          url: "/v1/ai/character-card/generate",
          method: "POST",
          header: { "Idempotency-Key": reqUuid() },
          data: { premise: prompt },
        });
        if (body.code !== 0) {
          wx.showToast({ title: body.user_msg || "生成失败", icon: "none" });
          return;
        }
        const p = (body.data && body.data.payload) || {};
        const sections = this.data.sections.map((s) =>
          Object.assign({}, s, {
            open: s.id === "remark" ? !!p.remark : true,
          })
        );
        this.setData({
          "form.name": p.name || this.data.form.name,
          "form.title": p.title || this.data.form.title,
          "form.avatarDesc": p.avatarDesc || this.data.form.avatarDesc,
          "form.personality": p.personality || this.data.form.personality,
          "form.story": p.story || this.data.form.story,
          "form.ability": p.ability || this.data.form.ability,
          "form.weakness": p.weakness || this.data.form.weakness,
          "form.remark": p.remark || this.data.form.remark,
          sections,
        });
        wx.showToast({ title: "人设文字已填充", icon: "success" });
      } catch (e) {
        wx.showToast({ title: "无法连接 AI 服务", icon: "none" });
      } finally {
        this.setData({ aiBusy: false });
      }
    },
    /** 核心：文字 → 角色立绘图片 */
    async onImagineImage() {
      const f = this.data.form;
      const desc = (f.prompt || f.avatarDesc || f.story || "").trim();
      if (!desc && !(f.name || "").trim()) {
        wx.showToast({ title: "请先写角色描述或姓名", icon: "none" });
        return;
      }
      this.setData({ imagineBusy: true });
      try {
        const body = await request({
          url: "/v1/ai/character-card/imagine",
          method: "POST",
          data: {
            prompt: f.prompt || "",
            name: f.name || "",
            title: f.title || "",
            avatarDesc: f.avatarDesc || "",
            personality: f.personality || "",
            story: f.story || "",
          },
        });
        if (body.code !== 0) {
          wx.showToast({ title: body.user_msg || "出图失败", icon: "none" });
          return;
        }
        const imageUrl = body.data && body.data.imageUrl;
        if (!imageUrl) {
          wx.showToast({ title: "未返回图片", icon: "none" });
          return;
        }
        const id = f.id || uuid();
        const localPath = await downloadToLocal(imageUrl, id);
        this.setData({
          "form.id": id,
          "form.status": "ready",
          "form.cardImagePath": localPath,
          "form.coverPath": localPath,
          cardImagePath: localPath,
        });
        wx.previewImage({ urls: [localPath], current: localPath });
        wx.showToast({ title: "角色图片已生成", icon: "success" });
      } catch (e) {
        wx.showToast({ title: "生成失败，请检查网络", icon: "none" });
      } finally {
        this.setData({ imagineBusy: false });
      }
    },
    onSaveDraft() {
      const form = Object.assign({}, this.data.form);
      if (!(form.name || "").trim() && !(form.prompt || "").trim()) {
        wx.showToast({ title: "请至少填写姓名或描述", icon: "none" });
        return;
      }
      if (!form.id) form.id = uuid();
      if (!(form.name || "").trim()) form.name = "未命名角色";
      form.cardImagePath =
        this.data.cardImagePath || form.cardImagePath || "";
      form.coverPath = form.cardImagePath;
      form.status = form.cardImagePath ? "ready" : "draft";
      upsertCard(form);
      this.setData({ form, cardImagePath: form.cardImagePath });
      wx.showToast({
        title: form.cardImagePath ? "已更新角色卡集" : "草稿已保存",
        icon: "success",
      });
      setTimeout(() => {
        wx.redirectTo({ url: "/pages/rolecard/list/index" });
      }, 400);
    },
    onSaveCardToCollection() {
      const form = Object.assign({}, this.data.form);
      const path = this.data.cardImagePath || form.cardImagePath;
      if (!path) {
        wx.showToast({ title: "请先生成角色图片", icon: "none" });
        return;
      }
      if (!form.id) form.id = uuid();
      if (!(form.name || "").trim()) form.name = "未命名角色";
      form.cardImagePath = path;
      form.coverPath = path;
      form.status = "ready";
      upsertCard(form);
      this.setData({ form });
      wx.showToast({ title: "已保存到角色卡集", icon: "success" });
      setTimeout(() => {
        wx.redirectTo({ url: "/pages/rolecard/list/index" });
      }, 400);
    },
    onSavePhoto() {
      const path = this.data.cardImagePath;
      if (!path) {
        wx.showToast({ title: "请先生成角色图片", icon: "none" });
        return;
      }
      this.setData({ saveBusy: true });
      wx.saveImageToPhotosAlbum({
        filePath: path,
        success: () => wx.showToast({ title: "已保存到相册", icon: "success" }),
        fail: () => {
          wx.showModal({
            title: "需要相册权限",
            content: "请在设置中允许保存到相册后重试",
            showCancel: false,
          });
        },
        complete: () => this.setData({ saveBusy: false }),
      });
    },
    onPreviewRendered() {
      const path = this.data.cardImagePath;
      if (!path) return;
      wx.previewImage({ urls: [path], current: path });
    },
  };
}

module.exports = { buildEditorPage };
