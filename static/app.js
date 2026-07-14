const state = {
  sourceUrl: "",
  sourcePageId: "",
  title: "",
  sourceContent: "",
  summary: "",
  notionPageId: "",
  notionPageUrl: "",
  tcMarkdown: "",
  embedHtml: "",
  embedFilename: "report.html",
  busy: false,
  embedBusy: false,
  pixelBusy: false,
  pixelImageDataUrl: "",
  pixelRenderCacheKey: "",
  pixelRenderData: null,
  pixelActualLoaded: false,
  pixelActualStartUrl: "",
  pixelParsed: null,
  localizationUrl: "",
  localizationRepoUrl: "https://github.com/mhjang-qa/go_hanpass_localization_validator",
  loginBusy: false,
  isAnalyzing: false,
  geminiRetryUntil: 0,
  geminiLimitReason: "",
};

const el = {
  loadingView: document.querySelector("#loadingView"),
  loginView: document.querySelector("#loginView"),
  appView: document.querySelector("#appView"),
  loadingStatus: document.querySelector("#loadingStatus"),
  loadingHint: document.querySelector("#loadingHint"),
  loginForm: document.querySelector("#loginForm"),
  loginPassword: document.querySelector("#loginPassword"),
  loginBtn: document.querySelector("#loginBtn"),
  loginMessage: document.querySelector("#loginMessage"),
  notionUrl: document.querySelector("#notionUrl"),
  ticketTab: document.querySelector("#ticketTab"),
  embedTab: document.querySelector("#embedTab"),
  pixelTab: document.querySelector("#pixelTab"),
  localizationTab: document.querySelector("#localizationTab"),
  ticketView: document.querySelector("#ticketView"),
  embedView: document.querySelector("#embedView"),
  pixelView: document.querySelector("#pixelView"),
  localizationView: document.querySelector("#localizationView"),
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
  embedType: document.querySelector("#embedType"),
  embedVersion: document.querySelector("#embedVersion"),
  embedTitle: document.querySelector("#embedTitle"),
  embedFilename: document.querySelector("#embedFilename"),
  embedNotionUrl: document.querySelector("#embedNotionUrl"),
  embedDefectDbUrl: document.querySelector("#embedDefectDbUrl"),
  embedTargetVersion: document.querySelector("#embedTargetVersion"),
  embedTargetVersionList: document.querySelector("#embedTargetVersionList"),
  embedDefectFields: document.querySelector("#embedDefectFields"),
  embedTcFields: document.querySelector("#embedTcFields"),
  embedEndFields: document.querySelector("#embedEndFields"),
  tcAosPass: document.querySelector("#tcAosPass"),
  tcAosFail: document.querySelector("#tcAosFail"),
  tcAosNa: document.querySelector("#tcAosNa"),
  tcIosPass: document.querySelector("#tcIosPass"),
  tcIosFail: document.querySelector("#tcIosFail"),
  tcIosNa: document.querySelector("#tcIosNa"),
  endTotal: document.querySelector("#endTotal"),
  endFixed: document.querySelector("#endFixed"),
  endFuture: document.querySelector("#endFuture"),
  endInvalid: document.querySelector("#endInvalid"),
  endNote: document.querySelector("#endNote"),
  embedRawText: document.querySelector("#embedRawText"),
  embedMessage: document.querySelector("#embedMessage"),
  embedMeta: document.querySelector("#embedMeta"),
  embedPreview: document.querySelector("#embedPreview"),
  generateEmbedBtn: document.querySelector("#generateEmbedBtn"),
  copyEmbedHtmlBtn: document.querySelector("#copyEmbedHtmlBtn"),
  downloadEmbedHtmlBtn: document.querySelector("#downloadEmbedHtmlBtn"),
  loadTargetVersionsBtn: document.querySelector("#loadTargetVersionsBtn"),
  pixelFigmaUrl: document.querySelector("#pixelFigmaUrl"),
  pixelFigmaImageUrl: document.querySelector("#pixelFigmaImageUrl"),
  pixelFigmaImageFile: document.querySelector("#pixelFigmaImageFile"),
  pixelPageUrl: document.querySelector("#pixelPageUrl"),
  pixelStartUrl: document.querySelector("#pixelStartUrl"),
  pixelViewportPreset: document.querySelector("#pixelViewportPreset"),
  pixelFrameSelect: document.querySelector("#pixelFrameSelect"),
  pixelWidth: document.querySelector("#pixelWidth"),
  pixelHeight: document.querySelector("#pixelHeight"),
  pixelMessage: document.querySelector("#pixelMessage"),
  pixelLoadFramesBtn: document.querySelector("#pixelLoadFramesBtn"),
  pixelLaunchActualBtn: document.querySelector("#pixelLaunchActualBtn"),
  pixelRenderBtn: document.querySelector("#pixelRenderBtn"),
  pixelDeviceBtn: document.querySelector("#pixelDeviceBtn"),
  pixelOpenUrlBtn: document.querySelector("#pixelOpenUrlBtn"),
  pixelModeWeb: document.querySelector("#pixelModeWeb"),
  pixelModeApp: document.querySelector("#pixelModeApp"),
  pixelExcludeChrome: document.querySelector("#pixelExcludeChrome"),
  pixelExcludeTop: document.querySelector("#pixelExcludeTop"),
  pixelExcludeBottom: document.querySelector("#pixelExcludeBottom"),
  pixelOpacity: document.querySelector("#pixelOpacity"),
  pixelOffsetX: document.querySelector("#pixelOffsetX"),
  pixelOffsetY: document.querySelector("#pixelOffsetY"),
  pixelScale: document.querySelector("#pixelScale"),
  pixelReadout: document.querySelector("#pixelReadout"),
  pixelMeta: document.querySelector("#pixelMeta"),
  pixelCompareGrid: document.querySelector("#pixelCompareGrid"),
  pixelFigmaStage: document.querySelector("#pixelFigmaStage"),
  pixelActualStage: document.querySelector("#pixelActualStage"),
  pixelStage: document.querySelector("#pixelStage"),
  pixelFigmaOnlyImage: document.querySelector("#pixelFigmaOnlyImage"),
  pixelActualScreenshot: document.querySelector("#pixelActualScreenshot"),
  pixelOverlayActualScreenshot: document.querySelector("#pixelOverlayActualScreenshot"),
  pixelActualFigmaImage: document.querySelector("#pixelActualFigmaImage"),
  pixelFigmaImage: document.querySelector("#pixelFigmaImage"),
  pixelEmptyState: document.querySelector("#pixelEmptyState"),
  localizationFrame: document.querySelector("#localizationFrame"),
  localizationMessage: document.querySelector("#localizationMessage"),
  localizationReloadBtn: document.querySelector("#localizationReloadBtn"),
  localizationOpenBtn: document.querySelector("#localizationOpenBtn"),
  localizationRepoBtn: document.querySelector("#localizationRepoBtn"),
};

