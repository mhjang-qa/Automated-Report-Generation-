const state = {
  sourceUrl: "",
  sourcePageId: "",
  title: "",
  sourceContent: "",
  summary: "",
  notionPageId: "",
  notionPageUrl: "",
  tcMarkdown: "",
  busy: false,
  loginBusy: false,
  isAnalyzing: false,
};

const el = {
  loadingView: document.querySelector("#loadingView"),
  loginView: document.querySelector("#loginView"),
  appView: document.querySelector("#appView"),
  loginForm: document.querySelector("#loginForm"),
  loginPassword: document.querySelector("#loginPassword"),
  loginBtn: document.querySelector("#loginBtn"),
  loginMessage: document.querySelector("#loginMessage"),
  notionUrl: document.querySelector("#notionUrl"),
  analyzeBtn: document.querySelector("#analyzeBtn"),
  registerBtn: document.querySelector("#registerBtn"),
  generateTcBtn: document.querySelector("#generateTcBtn"),
  uploadTcBtn: document.querySelector("#uploadTcBtn"),
  copySummaryBtn: document.querySelector("#copySummaryBtn"),
  copyTcBtn: document.querySelector("#copyTcBtn"),
  summaryPreview: document.querySelector("#summaryPreview"),
  tcPreview: document.querySelector("#tcPreview"),
  summaryMeta: document.querySelector("#summaryMeta"),
  tcMeta: document.querySelector("#tcMeta"),
  message: document.querySelector("#message"),
  phaseBadge: document.querySelector("#phaseBadge"),
  linkPanel: document.querySelector("#linkPanel"),
  notionPageLink: document.querySelector("#notionPageLink"),
};

const FLOOR_RISE_LOADING_DURATION_MS = 10200;
const HEALTH_POLL_INTERVAL_MS = 1500;

function showView(view) {
  if (el.loadingView) {
    el.loadingView.classList.toggle("hidden", view !== "loading");
  }
  el.loginView.classList.toggle("hidden", view !== "login");
  el.appView.classList.toggle("hidden", view !== "app");
  if (view === "login") {
    el.loginPassword.focus();
  }
  if (view === "app") {
    el.notionUrl.focus();
  }
}

function completeLoading() {
  showView("login");
  destroyLoadingView();
}

function destroyLoadingView() {
  if (!el.loadingView) return;
  const iframe = el.loadingView.querySelector("iframe");
  if (iframe) {
    iframe.src = "about:blank";
  }
  el.loadingView.remove();
  el.loadingView = null;
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function setBusy(isBusy, phase = "대기 중") {
  state.busy = isBusy;
  el.phaseBadge.textContent = phase;
  el.phaseBadge.className = `phase${isBusy ? " busy" : ""}`;
  syncButtons();
}

function setDone(message) {
  el.phaseBadge.textContent = "완료";
  el.phaseBadge.className = "phase done";
  showMessage(message, "success");
  syncButtons();
}

function setError(message) {
  el.phaseBadge.textContent = "오류";
  el.phaseBadge.className = "phase error";
  showMessage(message, "error");
  syncButtons();
}

function showMessage(message, type = "") {
  el.message.textContent = message || "";
  el.message.className = `message ${type}`.trim();
}

function syncButtons() {
  const busy = state.busy || state.isAnalyzing;
  el.analyzeBtn.disabled = busy;
  el.registerBtn.disabled = busy || !state.summary;
  el.generateTcBtn.disabled = busy || !state.summary;
  el.uploadTcBtn.disabled = busy || !state.tcMarkdown || !state.notionPageId;
  el.copySummaryBtn.disabled = !state.summary;
  el.copyTcBtn.disabled = !state.tcMarkdown;
}

function setPreview(node, value, emptyText) {
  node.textContent = value || emptyText;
  node.classList.toggle("empty", !value);
}

async function apiPost(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    throw new Error(data.message || "요청 처리에 실패했습니다.");
  }
  return data;
}

