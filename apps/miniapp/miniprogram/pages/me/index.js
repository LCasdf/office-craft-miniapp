const { request } = require("../../utils/api");

Page({
  data: {
    available: 0,
    dailyRemaining: 0,
    frozenQuota: 0,
    dailyQuotaLimit: 20,
    loading: true,
  },
  onShow() {
    this.loadQuota();
  },
  loadQuota() {
    this.setData({ loading: true });
    request({ url: "/v1/me/quota" })
      .then((body) => {
        if (body.code !== 0) {
          this.setData({ loading: false });
          wx.showToast({ title: body.user_msg || "额度加载失败", icon: "none" });
          return;
        }
        const d = body.data || {};
        this.setData({
          available: d.available ?? 0,
          dailyRemaining: d.dailyRemaining ?? 0,
          frozenQuota: d.frozenQuota ?? 0,
          dailyQuotaLimit: d.dailyQuotaLimit ?? 20,
          loading: false,
        });
      })
      .catch(() => {
        this.setData({ loading: false });
        wx.showToast({ title: "无法连接 API", icon: "none" });
      });
  },
});
