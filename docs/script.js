const RENDER_URL = "https://automated-report-generation-dh2g.onrender.com";
const HEALTH_URL = `${RENDER_URL}/api/health`;
const APP_URL = `${RENDER_URL}/?app=1&skipIntro=1`;
const POLL_INTERVAL_MS = 2500;
const SLOW_ATTEMPTS = 8;
const LOADING_LOOP_MS = 11200;

const loadingFrame = document.querySelector("#loadingFrame");
const statusText = document.querySelector("#statusText");
const hintText = document.querySelector("#hintText");
let attempts = 0;
let redirecting = false;

function setMessage(status, hint) {
  statusText.textContent = status;
  hintText.textContent = hint;
}

function isReady(data) {
  const status = String(data.status || "").toLowerCase();
  return data.ok === true && (!status || ["ready", "running", "ok"].includes(status));
}

async function waitForRender() {
  if (redirecting) return;
  attempts += 1;
  try {
    const response = await fetch(`${HEALTH_URL}?t=${Date.now()}`, {
      method: "GET",
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok && isReady(data)) {
      redirecting = true;
      setMessage("서버 준비가 완료되었습니다.", "잠시 후 로그인 화면으로 이동합니다.");
      window.setTimeout(() => window.location.replace(APP_URL), 650);
      return;
    }
  } catch (error) {
    console.debug("Render is not ready yet.", error);
  }

  if (attempts >= SLOW_ATTEMPTS) {
    setMessage(
      "서버 준비가 예상보다 오래 걸리고 있습니다.",
      "새로고침하지 않아도 준비 완료 후 자동으로 이동합니다.",
    );
  }
  window.setTimeout(waitForRender, POLL_INTERVAL_MS);
}

function restartLoadingAnimation() {
  if (redirecting || !loadingFrame) return;
  loadingFrame.src = `./logding/index.html?loop=${Date.now()}`;
}

window.setInterval(restartLoadingAnimation, LOADING_LOOP_MS);
waitForRender();