async function waitForBackendReady() {
  while (true) {
    try {
      const res = await fetch("/api/health", {
        method: "GET",
        cache: "no-store",
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        return;
      }
    } catch (error) {
      console.debug("Backend is not ready yet.", error);
    }
    await delay(HEALTH_POLL_INTERVAL_MS);
  }
}

async function bootApp() {
  showView("loading");
  await Promise.all([delay(FLOOR_RISE_LOADING_DURATION_MS), waitForBackendReady()]);
  completeLoading();
}

async function login(event) {
  event.preventDefault();
  if (state.loginBusy) return;
  state.loginBusy = true;
  el.loginBtn.disabled = true;
  el.loginMessage.textContent = "";
  try {
    await apiPost("/api/login", {
      password: el.loginPassword.value,
    });
    sessionStorage.setItem("arg_authenticated", "true");
    showView("app");
  } catch (error) {
    console.error(error);
    el.loginMessage.textContent = error.message;
  } finally {
    state.loginBusy = false;
    el.loginBtn.disabled = false;
  }
}

async function analyze() {
  if (state.isAnalyzing) {
    return;
  }
  const url = el.notionUrl.value.trim();
  if (!url) {
    setError("노션 링크를 입력해 주세요.");
    return;
  }
  state.isAnalyzing = true;
  setBusy(true, "분석 중");
  el.analyzeBtn.disabled = true;
  showMessage("노션 페이지를 읽고 Gemini로 요약을 생성하는 중입니다.");
  try {
    const data = await apiPost("/api/analyze", { url });
    Object.assign(state, {
      sourceUrl: data.sourceUrl,
      sourcePageId: data.sourcePageId,
      title: data.title,
      sourceContent: data.sourceContent,
      summary: data.summary,
      tcMarkdown: "",
    });
    setPreview(el.summaryPreview, state.summary, "요약 결과가 여기에 표시됩니다.");
    setPreview(el.tcPreview, "", "TC 결과가 여기에 표시됩니다.");
    el.summaryMeta.textContent = state.title;
    el.tcMeta.textContent = "";
    setDone("요약 생성이 완료되었습니다.");
  } catch (error) {
    console.error(error);
    setError(error.message);
  } finally {
    state.isAnalyzing = false;
    state.busy = false;
    syncButtons();
  }
}

async function registerSummary() {
  setBusy(true, "저장 중");
  showMessage("요약 결과를 대상 노션 DB에 저장하는 중입니다.");
  try {
    const data = await apiPost("/api/register-summary", {
      sourceUrl: state.sourceUrl,
      title: state.title,
      summary: state.summary,
    });
    state.notionPageId = data.page_id;
    state.notionPageUrl = data.url;
    renderNotionLink();
    setDone("노션 등록이 완료되었습니다.");
  } catch (error) {
    console.error(error);
    setError(error.message);
  } finally {
    state.busy = false;
    syncButtons();
  }
}

async function generateTc() {
  setBusy(true, "TC 생성 중");
  showMessage("요약 내용을 기반으로 테스트 케이스를 생성하는 중입니다.");
  try {
    const data = await apiPost("/api/generate-tc", {
      title: state.title,
      summary: state.summary,
      sourceContent: state.sourceContent,
    });
    state.tcMarkdown = data.tcMarkdown;
    setPreview(el.tcPreview, state.tcMarkdown, "TC 결과가 여기에 표시됩니다.");
    el.tcMeta.textContent = "Markdown Table";
    setDone("TC 생성이 완료되었습니다.");
  } catch (error) {
    console.error(error);
    setError(error.message);
  } finally {
    state.busy = false;
    syncButtons();
  }
}

async function uploadTc() {
  setBusy(true, "업로드 중");
  showMessage("생성된 TC를 노션 페이지 하단에 업로드하는 중입니다.");
  try {
    const data = await apiPost("/api/upload-tc", {
      pageId: state.notionPageId,
      tcMarkdown: state.tcMarkdown,
    });
    state.notionPageUrl = data.url || state.notionPageUrl;
    renderNotionLink();
    setDone("TC 업로드가 완료되었습니다.");
  } catch (error) {
    console.error(error);
    setError(error.message);
  } finally {
    state.busy = false;
    syncButtons();
  }
}

async function copyText(value, label) {
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    showMessage(`${label} 복사가 완료되었습니다.`, "success");
  } catch (error) {
    console.error(error);
    showMessage("브라우저 클립보드 권한 때문에 복사하지 못했습니다.", "error");
  }
}

function renderNotionLink() {
  if (!state.notionPageUrl) return;
  el.linkPanel.classList.remove("hidden");
  el.notionPageLink.href = state.notionPageUrl;
  el.notionPageLink.textContent = state.notionPageUrl;
}

el.analyzeBtn.addEventListener("click", analyze);
el.registerBtn.addEventListener("click", registerSummary);
el.generateTcBtn.addEventListener("click", generateTc);
el.uploadTcBtn.addEventListener("click", uploadTc);
el.copySummaryBtn.addEventListener("click", () => copyText(state.summary, "요약 결과"));
el.copyTcBtn.addEventListener("click", () => copyText(state.tcMarkdown, "TC 결과"));
el.loginForm.addEventListener("submit", login);
el.notionUrl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") analyze();
});

syncButtons();
bootApp();
