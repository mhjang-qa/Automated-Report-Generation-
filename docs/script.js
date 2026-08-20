const APPS = {
  report: {
    label: "자동 리포트",
    renderUrl: "https://automated-report-generation-dh2g.onrender.com",
    healthPath: "/api/health",
    appPath: "/?app=1&skipIntro=1",
    readyStatus: ["ready", "running", "ok"],
  },
  defect: {
    label: "결함 대시보드",
    staticUrl: "./defect-dashboard/hanpass-renewal.html",
    renderUrl: "https://notion-daily-defect-dashboard.onrender.com",
    healthPath: "/api/health",
    appPath: "/",
    readyStatus: ["ok"],
  },
};
const POLL_INTERVAL_MS = 2500;
const SLOW_ATTEMPTS = 8;
const LOADING_LOOP_MS = 9200;

const loadingFrame = document.querySelector("#loadingFrame");
const statusText = document.querySelector("#statusText");
const hintText = document.querySelector("#hintText");
const tabs = Array.from(document.querySelectorAll(".app-tab"));
let attempts = 0;
let redirecting = false;
let activeAppKey = window.location.hash.replace("#", "") === "defect" ? "defect" : "report";
let pollToken = 0;

function setMessage(status, hint) {
  statusText.textContent = status;
  hintText.textContent = hint;
}

function activeApp() {
  return APPS[activeAppKey];
}

function isReady(data, app) {
  const status = String(data.status || "").toLowerCase();
  if (data.ok === true && !status) return true;
  return app.readyStatus.includes(status);
}

async function waitForRender(token = pollToken) {
  if (redirecting) return;
  const app = activeApp();
  if (app.staticUrl) {
    redirecting = true;
    setMessage(`${app.label} 정적 화면으로 이동합니다.`, "GitHub Pages에 저장된 마지막 Snapshot을 표시합니다.");
    window.setTimeout(() => window.location.replace(app.staticUrl), 250);
    return;
  }
  attempts += 1;
  try {
    const response = await fetch(`${app.renderUrl}${app.healthPath}?t=${Date.now()}`, {
      method: "GET",
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (token !== pollToken) return;
    if (response.ok && isReady(data, app)) {
      redirecting = true;
      setMessage("서버 준비가 완료되었습니다.", `잠시 후 ${app.label}(으)로 이동합니다.`);
      window.setTimeout(() => window.location.replace(`${app.renderUrl}${app.appPath}`), 650);
      return;
    }
  } catch (error) {
    console.debug("Render is not ready yet.", error);
  }

  if (token !== pollToken) return;
  if (attempts >= SLOW_ATTEMPTS) {
    setMessage(
      "서버 준비가 예상보다 오래 걸리고 있습니다.",
      "새로고침하지 않아도 준비 완료 후 자동으로 이동합니다.",
    );
  }
  window.setTimeout(() => waitForRender(token), POLL_INTERVAL_MS);
}

function restartLoadingAnimation() {
  if (redirecting || !loadingFrame) return;
  loadingFrame.src = `./logding/index.html?loop=${Date.now()}`;
}

window.setInterval(restartLoadingAnimation, LOADING_LOOP_MS);

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const appKey = tab.dataset.app;
    if (!appKey || appKey === activeAppKey || !APPS[appKey]) return;
    activeAppKey = appKey;
    attempts = 0;
    redirecting = false;
    pollToken += 1;
    tabs.forEach((item) => item.classList.toggle("active", item === tab));
    window.history.replaceState(null, "", `#${appKey}`);
    setMessage(`${APPS[appKey].label} 서버를 준비하는 중입니다.`, "Render Cold Start로 인해 초기 접속 시간이 소요될 수 있습니다.");
    waitForRender(pollToken);
  });
});

tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.app === activeAppKey));
setMessage(`${activeApp().label} 서버를 준비하는 중입니다.`, "Render Cold Start로 인해 초기 접속 시간이 소요될 수 있습니다.");
waitForRender(pollToken);
