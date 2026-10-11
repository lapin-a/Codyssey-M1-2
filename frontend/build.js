// Vercel 빌드 시 환경 변수 API_BASE_URL 을 읽어 public/config.js 를 만든다.
// 로컬에서 실행하면 기본값 http://localhost:8000 을 쓴다.
const fs = require("fs");
const path = require("path");

const apiBase = (process.env.API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
const out = path.join(__dirname, "public", "config.js");
fs.writeFileSync(out, `window.API_BASE_URL = ${JSON.stringify(apiBase)};\n`);
console.log(`config.js 생성: API_BASE_URL=${apiBase}`);
