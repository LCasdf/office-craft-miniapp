Page({
  data: {
    tools: [
      { id: "pdf_compress", name: "PDF 压缩", ready: false },
      { id: "pdf_merge", name: "PDF 合并", ready: false },
      { id: "image_to_pdf", name: "图片转 PDF", ready: false },
    ],
  },
  goTasks() {
    wx.navigateTo({ url: "/pages/tasks/list/index" });
  },
  goMe() {
    wx.navigateTo({ url: "/pages/me/index" });
  },
});
