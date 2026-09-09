const { listCards, removeCard } = require("../../../utils/roleCards");

Page({
  data: { items: [] },
  onShow() {
    this.refresh();
  },
  onPullDownRefresh() {
    this.refresh();
    wx.stopPullDownRefresh();
  },
  refresh() {
    const items = listCards()
      .slice()
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    this.setData({ items });
  },
  goCreate() {
    wx.navigateTo({ url: "/pages/rolecard/create/index" });
  },
  onEdit(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({ url: `/pages/rolecard/edit/index?id=${id}` });
  },
  onPreview(e) {
    const { path, ready } = e.currentTarget.dataset;
    if (!ready || !path) {
      wx.showToast({ title: "还是草稿，请先生成角色卡图片", icon: "none" });
      return;
    }
    wx.previewImage({ urls: [path], current: path });
  },
  onDelete(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    wx.showModal({
      title: "删除作品",
      content: "将同时删除人设草稿与角色卡图片，确认删除？",
      confirmColor: "#ef4444",
      success: (res) => {
        if (!res.confirm) return;
        removeCard(id);
        this.refresh();
        wx.showToast({ title: "已删除", icon: "success" });
      },
    });
  },
});