const FLOOR_RISE_LOADING_DURATION_MS = 8200;
const HEALTH_POLL_INTERVAL_MS = 2500;
const SLOW_HEALTH_CHECK_ATTEMPTS = 8;
let geminiCooldownTimer = null;

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

function setLoadingMessage(status, hint) {
  if (el.loadingStatus) {
    el.loadingStatus.textContent = status;
  }
  if (el.loadingHint) {
    el.loadingHint.textContent = hint;
  }
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

function showEmbedMessage(message, type = "") {
  el.embedMessage.textContent = message || "";
  el.embedMessage.className = `message ${type}`.trim();
}

function showPixelMessage(message, type = "") {
  el.pixelMessage.textContent = message || "";
  el.pixelMessage.className = `message ${type}`.trim();
}

function showLocalizationMessage(message, type = "") {
  el.localizationMessage.textContent = message || "";
  el.localizationMessage.className = `message ${type}`.trim();
}

function switchTab(tabName) {
  const isTicket = tabName === "ticket";
  const isEmbed = tabName === "embed";
  const isPixel = tabName === "pixel";
  const isLocalization = tabName === "localization";
  el.ticketTab.classList.toggle("active", isTicket);
  el.embedTab.classList.toggle("active", isEmbed);
  el.pixelTab.classList.toggle("active", isPixel);
  el.localizationTab.classList.toggle("active", isLocalization);
  el.ticketView.classList.toggle("hidden", !isTicket);
  el.embedView.classList.toggle("hidden", !isEmbed);
  el.pixelView.classList.toggle("hidden", !isPixel);
  el.localizationView.classList.toggle("hidden", !isLocalization);
  if (isEmbed) {
    el.phaseBadge.textContent = "HTML 생성";
    el.phaseBadge.className = "phase";
    el.embedNotionUrl.focus();
  } else if (isPixel) {
    el.phaseBadge.textContent = "PixelAudit";
    el.phaseBadge.className = "phase";
    el.pixelFigmaUrl.focus();
  } else if (isLocalization) {
    el.phaseBadge.textContent = "다국어 검증";
    el.phaseBadge.className = "phase";
    loadLocalizationApp();
  } else {
    el.phaseBadge.textContent = "대기 중";
    el.phaseBadge.className = "phase";
    el.notionUrl.focus();
  }
}

async function loadLocalizationApp(force = false) {
  if (state.localizationUrl && !force) return;
  showLocalizationMessage("다국어 검증 앱 설정을 확인하는 중입니다.");
  try {
    const res = await fetch("/api/localization-config", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      el.localizationFrame.src = "about:blank";
      el.localizationOpenBtn.removeAttribute("href");
      el.localizationRepoBtn.href = data.repoUrl || state.localizationRepoUrl;
      throw new Error(data.message || "다국어 검증 앱 설정을 불러오지 못했습니다.");
    }
    state.localizationUrl = data.url;
    state.localizationRepoUrl = data.repoUrl || state.localizationRepoUrl;
    el.localizationFrame.src = state.localizationUrl;
    el.localizationOpenBtn.href = state.localizationUrl;
    el.localizationRepoBtn.href = state.localizationRepoUrl;
    showLocalizationMessage(`연결 URL: ${state.localizationUrl}`, "success");
  } catch (error) {
    showLocalizationMessage(error.message || "다국어 검증 앱을 불러오지 못했습니다.", "error");
  }
}

function reloadLocalizationApp() {
  state.localizationUrl = "";
  el.localizationFrame.src = "about:blank";
  loadLocalizationApp(true);
}

function syncButtons() {
  const busy = state.busy || state.isAnalyzing;
  el.analyzeBtn.disabled = busy || isGeminiCoolingDown();
  el.registerBtn.disabled = busy || !state.summary;
  el.generateTcBtn.disabled = busy || !state.summary;
  el.uploadTcBtn.disabled = busy || !state.tcMarkdown || !state.notionPageId;
  el.copySummaryBtn.disabled = !state.summary;
  el.copyTcBtn.disabled = !state.tcMarkdown;
  el.generateEmbedBtn.disabled = state.embedBusy;
  el.loadTargetVersionsBtn.disabled = state.embedBusy;
  el.copyEmbedHtmlBtn.disabled = !state.embedHtml;
  el.downloadEmbedHtmlBtn.disabled = !state.embedHtml;
  el.pixelLoadFramesBtn.disabled = state.pixelBusy;
  el.pixelLaunchActualBtn.disabled = state.pixelBusy;
  el.pixelRenderBtn.disabled = state.pixelBusy;
  el.pixelDeviceBtn.disabled = state.pixelBusy;
}

function setPreview(node, value, emptyText) {
  node.textContent = value || emptyText;
  node.classList.toggle("empty", !value);
}

async function apiPost(path, payload) {
  let res;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    const networkError = new Error("API 서버에 연결하지 못했습니다. Render 배포 상태와 네트워크를 확인해 주세요.");
    networkError.status = 0;
    networkError.cause = error;
    throw networkError;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    const error = new Error(apiErrorMessage(path, res.status, data));
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
}

function apiErrorMessage(path, status, data) {
  const message = data.message || "요청 처리에 실패했습니다.";
  if (data.code === "FIGMA_RATE_LIMIT" || status === 429) {
    const retry = data.retryAfterSeconds ? ` 약 ${data.retryAfterSeconds}초 후 재시도하거나` : "";
    return `${message}${retry} Figma PNG 업로드/PNG URL 입력으로 우회할 수 있습니다.`;
  }
  if (path.startsWith("/api/pixel/figma") && (status === 401 || status === 403)) {
    return `${message} Render 환경변수 FIGMA_ACCESS_TOKEN과 Figma 파일 공유 권한을 확인해 주세요.`;
  }
  if (path.startsWith("/api/pixel/figma") && status === 404) {
    return `${message} Figma 링크의 file key와 node-id가 올바른지 확인해 주세요.`;
  }
  if (path === "/api/pixel/page-check" || path === "/api/pixel/proxy") {
    return `${message} 실제 URL이 외부에서 접근 가능한지, 내부망/localhost 차단 대상이 아닌지 확인해 주세요.`;
  }
  if (status >= 500) {
    return `${message} 서버 로그 또는 Render 배포 로그 확인이 필요합니다.`;
  }
  return message;
}

async function apiGet(path) {
  const res = await fetch(path, { method: "GET", cache: "no-store" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    const error = new Error(data.message || "요청 처리에 실패했습니다.");
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
}

function getGeminiCooldownSeconds() {
  return Math.max(0, Math.ceil((state.geminiRetryUntil - Date.now()) / 1000));
}

function isGeminiCoolingDown() {
  return getGeminiCooldownSeconds() > 0;
}

function renderGeminiCooldownMessage() {
  const remaining = getGeminiCooldownSeconds();
  if (remaining <= 0) {
    state.geminiRetryUntil = 0;
    state.geminiLimitReason = "";
    if (geminiCooldownTimer) {
      window.clearInterval(geminiCooldownTimer);
      geminiCooldownTimer = null;
    }
    el.phaseBadge.textContent = "대기 중";
    el.phaseBadge.className = "phase";
    showMessage("Gemini 사용 제한 대기 시간이 지났습니다. 다시 시도할 수 있습니다.", "success");
    syncButtons();
    return;
  }
  const reason = state.geminiLimitReason ? ` 원인: ${state.geminiLimitReason}` : "";
  setError(`Gemini 사용 제한으로 분석 기능을 ${remaining}초 동안 일시 중지했습니다.${reason}`);
}

function setGeminiCooldown(seconds, reason = "") {
  const safeSeconds = Math.max(1, Number(seconds) || 1);
  state.geminiRetryUntil = Date.now() + safeSeconds * 1000;
  state.geminiLimitReason = reason;
  renderGeminiCooldownMessage();
  if (geminiCooldownTimer) {
    window.clearInterval(geminiCooldownTimer);
  }
  geminiCooldownTimer = window.setInterval(renderGeminiCooldownMessage, 1000);
  syncButtons();
}

async function refreshGeminiStatus() {
  try {
    const data = await apiGet("/api/gemini-status");
    if (!data.available && data.retryAfterSeconds > 0) {
      setGeminiCooldown(data.retryAfterSeconds, data.reason || "");
    }
  } catch (error) {
    console.debug("Gemini status check failed.", error);
  }
}

async function waitForBackendReady() {
  let attempts = 0;
  setLoadingMessage(
    "서버를 준비하는 중입니다. 잠시만 기다려주세요.",
    "Render Cold Start로 인해 초기 접속 시간이 소요될 수 있습니다.",
  );
  while (true) {
    attempts += 1;
    try {
      const res = await fetch("/api/health", {
        method: "GET",
        cache: "no-store",
      });
      const data = await res.json().catch(() => ({}));
      const status = String(data.status || "").toLowerCase();
      const ready = data.ok === true && (!status || ["ready", "running", "ok"].includes(status));
      if (res.ok && ready) {
        return;
      }
    } catch (error) {
      console.debug("Backend is not ready yet.", error);
    }
    if (attempts >= SLOW_HEALTH_CHECK_ATTEMPTS) {
      setLoadingMessage(
        "서버 준비가 예상보다 오래 걸리고 있습니다.",
        "새로고침하지 않아도 준비 완료 후 자동으로 로그인 화면으로 이동합니다.",
      );
    }
    await delay(HEALTH_POLL_INTERVAL_MS);
  }
}

async function bootApp() {
  showView("loading");
  const params = new URLSearchParams(window.location.search);
  if (params.get("skipIntro") === "1") {
    await waitForBackendReady();
  } else {
    await Promise.all([delay(FLOOR_RISE_LOADING_DURATION_MS), waitForBackendReady()]);
  }
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
    refreshGeminiStatus();
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
  if (isGeminiCoolingDown()) {
    renderGeminiCooldownMessage();
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
    if (error.status === 429 && error.data && error.data.retryAfterSeconds) {
      setGeminiCooldown(error.data.retryAfterSeconds, error.data.reason || "");
      return;
    }
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

function escapeAttr(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function updateEmbedTypeFields() {
  const type = el.embedType.value;
  el.embedTcFields.classList.toggle("hidden", type !== "TC");
  el.embedEndFields.classList.toggle("hidden", type !== "END");
  el.embedDefectFields.classList.toggle("hidden", !["EM", "FEA"].includes(type));
  if (!el.embedFilename.value.trim()) {
    const version = el.embedVersion.value.trim() || "report";
    el.embedFilename.placeholder = `${type.toLowerCase()}_${version}.html`;
  }
}

function embedPayload() {
  return {
    templateType: el.embedType.value,
    title: el.embedTitle.value.trim(),
    version: el.embedVersion.value.trim(),
    filename: el.embedFilename.value.trim(),
    notionUrl: el.embedNotionUrl.value.trim(),
    defectDbUrl: el.embedDefectDbUrl.value.trim(),
    targetVersion: el.embedTargetVersion.value.trim(),
    rawText: el.embedRawText.value,
    tcAosPass: el.tcAosPass.value,
    tcAosFail: el.tcAosFail.value,
    tcAosNa: el.tcAosNa.value,
    tcIosPass: el.tcIosPass.value,
    tcIosFail: el.tcIosFail.value,
    tcIosNa: el.tcIosNa.value,
    endTotal: el.endTotal.value,
    endFixed: el.endFixed.value,
    endFuture: el.endFuture.value,
    endInvalid: el.endInvalid.value,
    endNote: el.endNote.value,
  };
}

async function generateEmbedHtml() {
  if (state.embedBusy) return;
  state.embedBusy = true;
  state.embedHtml = "";
  syncButtons();
  showEmbedMessage("HTML을 생성하는 중입니다.");
  try {
    const data = await apiPost("/api/embed-html", embedPayload());
    state.embedHtml = data.html || "";
    state.embedFilename = data.filename || el.embedFilename.value.trim() || "report.html";
    el.embedPreview.srcdoc = state.embedHtml;
    el.embedMeta.textContent = `${data.templateType || el.embedType.value} · ${state.embedFilename}`;
    showEmbedMessage("HTML 생성이 완료되었습니다.", "success");
  } catch (error) {
    console.error(error);
    el.embedPreview.removeAttribute("srcdoc");
    showEmbedMessage(error.message, "error");
  } finally {
    state.embedBusy = false;
    syncButtons();
  }
}

async function loadEmbedTargetVersions() {
  if (state.embedBusy) return;
  state.embedBusy = true;
  syncButtons();
  showEmbedMessage("목표버전 목록을 불러오는 중입니다.");
  try {
    const data = await apiPost("/api/embed-target-versions", {
      defectDbUrl: el.embedDefectDbUrl.value.trim(),
    });
    const versions = data.versions || [];
    el.embedTargetVersionList.innerHTML = versions.map((version) => `<option value="${escapeAttr(version)}"></option>`).join("");
    if (versions.length && !el.embedTargetVersion.value.trim()) {
      el.embedTargetVersion.value = versions[versions.length - 1];
    }
    showEmbedMessage(`목표버전 ${versions.length}개를 불러왔습니다.`, "success");
  } catch (error) {
    console.error(error);
    showEmbedMessage(error.message, "error");
  } finally {
    state.embedBusy = false;
    syncButtons();
  }
}

function downloadEmbedHtml() {
  if (!state.embedHtml) return;
  const blob = new Blob([state.embedHtml], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = state.embedFilename || "report.html";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function pixelViewport() {
  return {
    width: Number(el.pixelWidth.value) || 360,
    height: Number(el.pixelHeight.value) || 800,
  };
}

function updatePixelViewportFromPreset() {
  const [width, height] = el.pixelViewportPreset.value.split("x").map((value) => Number(value));
  el.pixelWidth.value = String(width || 360);
  el.pixelHeight.value = String(height || 800);
  applyPixelStage();
}

function applyPixelStage() {
  const viewport = pixelViewport();
  const opacity = Number(el.pixelOpacity.value) || 0;
  const x = Number(el.pixelOffsetX.value) || 0;
  const y = Number(el.pixelOffsetY.value) || 0;
  const scale = Number(el.pixelScale.value) || 100;
  const excludeEnabled = el.pixelExcludeChrome.checked;
  const excludeTop = excludeEnabled ? Math.max(0, Number(el.pixelExcludeTop.value) || 0) : 0;
  const excludeBottom = excludeEnabled ? Math.max(0, Number(el.pixelExcludeBottom.value) || 0) : 0;
  const compareHeight = Math.max(0, viewport.height - excludeTop - excludeBottom);
  const targetMode = el.pixelModeApp.checked ? "app" : "web";
  const actualOffsetTop = targetMode === "web" ? excludeTop : 0;
  [el.pixelFigmaStage, el.pixelActualStage, el.pixelStage].forEach((stage) => {
    stage.style.width = `${viewport.width}px`;
    stage.style.height = `${viewport.height}px`;
    stage.style.setProperty("--exclude-top", `${excludeTop}px`);
    stage.style.setProperty("--exclude-bottom", `${excludeBottom}px`);
    stage.style.setProperty("--actual-offset-top", `${actualOffsetTop}px`);
    stage.classList.toggle("exclude-disabled", !excludeEnabled);
  });
  [el.pixelFigmaImage, el.pixelActualFigmaImage].forEach((image) => {
    image.style.opacity = String(opacity / 100);
    image.style.transform = `translate(${x}px, ${y}px) scale(${scale / 100})`;
    image.style.clipPath = excludeEnabled ? `inset(${excludeTop}px 0 ${excludeBottom}px 0)` : "none";
  });
  [el.pixelActualScreenshot, el.pixelOverlayActualScreenshot].forEach((image) => {
    image.style.opacity = "1";
    image.style.top = `${actualOffsetTop}px`;
    image.style.bottom = "auto";
    image.style.height = `${viewport.height}px`;
    image.style.transform = "none";
    image.style.clipPath = "none";
  });
  el.pixelReadout.textContent = `Mode ${targetMode.toUpperCase()} · X ${x}px · Y ${y}px · Scale ${scale}% · Opacity ${opacity}% · Viewport ${viewport.width} × ${viewport.height} · Actual Y +${actualOffsetTop}px · Diff ${viewport.width} × ${compareHeight}`;
}

function pixelNodeId() {
  return el.pixelFrameSelect.value || (state.pixelParsed && state.pixelParsed.nodeId) || "";
}

function pixelLocalRenderCacheKey(renderCacheKey) {
  return `pixelaudit:figma-render:${renderCacheKey}`;
}

function getPixelLocalRenderCache(renderCacheKey) {
  try {
    const raw = localStorage.getItem(pixelLocalRenderCacheKey(renderCacheKey));
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || !data.imageDataUrl) return null;
    data.cached = true;
    data.localCached = true;
    return data;
  } catch (error) {
    return null;
  }
}

function setPixelLocalRenderCache(renderCacheKey, data) {
  try {
    localStorage.setItem(pixelLocalRenderCacheKey(renderCacheKey), JSON.stringify({
      fileKey: data.fileKey,
      nodeId: data.nodeId,
      frameName: data.frameName,
      imageDataUrl: data.imageDataUrl,
      byteLength: data.byteLength,
      storedAt: Date.now(),
    }));
  } catch (error) {
    // Large Figma PNG data URLs can exceed browser storage quota. Server cache still applies.
  }
}

function readPixelImageFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Figma PNG 파일을 읽지 못했습니다."));
    reader.readAsDataURL(file);
  });
}

function validatePixelImageUrl(imageUrl) {
  if (/^data:image\//i.test(imageUrl)) return;
  let parsed;
  try {
    parsed = new URL(imageUrl);
  } catch (error) {
    throw new Error("Figma PNG URL 형식이 올바르지 않습니다.");
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("Figma PNG URL은 http(s) 또는 data:image 형식이어야 합니다.");
  }
  if (parsed.hostname.endsWith("figma.com") && /\/(design|file)\//.test(parsed.pathname)) {
    throw new Error("Figma PNG URL에는 Figma 디자인 링크가 아니라 Export한 PNG 파일 URL 또는 PNG 업로드를 사용해 주세요.");
  }
}

function ensurePixelImageLoads(imageUrl) {
  return new Promise((resolve, reject) => {
    if (!imageUrl) {
      reject(new Error("Figma PNG URL이 비어 있습니다."));
      return;
    }
    const image = new Image();
    const timer = window.setTimeout(() => {
      image.onload = null;
      image.onerror = null;
      reject(new Error("Figma PNG 이미지를 불러오지 못했습니다. URL이 직접 이미지인지 확인하거나 PNG 업로드를 사용해 주세요."));
    }, 12000);
    image.onload = () => {
      window.clearTimeout(timer);
      resolve();
    };
    image.onerror = () => {
      window.clearTimeout(timer);
      reject(new Error("Figma PNG URL이 이미지로 로드되지 않습니다. Figma 디자인 링크가 아닌 PNG 파일 URL을 넣어 주세요."));
    };
    image.src = imageUrl;
  });
}

async function getPixelManualRenderData(renderCacheKey, nodeId) {
  const file = el.pixelFigmaImageFile.files && el.pixelFigmaImageFile.files[0];
  if (file) {
    if (!file.type.startsWith("image/")) {
      throw new Error("Figma PNG 업로드에는 이미지 파일만 사용할 수 있습니다.");
    }
    const imageDataUrl = await readPixelImageFile(file);
    const data = {
      fileKey: "manual-upload",
      nodeId,
      frameName: file.name,
      imageDataUrl,
      byteLength: file.size,
      cached: true,
      localCached: true,
      warning: "업로드한 Figma PNG를 사용했습니다.",
    };
    setPixelLocalRenderCache(renderCacheKey, data);
    return data;
  }
  const imageUrl = el.pixelFigmaImageUrl.value.trim();
  if (!imageUrl) return null;
  validatePixelImageUrl(imageUrl);
  await ensurePixelImageLoads(imageUrl);
  const data = {
    fileKey: "manual-url",
    nodeId,
    frameName: "Manual Figma PNG",
    imageDataUrl: imageUrl,
    byteLength: imageUrl.length,
    cached: true,
    localCached: true,
    warning: "직접 입력한 Figma PNG를 사용했습니다.",
  };
  if (imageUrl.startsWith("data:image/")) {
    setPixelLocalRenderCache(renderCacheKey, data);
  }
  return data;
}

function pixelSpecialStartUrl(pageUrl) {
  try {
    const url = new URL(pageUrl);
    if (url.hostname === "go.hanpass.com" && url.pathname.startsWith("/auth/visiting_signup")) {
      return `${url.origin}/home`;
    }
  } catch (error) {
    return pageUrl;
  }
  return pageUrl;
}

function pixelStartUrl(pageUrl) {
  return el.pixelStartUrl.value.trim() || pixelSpecialStartUrl(pageUrl);
}

async function captureExternalActualScreen() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    throw new Error("현재 브라우저는 화면 캡처를 지원하지 않습니다. Chrome 최신 버전에서 사용해 주세요.");
  }
  const viewport = pixelViewport();
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        displaySurface: "browser",
        width: { ideal: viewport.width },
        height: { ideal: viewport.height },
        frameRate: { ideal: 1, max: 5 },
      },
      audio: false,
    });
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.srcObject = stream;
    await video.play();
    await new Promise((resolve) => {
      if (video.videoWidth && video.videoHeight) {
        resolve();
        return;
      }
      video.onloadedmetadata = resolve;
    });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");
    const sourceWidth = video.videoWidth || viewport.width;
    const sourceHeight = video.videoHeight || viewport.height;
    const scale = Math.max(viewport.width / sourceWidth, viewport.height / sourceHeight);
    const drawWidth = sourceWidth * scale;
    const drawHeight = sourceHeight * scale;
    const dx = (viewport.width - drawWidth) / 2;
    const dy = (viewport.height - drawHeight) / 2;
    ctx.drawImage(video, dx, dy, drawWidth, drawHeight);
    return canvas.toDataURL("image/png");
  } catch (error) {
    if (error && error.name === "NotAllowedError") {
      throw new Error("화면 캡처 권한이 취소되었습니다. 현재 화면 검증을 누른 뒤 실제 화면 탭/창을 선택해 주세요.");
    }
    throw error;
  } finally {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
  }
}

