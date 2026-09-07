function apiBase() {
  return getApp().globalData.apiBaseUrl;
}

function uuid() {
  const s = [];
  const hex = "0123456789abcdef";
  for (let i = 0; i < 36; i++) s[i] = hex[(Math.random() * 16) | 0];
  s[14] = "4";
  s[19] = hex[(s[19] & 0x3) | 0x8];
  s[8] = s[13] = s[18] = s[23] = "-";
  return s.join("");
}

function request({ url, method = "GET", data, header = {} }) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBase()}${url}`,
      method,
      data,
      header: { "Content-Type": "application/json", ...header },
      success: (res) => resolve(res.data),
      fail: reject,
    });
  });
}

function uploadObject({ uploadId, filePath, filename, index, taskType }) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${apiBase()}/v1/uploads/${uploadId}/objects`,
      filePath,
      name: "file",
      formData: {
        index: String(index),
        taskType,
        task_type: taskType,
      },
      success: (res) => {
        try {
          resolve(JSON.parse(res.data));
        } catch (e) {
          reject(e);
        }
      },
      fail: reject,
    });
  });
}

module.exports = { apiBase, uuid, request, uploadObject };
