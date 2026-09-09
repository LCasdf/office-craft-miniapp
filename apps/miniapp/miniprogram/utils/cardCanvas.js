/** Draw character card to canvas 2d and export temp PNG path. */

const TEMPLATES = {
  doc: {
    bg: "#fafaf9",
    fg: "#1c1917",
    muted: "#78716c",
    accent: "#44403c",
    tagBg: "#f5f5f4",
    tagFg: "#44403c",
    line: "#d6d3d1",
  },
  dossier: {
    bg: "#1c1917",
    fg: "#f5f5f4",
    muted: "#a8a29e",
    accent: "#d6a756",
    tagBg: "#292524",
    tagFg: "#e7e5e4",
    line: "#44403c",
  },
  fresh: {
    bg: "#ecfdf5",
    fg: "#064e3b",
    muted: "#047857",
    accent: "#0d9488",
    tagBg: "#ccfbf1",
    tagFg: "#115e59",
    line: "#99f6e4",
  },
};

function wrapText(ctx, text, maxWidth, maxLines) {
  const chars = String(text || "").split("");
  const lines = [];
  let line = "";
  for (let i = 0; i < chars.length; i++) {
    const trial = line + chars[i];
    if (ctx.measureText(trial).width <= maxWidth) {
      line = trial;
    } else {
      if (line) lines.push(line);
      line = chars[i];
      if (lines.length >= maxLines) break;
    }
  }
  if (line && lines.length < maxLines) lines.push(line);
  if (!lines.length) lines.push("");
  return lines;
}

function drawCard(canvas, form, opts) {
  const dpr = (opts && opts.dpr) || 2;
  const W = 375;
  const H = 560;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const t = TEMPLATES[form.templateId] || TEMPLATES.doc;
  ctx.fillStyle = t.bg;
  ctx.fillRect(0, 0, W, H);

  // frame
  ctx.strokeStyle = t.line;
  ctx.lineWidth = 1;
  ctx.strokeRect(16, 16, W - 32, H - 32);

  // accent top bar
  ctx.fillStyle = t.accent;
  ctx.fillRect(16, 16, W - 32, 4);

  // avatar box
  const ax = 36;
  const ay = 40;
  const as = 72;
  ctx.strokeStyle = t.line;
  ctx.strokeRect(ax, ay, as, as);
  if (form.avatarPath) {
    // image drawn async by caller if needed — placeholder letter
  }
  ctx.fillStyle = t.tagBg;
  ctx.fillRect(ax + 1, ay + 1, as - 2, as - 2);
  ctx.fillStyle = t.muted;
  ctx.font = "28px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText((form.name || "?").slice(0, 1), ax + as / 2, ay + as / 2 + 10);
  ctx.textAlign = "left";

  // name + title
  ctx.fillStyle = t.fg;
  ctx.font = "bold 22px sans-serif";
  ctx.fillText((form.name || "未命名角色").slice(0, 12), ax + as + 16, ay + 28);
  ctx.fillStyle = t.accent;
  ctx.font = "14px sans-serif";
  ctx.fillText((form.title || "").slice(0, 16), ax + as + 16, ay + 52);

  // tags
  let tx = 36;
  const ty = 132;
  const tags = [form.personality, form.ability, form.weakness]
    .map((s) => String(s || "").trim())
    .filter(Boolean)
    .map((s) => s.slice(0, 8));
  ctx.font = "12px sans-serif";
  tags.slice(0, 3).forEach((tag) => {
    const tw = ctx.measureText(tag).width + 16;
    ctx.fillStyle = t.tagBg;
    ctx.fillRect(tx, ty, tw, 24);
    ctx.fillStyle = t.tagFg;
    ctx.fillText(tag, tx + 8, ty + 16);
    tx += tw + 8;
  });

  // body
  let y = 176;
  ctx.fillStyle = t.accent;
  ctx.font = "13px sans-serif";
  ctx.fillText("形象外貌", 36, y);
  y += 18;
  ctx.fillStyle = t.fg;
  ctx.font = "13px sans-serif";
  wrapText(ctx, form.avatarDesc, W - 72, 4).forEach((ln) => {
    ctx.fillText(ln, 36, y);
    y += 18;
  });
  y += 10;
  ctx.fillStyle = t.accent;
  ctx.fillText("背景故事", 36, y);
  y += 18;
  ctx.fillStyle = t.fg;
  wrapText(ctx, form.story, W - 72, 6).forEach((ln) => {
    ctx.fillText(ln, 36, y);
    y += 18;
  });

  // footer
  ctx.fillStyle = t.muted;
  ctx.font = "11px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("文匠工具 · 角色卡", W / 2, H - 28);
  ctx.textAlign = "left";
}

function exportCardImage(component, canvasId, form) {
  return new Promise((resolve, reject) => {
    const q = component
      ? wx.createSelectorQuery().in(component)
      : wx.createSelectorQuery();
    q.select(`#${canvasId}`)
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) {
          reject(new Error("canvas missing"));
          return;
        }
        const canvas = res[0].node;
        try {
          drawCard(canvas, form, { dpr: wx.getSystemInfoSync().pixelRatio || 2 });
        } catch (e) {
          reject(e);
          return;
        }
        setTimeout(() => {
          wx.canvasToTempFilePath({
            canvas,
            fileType: "png",
            quality: 1,
            success: (r) => resolve(r.tempFilePath),
            fail: reject,
          });
        }, 50);
      });
  });
}

module.exports = { TEMPLATES, drawCard, exportCardImage };