async function pixelLoadFrames() {
  if (state.pixelBusy) return;
  const figmaUrl = el.pixelFigmaUrl.value.trim();
  if (!figmaUrl) {
    showPixelMessage("Figma 링크를 입력해 주세요.", "error");
    return;
  }
  state.pixelBusy = true;
  syncButtons();
  showPixelMessage("Figma 링크를 분석하는 중입니다.");
  try {
    const parsed = await apiPost("/api/pixel/figma-parse", { figmaUrl });
    state.pixelParsed = parsed;
    el.pixelFrameSelect.innerHTML = "";
    if (parsed.nodeId) {
      el.pixelFrameSelect.innerHTML = `<option value="${escapeAttr(parsed.nodeId)}">${escapeAttr(parsed.frameName || parsed.nodeId)} · ${escapeAttr(parsed.nodeId)}</option>`;
      showPixelMessage(`node-id ${parsed.nodeId}를 확인했습니다.`, "success");
      return;
    }
    const data = await apiPost("/api/pixel/figma-frames", { fileKey: parsed.fileKey });
    const frames = data.frames || [];
    el.pixelFrameSelect.innerHTML = frames.length
      ? frames.map((frame) => `<option value="${escapeAttr(frame.id)}">${escapeAttr(frame.name)} (${frame.width} × ${frame.height})</option>`).join("")
      : '<option value="">Frame 없음</option>';
    showPixelMessage(`Frame ${frames.length}개를 불러왔습니다.`, frames.length ? "success" : "error");
  } catch (error) {
    console.error(error);
    showPixelMessage(error.message, "error");
  } finally {
    state.pixelBusy = false;
    syncButtons();
  }
}

