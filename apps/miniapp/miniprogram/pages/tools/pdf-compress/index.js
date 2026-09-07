const { uuid, request, uploadObject } = require("../../../utils/api");

Page({
  data: {
    file: null,
    busy: false,
    quality: "standard",
    qualities: [
      { id: "high", name: "高质量", hint: "体积较大" },
      { id: "standard", name: "标准", hint: "推荐" },
      { id: "extreme", name: "极限", hint: "更小更糊" },
    ],
  },
  setQuality(e) {
    this.setData({ quality: e.currentTarget.dataset.id });
  },
  choose() {
    wx.chooseMessageFile({
      count: 1,
      type: "file",
      extension: ["pdf"],
      success: (res) => {
        const f = (res.tempFiles || [])[0];
        if (!f) return;
        this.setData({
          file: { path: f.path, name: f.name || "file.pdf", size: f.size },
        });
      },
    });
  },
  async submit() {
    const f = this.data.file;
    if (!f) {
      wx.showToast({ title: "请选择 PDF", icon: "none" });
      return;
    }
    this.setData({ busy: true });
    try {
      const cred = await request({
        url: "/v1/uploads/credential",
        method: "POST",
        data: { taskType: "pdf_compress", fileCount: 1 },
      });
      if (cred.code !== 0) throw new Error(cred.user_msg || "凭证失败");
      const uploadId = cred.data.uploadId;
      const up = await uploadObject({
        uploadId,
        filePath: f.path,
        filename: f.name,
        index: 0,
        taskType: "pdf_compress",
      });
      if (up.code !== 0) throw new Error(up.user_msg || "上传失败");
      const task = await request({
        url: "/v1/tasks",
        method: "POST",
        header: { "Idempotency-Key": uuid() },
        data: {
          type: "pdf_compress",
          uploadId,
          inputs: [
            {
              cosKey: up.data.cosKey,
              filename: f.name,
              sizeBytes: up.data.sizeBytes,
            },
          ],
          params: { quality: this.data.quality },
        },
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
