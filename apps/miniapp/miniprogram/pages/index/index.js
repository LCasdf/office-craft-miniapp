Page({
  data: {
    tools: [
      {
        id: "image_to_pdf",
        name: "图片转 PDF",
        desc: "多图合成一页页 PDF",
        icon: "🖼️",
        ready: true,
        url: "/pages/tools/image-to-pdf/index",
      },
      {
        id: "office_to_pdf",
        name: "Word 转 PDF",
        desc: "doc / docx 快速转换",
        icon: "📄",
        ready: true,
        url: "/pages/tools/office-to-pdf/index",
      },
      {
        id: "pdf_compress",
        name: "PDF 压缩",
        desc: "缩小体积更易分享",
        icon: "🗜️",
        ready: true,
        url: "/pages/tools/pdf-compress/index",
      },
      {
        id: "pdf_merge",
        name: "PDF 合并",
        desc: "多文件合并成一份",
        icon: "📚",
        ready: true,
        url: "/pages/tools/pdf-merge/index",
      },
    ],
  },
  onTool(e) {
    const { url, ready } = e.currentTarget.dataset;
    if (!ready || !url) {
      wx.showToast({ title: "即将开放", icon: "none" });
      return;
    }
    wx.navigateTo({ url });
  },
  goTasks() {
    wx.navigateTo({ url: "/pages/tasks/list/index" });
  },
  goMe() {
    wx.navigateTo({ url: "/pages/me/index" });
  },
});