async function loadPixelDesignData(figmaUrl) {
  if (!state.pixelParsed) {
    state.pixelParsed = await apiPost("/api/pixel/figma-parse", { figmaUrl });
  }
  const nodeId = pixelNodeId();
  const renderCacheKey = `${figmaUrl}::${nodeId}`;
  let data = await getPixelManualRenderData(renderCacheKey, nodeId);
  if (!data) {
    data = state.pixelRenderCacheKey === renderCacheKey && state.pixelRenderData
      ? state.pixelRenderData
      : getPixelLocalRenderCache(renderCacheKey);
  }
  if (!data) {
    try {
      data = await apiPost("/api/pixel/figma-render", {
        figmaUrl,
        nodeId,
      });
      setPixelLocalRenderCache(renderCacheKey, data);
    } catch (error) {
      const localCache = getPixelLocalRenderCache(renderCacheKey);
      if (error.status === 429 && localCache) {
        data = {
          ...localCache,
          warning: "Figma API 호출 제한으로 브라우저 캐시 이미지를 사용했습니다.",
        };
      } else {
        if (error.status === 429) {
          error.message = "Figma API 호출 제한입니다. 캐시가 없는 최초 요청이면 Figma PNG 업로드 또는 Figma PNG URL 입력으로 우회할 수 있습니다.";
        }
        throw error;
      }
    }
  }
  state.pixelRenderCacheKey = renderCacheKey;
  state.pixelRenderData = data;
  state.pixelImageDataUrl = data.imageDataUrl;
  el.pixelFigmaImage.src = state.pixelImageDataUrl;
  el.pixelActualFigmaImage.src = state.pixelImageDataUrl;
  el.pixelFigmaOnlyImage.src = state.pixelImageDataUrl;
  return data;
}

