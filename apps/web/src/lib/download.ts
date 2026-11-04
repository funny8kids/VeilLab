export function downloadTextFile(
  filename: string,
  content: string,
  mimeType = "application/json",
): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function makeDemoTxHash(seed: string): string {
  let state = 0;
  for (let index = 0; index < seed.length; index += 1) {
    state = (state * 31 + seed.charCodeAt(index)) >>> 0;
  }
  let hash = "";
  for (let index = 0; index < 8; index += 1) {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    hash += state.toString(16).padStart(8, "0");
  }
  return `0x${hash}`;
}
