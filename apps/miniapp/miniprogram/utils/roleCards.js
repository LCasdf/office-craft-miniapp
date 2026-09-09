/**
 * 角色卡集本地仓库
 * - draft：文字人设（编辑素材）
 * - cardImagePath：渲染后的竖版角色卡图片（成品）
 * - status：draft | ready（由是否有成品图推导）
 */
const STORAGE_KEY = "roleCardList";

function uuid() {
  const s = [];
  const hex = "0123456789abcdef";
  for (let i = 0; i < 36; i++) s[i] = hex[(Math.random() * 16) | 0];
  s[14] = "4";
  s[19] = hex[(s[19] & 0x3) | 0x8];
  s[8] = s[13] = s[18] = s[23] = "-";
  return s.join("");
}

function listCards() {
  try {
    const raw = wx.getStorageSync(STORAGE_KEY);
    if (!Array.isArray(raw)) return [];
    return raw.map(normalizeCard);
  } catch (e) {
    return [];
  }
}

function saveAll(list) {
  wx.setStorageSync(STORAGE_KEY, list || []);
}

function normalizeCard(card) {
  const c = card || {};
  // 兼容旧字段 coverPath
  const cardImagePath = c.cardImagePath || c.coverPath || "";
  const status = cardImagePath ? "ready" : "draft";
  return Object.assign({}, c, {
    cardImagePath,
    coverPath: cardImagePath,
    status,
    hasCardImage: !!cardImagePath,
    statusLabel: status === "ready" ? "已出图" : "草稿",
  });
}

function getCard(id) {
  return listCards().find((c) => c.id === id) || null;
}

function upsertCard(card) {
  const list = listCards().map((c) => ({
    id: c.id,
    prompt: c.prompt,
    name: c.name,
    title: c.title,
    avatarPath: c.avatarPath,
    avatarDesc: c.avatarDesc,
    personality: c.personality,
    story: c.story,
    ability: c.ability,
    weakness: c.weakness,
    remark: c.remark,
    templateId: c.templateId,
    cardImagePath: c.cardImagePath || c.coverPath || "",
    createdAt: c.createdAt,
    updatedAt: c.updatedAt,
  }));
  const now = Date.now();
  const imagePath = card.cardImagePath || card.coverPath || "";
  const next = {
    id: card.id,
    prompt: card.prompt || "",
    name: card.name || "",
    title: card.title || "",
    avatarPath: card.avatarPath || "",
    avatarDesc: card.avatarDesc || "",
    personality: card.personality || "",
    story: card.story || "",
    ability: card.ability || "",
    weakness: card.weakness || "",
    remark: card.remark || "",
    templateId: card.templateId || "doc",
    cardImagePath: imagePath,
    status: imagePath ? "ready" : "draft",
    createdAt: card.createdAt || now,
    updatedAt: now,
  };
  const idx = list.findIndex((c) => c.id === next.id);
  if (idx >= 0) list[idx] = next;
  else list.unshift(next);
  saveAll(list);
  return normalizeCard(next);
}

function removeCard(id) {
  const list = listCards()
    .filter((c) => c.id !== id)
    .map((c) => ({
      id: c.id,
      prompt: c.prompt,
      name: c.name,
      title: c.title,
      avatarPath: c.avatarPath,
      avatarDesc: c.avatarDesc,
      personality: c.personality,
      story: c.story,
      ability: c.ability,
      weakness: c.weakness,
      remark: c.remark,
      templateId: c.templateId,
      cardImagePath: c.cardImagePath,
      createdAt: c.createdAt,
      updatedAt: c.updatedAt,
    }));
  saveAll(list);
  return list;
}

function emptyForm() {
  return {
    id: "",
    prompt: "",
    name: "",
    title: "",
    avatarPath: "",
    avatarDesc: "",
    personality: "",
    story: "",
    ability: "",
    weakness: "",
    remark: "",
    templateId: "doc",
    status: "draft",
    cardImagePath: "",
    coverPath: "",
  };
}

/** 将临时渲染图复制到用户目录，避免 temp 被清掉后列表空白 */
function persistCardImage(tempPath, cardId) {
  return new Promise((resolve, reject) => {
    if (!tempPath) {
      reject(new Error("empty path"));
      return;
    }
    const fs = wx.getFileSystemManager();
    const dir = `${wx.env.USER_DATA_PATH}/rolecards`;
    const dest = `${dir}/${cardId || uuid()}.png`;
    const ensureDir = (cb) => {
      fs.access({
        path: dir,
        success: () => cb(),
        fail: () => {
          fs.mkdir({
            dirPath: dir,
            recursive: true,
            success: () => cb(),
            fail: reject,
          });
        },
      });
    };
    ensureDir(() => {
      fs.copyFile({
        srcPath: tempPath,
        destPath: dest,
        success: () => resolve(dest),
        fail: () => {
          // 部分环境 copyFile 失败时退回原路径
          resolve(tempPath);
        },
      });
    });
  });
}

module.exports = {
  STORAGE_KEY,
  uuid,
  listCards,
  getCard,
  upsertCard,
  removeCard,
  emptyForm,
  normalizeCard,
  persistCardImage,
};