async function pixelLaunchActual() {
  if (state.pixelBusy) return;
  const pageUrl = el.pixelPageUrl.value.trim();
  if (!pageUrl) {
    showPixelMessage("실제 웹 URL을 입력해 주세요.", "error");
    return;
  }
  const startUrl = pixelStartUrl(pageUrl);
  window.open(startUrl, "pixelaudit_actual_target", "width=430,height=940,noopener,noreferrer");
  state.pixelActualLoaded = true;
  state.pixelActualStartUrl = startUrl;
  el.pixelActualScreenshot.classList.add("hidden");
  el.pixelOverlayActualScreenshot.classList.add("hidden");
  el.pixelActualFigmaImage.classList.add("hidden");
  el.pixelFigmaImage.classList.add("hidden");
  el.pixelEmptyState.classList.add("hidden");
  el.pixelCompareGrid.classList.remove("hidden");
  applyPixelStage();
  el.pixelMeta.textContent = `외부 실제 화면 이동 중 · ${pixelViewport().width} × ${pixelViewport().height}`;
  showPixelMessage(`외부 창을 열었습니다. 그 창에서 목표 화면까지 직접 이동한 뒤 현재 화면 검증을 누르고 해당 창/탭을 선택하세요. · 진입 ${startUrl}`, "success");
}

