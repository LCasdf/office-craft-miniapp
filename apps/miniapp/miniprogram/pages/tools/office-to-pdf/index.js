const { uuid, request, uploadObject } = require("../../../utils/api");

Page({
  data: { file: null, busy: false },
  choose() {
    wx.chooseMessageFile({
      count: 1,
      type: "file",
      extension: ["doc", "docx"],
      success: (res) => {
        const f = (res.tempFiles || [])[0];
        if (!f) return;
        this.setData({
          file: { path: f.path, name: f.name || "doc.docx", size: f.size },
        });
      },
    });
  },
  async submit() {
    const f = this.data.file;
    if (!f) {
      wx.showToast({ title: "请选择 Word", icon: "none" });
      return;
    }
    this.setData({ busy: true });
    try {
      const cred = await request({
        url: "/v1/uploads/credential",
        method: "POST",
        data: { taskType: "office_to_pdf", fileCount: 1 },
      });
      if (cred.code !== 0) throw new Error(cred.user_msg || "凭证失败");
      const uploadId = cred.data.uploadId;
      const up = await uploadObject({
        uploadId,
        filePath: f.path,
        filename: f.name,
        index: 0,
        taskType: "office_to_pdf",
      });
      if (up.code !== 0) throw new Error(up.user_msg || "上传失败");
      const task = await request({
        url: "/v1/tasks",
        method: "POST",
        header: { "Idempotency-Key": uuid() },
        data: {
          type: "office_to_pdf",
          uploadId,
          inputs: [
            {
              cosKey: up.data.cosKey,
              filename: f.name,
              sizeBytes: up.data.sizeBytes,
            },
          ],
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
