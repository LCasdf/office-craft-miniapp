export function createIdempotencyKey() {
  // UUIDv4-ish for mini program without crypto.randomUUID polyfill guarantee
  const s = [];
  const hex = "0123456789abcdef";
  for (let i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) s.push("-");
    else if (i === 14) s.push("4");
    else if (i === 19) s.push(hex[(Math.random() * 4) | 8]);
    else s.push(hex[(Math.random() * 16) | 0]);
  }
  return s.join("");
}
