Page({
  data: {
    pdfTools: [
      {
        id: "image_to_pdf",
        name: "图片转 PDF",
        desc: "多图合成一页页 PDF",
        icon: "🖼️",
        url: "/pages/tools/image-to-pdf/index",
      },
      {
        id: "office_to_pdf",
        name: "Word 转 PDF",
        desc: "doc / docx 快速转换",
        icon: "📄",
        url: "/pages/tools/office-to-pdf/index",
      },
      {
        id: "pdf_compress",
        name: "PDF 压缩",
        desc: "缩小体积更易分享",
        icon: "🗜️",
        url: "/pages/tools/pdf-compress/index",
      },
      {
        id: "pdf_merge",
        name: "PDF 合并",
        desc: "多文件合并成一份",
        icon: "📚",
        url: "/pages/tools/pdf-merge/index",
      },
    ],
  },
  onTool(e) {
    const url = e.currentTarget.dataset.url;
    if (!url) return;
    wx.navigateTo({ url });
  },
  goRolecard() {
    wx.navigateTo({ url: "/pages/rolecard/list/index" });
  },
  goTasks() {
    wx.navigateTo({ url: "/pages/tasks/list/index" });
  },
  goMe() {
    wx.navigateTo({ url: "/pages/me/index" });
  },
});