async function pixelRender() {
  if (state.pixelBusy) return;
  const figmaUrl = el.pixelFigmaUrl.value.trim();
  const pageUrl = el.pixelPageUrl.value.trim();
  if (!figmaUrl) {
    showPixelMessage("Figma 링크를 입력해 주세요.", "error");
    return;
  }
  if (!pageUrl) {
    showPixelMessage("실제 웹 URL을 입력해 주세요.", "error");
    return;
  }
  state.pixelBusy = true;
  syncButtons();
  showPixelMessage("화면 선택창에서 목표 화면이 열린 실제 탭/창을 선택해 주세요.");
  try {
    const actualDataUrl = await captureExternalActualScreen();
    const data = await loadPixelDesignData(figmaUrl);
    el.pixelActualScreenshot.src = actualDataUrl;
    el.pixelOverlayActualScreenshot.src = actualDataUrl;
    el.pixelActualScreenshot.classList.remove("hidden");
    el.pixelOverlayActualScreenshot.classList.remove("hidden");
    el.pixelActualFigmaImage.classList.remove("hidden");
    el.pixelFigmaImage.classList.remove("hidden");
    el.pixelEmptyState.classList.add("hidden");
    el.pixelCompareGrid.classList.remove("hidden");
    applyPixelStage();
    state.pixelActualLoaded = true;
    el.pixelMeta.textContent = `${data.frameName || data.nodeId} · 외부 실제 화면 캡처 검증 · ${pixelViewport().width} × ${pixelViewport().height}`;
    const cacheText = data.cached ? " · Figma 캐시 사용" : "";
    const warningText = data.warning ? ` · ${data.warning}` : "";
    showPixelMessage(`외부 실제 화면을 캡처해 검증을 준비했습니다.${cacheText}${warningText}`, "success");
  } catch (error) {
    console.error(error);
    showPixelMessage(error.message, "error");
  } finally {
    state.pixelBusy = false;
    syncButtons();
  }
}

