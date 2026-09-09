const { request, uuid } = require("../../../utils/api");

const ACTIVE = { queued: 1, running: 1, pending: 1 };
const POLL_MS = 2000;
const MAX_RETRY = 2;

function decorate(items) {
  return (items || []).map((t) => ({
    ...t,
    canRetry:
      t.status === "failed" &&
      t.errorClass !== "safety" &&
      (t.retryCount || 0) < MAX_RETRY,
    canDownload: t.status === "succeeded" && !t.resultExpired,
  }));
}

Page({
  data: { items: [], loading: false, error: "", busyId: "", clearing: false },
  _timer: null,
  onShow() {
    this.loadTasks(true);
  },
  onHide() {
    this._stopPoll();
  },
  onUnload() {
    this._stopPoll();
  },
  onPullDownRefresh() {
    this.loadTasks(false).finally(() => wx.stopPullDownRefresh());
  },
  _stopPoll() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },
  _maybePoll(items) {
    this._stopPoll();
    if ((items || []).some((t) => ACTIVE[t.status])) {
      this._timer = setInterval(() => this.loadTasks(false), POLL_MS);
    }
  },
  loadTasks(showLoading) {
    if (showLoading) this.setData({ loading: true, error: "" });
    return request({ url: "/v1/tasks" })
      .then((body) => {
        if (body.code !== 0) {
          this.setData({ error: body.user_msg || "加载失败", items: [], loading: false });
          this._stopPoll();
          return;
        }
        const items = decorate((body.data && body.data.items) || []);
        this.setData({ items, loading: false, error: "" });
        this._maybePoll(items);
      })
      .catch(() => {
        this.setData({ error: "无法连接 API", items: [], loading: false });
        this._stopPoll();
      });
  },
  onCancel(e) {
    const taskId = e.currentTarget.dataset.id;
    if (!taskId || this.data.busyId) return;
    wx.showModal({
      title: "取消任务",
      content: "取消后将返还预扣额度，确认取消？",
      success: (res) => {
        if (!res.confirm) return;
        this.setData({ busyId: taskId });
        request({ url: `/v1/tasks/${taskId}/cancel`, method: "POST" })
          .then((body) => {
            if (body.code !== 0) {
              wx.showToast({ title: body.user_msg || "取消失败", icon: "none" });
              return;
            }
            wx.showToast({ title: body.user_msg || "已取消", icon: "success" });
            this.loadTasks(false);
          })
          .catch(() => wx.showToast({ title: "取消失败", icon: "none" }))
          .finally(() => this.setData({ busyId: "" }));
      },
    });
  },
  onDelete(e) {
    const taskId = e.currentTarget.dataset.id;
    if (!taskId || this.data.busyId || this.data.clearing) return;
    wx.showModal({
      title: "删除任务",
      content: "删除后无法从任务中心找回，确认删除？",
      confirmColor: "#ef4444",
      success: (res) => {
        if (!res.confirm) return;
        this.setData({ busyId: taskId });
        request({ url: `/v1/tasks/${taskId}`, method: "DELETE" })
          .then((body) => {
            if (body.code !== 0) {
              wx.showToast({ title: body.user_msg || "删除失败", icon: "none" });
              return;
            }
            const items = this.data.items.filter((t) => t.taskId !== taskId);
            this.setData({ items });
            this._maybePoll(items);
            wx.showToast({ title: "已删除", icon: "success" });
          })
          .catch(() => wx.showToast({ title: "删除失败", icon: "none" }))
          .finally(() => this.setData({ busyId: "" }));
      },
    });
  },
  onClear() {
    if (this.data.clearing || this.data.busyId || !this.data.items.length) return;
    wx.showModal({
      title: "清空任务",
      content: "将删除全部任务；进行中的会返还预扣额度，且无法找回。确认清空？",
      confirmColor: "#ef4444",
      success: (res) => {
        if (!res.confirm) return;
        this.setData({ clearing: true });
        this._stopPoll();
        request({ url: "/v1/tasks", method: "DELETE" })
          .then((body) => {
            if (body.code !== 0) {
              wx.showToast({ title: body.user_msg || "清空失败", icon: "none" });
              this.loadTasks(false);
              return;
            }
            this.setData({ items: [] });
            wx.showToast({ title: body.user_msg || "已清空", icon: "success" });
          })
          .catch(() => {
            wx.showToast({ title: "清空失败", icon: "none" });
            this.loadTasks(false);
          })
          .finally(() => this.setData({ clearing: false }));
      },
    });
  },
  onRetry(e) {
    const taskId = e.currentTarget.dataset.id;
    if (!taskId || this.data.busyId) return;
    this.setData({ busyId: taskId });
    request({
      url: `/v1/tasks/${taskId}/retry`,
      method: "POST",
      header: { "Idempotency-Key": uuid() },
    })
      .then((body) => {
        if (body.code !== 0) {
          wx.showToast({ title: body.user_msg || "重试失败", icon: "none" });
          return;
        }
        wx.showToast({ title: body.user_msg || "已重新提交", icon: "success" });
        this.loadTasks(false);
      })
      .catch(() => wx.showToast({ title: "重试失败", icon: "none" }))
      .finally(() => this.setData({ busyId: "" }));
  },
  onDownload(e) {
    const taskId = e.currentTarget.dataset.id;
    if (!taskId) return;
    wx.showLoading({ title: "获取链接…" });
    request({ url: `/v1/tasks/${taskId}/download` })
      .then((body) => {
        wx.hideLoading();
        if (body.code !== 0) {
          wx.showToast({ title: body.user_msg || "失败", icon: "none" });
          if (body.code === 40016) this.loadTasks(false);
          return;
        }
        const url = body.data && body.data.downloadUrl;
        const filename = (body.data && body.data.filename) || "";
        if (!url) {
          wx.showToast({ title: "暂无下载地址", icon: "none" });
          return;
        }
        const isPng = /\.png$/i.test(filename) || /\.png(\?|$)/i.test(url);
        wx.downloadFile({
          url,
          success: (res) => {
            if (res.statusCode !== 200) {
              wx.showToast({ title: "下载失败", icon: "none" });
              return;
            }
            if (isPng) {
              wx.previewImage({
                urls: [res.tempFilePath],
                current: res.tempFilePath,
                fail: () => wx.showToast({ title: "无法预览图片", icon: "none" }),
              });
              return;
            }
            wx.openDocument({
              filePath: res.tempFilePath,
              fileType: "pdf",
              showMenu: true,
              fail: () => wx.showToast({ title: "无法打开 PDF", icon: "none" }),
            });
          },
          fail: () => wx.showToast({ title: "下载失败", icon: "none" }),
        });
      })
      .catch(() => {
        wx.hideLoading();
        wx.showToast({ title: "请求失败", icon: "none" });
      });
  },
});
