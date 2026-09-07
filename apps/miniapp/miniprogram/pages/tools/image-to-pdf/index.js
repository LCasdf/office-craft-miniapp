const { uuid, request, uploadObject } = require("../../../utils/api");

Page({
  data: { files: [], busy: false, lastTaskId: "" },
  choose() {
    wx.chooseMedia({
      count: 20,
      mediaType: ["image"],
      success: (res) => {
        const files = (res.tempFiles || []).map((f, i) => ({
          path: f.tempFilePath,
          name: `img_${i}.jpg`,
          size: f.size,
        }));
        this.setData({ files });
      },
    });
  },
  async submit() {
    if (!this.data.files.length) {
      wx.showToast({ title: "请先选图", icon: "none" });
      return;
    }
    this.setData({ busy: true });
    try {
      const cred = await request({
        url: "/v1/uploads/credential",
        method: "POST",
        data: { taskType: "image_to_pdf", fileCount: this.data.files.length },
      });
      if (cred.code !== 0) throw new Error(cred.user_msg || "凭证失败");
      const uploadId = cred.data.uploadId;
      const inputs = [];
      for (let i = 0; i < this.data.files.length; i++) {
        const f = this.data.files[i];
        const up = await uploadObject({
          uploadId,
          filePath: f.path,
          filename: f.name,
          index: i,
          taskType: "image_to_pdf",
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
        data: { type: "image_to_pdf", uploadId, inputs, params: { orientation: "auto" } },
      });
      if (task.code !== 0) throw new Error(task.user_msg || "创建失败");
      this.setData({ lastTaskId: task.data.taskId });
      wx.showToast({ title: "已提交", icon: "success" });
      setTimeout(() => wx.navigateTo({ url: "/pages/tasks/list/index" }), 500);
    } catch (e) {
      wx.showToast({ title: (e && e.message) || "失败", icon: "none" });
    } finally {
      this.setData({ busy: false });
    }
  },
});
