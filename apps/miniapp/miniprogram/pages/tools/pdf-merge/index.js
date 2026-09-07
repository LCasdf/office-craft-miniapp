const { uuid, request, uploadObject } = require("../../../utils/api");

const MAX_FILES = 10;

Page({
  data: { files: [], busy: false },
  choose() {
    const remain = MAX_FILES - this.data.files.length;
    if (remain <= 0) {
      wx.showToast({ title: `最多 ${MAX_FILES} 个 PDF`, icon: "none" });
      return;
    }
    wx.chooseMessageFile({
      count: remain,
      type: "file",
      extension: ["pdf"],
      success: (res) => {
        const picked = (res.tempFiles || []).map((f) => ({
          path: f.path,
          name: f.name || "file.pdf",
          size: f.size,
        }));
        if (!picked.length) return;
        const seen = {};
        const files = this.data.files.slice();
        files.forEach((f) => {
          seen[`${f.path}|${f.size}`] = 1;
        });
        for (let i = 0; i < picked.length; i++) {
          if (files.length >= MAX_FILES) break;
          const f = picked[i];
          const key = `${f.path}|${f.size}`;
          if (seen[key]) continue;
          seen[key] = 1;
          files.push(f);
        }
        this.setData({ files });
        if (files.length < 2) {
          wx.showToast({ title: "请继续添加，至少 2 个", icon: "none" });
        }
      },
    });
  },
  clearFiles() {
    this.setData({ files: [] });
  },
  remove(e) {
    const i = Number(e.currentTarget.dataset.index);
    const files = this.data.files.slice();
    files.splice(i, 1);
    this.setData({ files });
  },
  moveUp(e) {
    const i = Number(e.currentTarget.dataset.index);
    if (i <= 0) return;
    const files = this.data.files.slice();
    const tmp = files[i - 1];
    files[i - 1] = files[i];
    files[i] = tmp;
    this.setData({ files });
  },
  moveDown(e) {
    const i = Number(e.currentTarget.dataset.index);
    const files = this.data.files.slice();
    if (i >= files.length - 1) return;
    const tmp = files[i + 1];
    files[i + 1] = files[i];
    files[i] = tmp;
    this.setData({ files });
  },
  async submit() {
    const files = this.data.files;
    if (files.length < 2) {
      wx.showToast({ title: "请选择 2–10 个 PDF", icon: "none" });
      return;
    }
    this.setData({ busy: true });
    try {
      const cred = await request({
        url: "/v1/uploads/credential",
        method: "POST",
        data: { taskType: "pdf_merge", fileCount: files.length },
      });
      if (cred.code !== 0) throw new Error(cred.user_msg || "凭证失败");
      const uploadId = cred.data.uploadId;
      const inputs = [];
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        const up = await uploadObject({
          uploadId,
          filePath: f.path,
          filename: f.name,
          index: i,
          taskType: "pdf_merge",
        });
        if (up.code !== 0) throw new Error(up.user_msg || "上传失败");
        inputs.push({
          cosKey: up.data.cosKey,
          filename: f.name,
          sizeBytes: up.data.sizeBytes,
        });
      }
      const task = await request({
        url: "/v1/tasks",
        method: "POST",
        header: { "Idempotency-Key": uuid() },
        data: { type: "pdf_merge", uploadId, inputs },
      });
      if (task.code !== 0) throw new Error(task.user_msg || "创建失败");
      wx.showToast({ title: "已提交", icon: "success" });
      setTimeout(() => wx.navigateTo({ url: "/pages/tasks/list/index" }), 500);
    } catch (e) {
      wx.showToast({ title: (e && e.message) || "失败", icon: "none" });
    } finally {
      this.setData({ busy: false });
    }
  },
});
