// Copy third-party browser files into static/ so the app needs no CDN (keeps the CSP strict).
import { cpSync, mkdirSync } from "node:fs";

const files = {
  "node_modules/chart.js/dist/chart.umd.min.js": "static/vendor/chart.umd.min.js",
  "node_modules/chart.js/dist/chart.umd.min.js.map": "static/vendor/chart.umd.min.js.map",
  "node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2": "static/fonts/inter.woff2",
  "node_modules/@fontsource-variable/space-grotesk/files/space-grotesk-latin-wght-normal.woff2": "static/fonts/space-grotesk.woff2",
};
for (const [from, to] of Object.entries(files)) {
  mkdirSync(to.slice(0, to.lastIndexOf("/")), { recursive: true });
  cpSync(from, to);
}
console.log("vendor files copied");