function pixelOpenUrl() {
  const pageUrl = el.pixelPageUrl.value.trim();
  if (!pageUrl) {
    showPixelMessage("실제 웹 URL을 입력해 주세요.", "error");
    return;
  }
  window.open(pageUrl, "_blank", "noopener,noreferrer");
}

function pixelOpenDevice() {
  const pageUrl = el.pixelPageUrl.value.trim();
  if (!pageUrl) {
    showPixelMessage("실제 웹 URL을 입력해 주세요.", "error");
    return;
  }
  const launcherUrl = `/pixel-device.html?url=${encodeURIComponent(pageUrl)}&width=360&height=800`;
  window.open(launcherUrl, "pixelaudit_web_avd_360", "width=430,height=940,noopener,noreferrer");
}

el.analyzeBtn.addEventListener("click", analyze);
el.registerBtn.addEventListener("click", registerSummary);
el.generateTcBtn.addEventListener("click", generateTc);
el.uploadTcBtn.addEventListener("click", uploadTc);
el.copySummaryBtn.addEventListener("click", () => copyText(state.summary, "요약 결과"));
el.copyTcBtn.addEventListener("click", () => copyText(state.tcMarkdown, "TC 결과"));
el.ticketTab.addEventListener("click", () => switchTab("ticket"));
el.embedTab.addEventListener("click", () => switchTab("embed"));
el.pixelTab.addEventListener("click", () => switchTab("pixel"));
el.localizationTab.addEventListener("click", () => switchTab("localization"));
el.embedType.addEventListener("change", updateEmbedTypeFields);
el.embedVersion.addEventListener("input", updateEmbedTypeFields);
el.generateEmbedBtn.addEventListener("click", generateEmbedHtml);
el.loadTargetVersionsBtn.addEventListener("click", loadEmbedTargetVersions);
el.copyEmbedHtmlBtn.addEventListener("click", () => copyText(state.embedHtml, "HTML"));
el.downloadEmbedHtmlBtn.addEventListener("click", downloadEmbedHtml);
el.pixelFigmaImageUrl.addEventListener("input", () => {
  state.pixelRenderCacheKey = "";
  state.pixelRenderData = null;
});
el.pixelFigmaImageFile.addEventListener("change", () => {
  state.pixelRenderCacheKey = "";
  state.pixelRenderData = null;
});
el.pixelPageUrl.addEventListener("input", () => {
  state.pixelActualLoaded = false;
  state.pixelActualStartUrl = "";
});
el.pixelStartUrl.addEventListener("input", () => {
  state.pixelActualLoaded = false;
  state.pixelActualStartUrl = "";
});
el.pixelViewportPreset.addEventListener("change", updatePixelViewportFromPreset);
el.pixelWidth.addEventListener("input", applyPixelStage);
el.pixelHeight.addEventListener("input", applyPixelStage);
el.pixelOpacity.addEventListener("input", applyPixelStage);
el.pixelOffsetX.addEventListener("input", applyPixelStage);
el.pixelOffsetY.addEventListener("input", applyPixelStage);
el.pixelScale.addEventListener("input", applyPixelStage);
el.pixelLoadFramesBtn.addEventListener("click", pixelLoadFrames);
el.pixelLaunchActualBtn.addEventListener("click", pixelLaunchActual);
el.pixelRenderBtn.addEventListener("click", pixelRender);
el.pixelDeviceBtn.addEventListener("click", pixelOpenDevice);
el.pixelOpenUrlBtn.addEventListener("click", pixelOpenUrl);
el.localizationReloadBtn.addEventListener("click", reloadLocalizationApp);
el.pixelModeWeb.addEventListener("change", applyPixelStage);
el.pixelModeApp.addEventListener("change", applyPixelStage);
el.pixelExcludeChrome.addEventListener("change", applyPixelStage);
el.pixelExcludeTop.addEventListener("input", applyPixelStage);
el.pixelExcludeBottom.addEventListener("input", applyPixelStage);
[el.pixelFigmaImage, el.pixelFigmaOnlyImage, el.pixelActualFigmaImage].forEach((image) => {
  image.addEventListener("error", () => {
    showPixelMessage("Figma PNG 이미지를 표시하지 못했습니다. PNG URL이 직접 이미지인지 확인하거나 PNG 업로드를 사용해 주세요.", "error");
  });
});
el.loginForm.addEventListener("submit", login);
el.notionUrl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") analyze();
});

updateEmbedTypeFields();
applyPixelStage();
syncButtons();
bootApp();
