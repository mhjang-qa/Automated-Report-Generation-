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
  pixelParsed: null,
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
  ticketView: document.querySelector("#ticketView"),
  embedView: document.querySelector("#embedView"),
  pixelView: document.querySelector("#pixelView"),
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
  pixelPageUrl: document.querySelector("#pixelPageUrl"),
  pixelViewportPreset: document.querySelector("#pixelViewportPreset"),
  pixelFrameSelect: document.querySelector("#pixelFrameSelect"),
  pixelWidth: document.querySelector("#pixelWidth"),
  pixelHeight: document.querySelector("#pixelHeight"),
  pixelMessage: document.querySelector("#pixelMessage"),
  pixelLoadFramesBtn: document.querySelector("#pixelLoadFramesBtn"),
  pixelRenderBtn: document.querySelector("#pixelRenderBtn"),
  pixelDeviceBtn: document.querySelector("#pixelDeviceBtn"),
  pixelOpenUrlBtn: document.querySelector("#pixelOpenUrlBtn"),
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
  pixelActualFrame: document.querySelector("#pixelActualFrame"),
  pixelPageFrame: document.querySelector("#pixelPageFrame"),
  pixelFigmaImage: document.querySelector("#pixelFigmaImage"),
  pixelEmptyState: document.querySelector("#pixelEmptyState"),
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

function switchTab(tabName) {
  const isTicket = tabName === "ticket";
  const isEmbed = tabName === "embed";
  const isPixel = tabName === "pixel";
  el.ticketTab.classList.toggle("active", isTicket);
  el.embedTab.classList.toggle("active", isEmbed);
  el.pixelTab.classList.toggle("active", isPixel);
  el.ticketView.classList.toggle("hidden", !isTicket);
  el.embedView.classList.toggle("hidden", !isEmbed);
  el.pixelView.classList.toggle("hidden", !isPixel);
  if (isEmbed) {
    el.phaseBadge.textContent = "HTML 생성";
    el.phaseBadge.className = "phase";
    el.embedNotionUrl.focus();
  } else if (isPixel) {
    el.phaseBadge.textContent = "PixelAudit";
    el.phaseBadge.className = "phase";
    el.pixelFigmaUrl.focus();
  } else {
    el.phaseBadge.textContent = "대기 중";
    el.phaseBadge.className = "phase";
    el.notionUrl.focus();
  }
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
  el.pixelRenderBtn.disabled = state.pixelBusy;
  el.pixelDeviceBtn.disabled = state.pixelBusy;
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
    const error = new Error(data.message || "요청 처리에 실패했습니다.");
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
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
  [el.pixelFigmaStage, el.pixelActualStage, el.pixelStage].forEach((stage) => {
    stage.style.width = `${viewport.width}px`;
    stage.style.height = `${viewport.height}px`;
    stage.style.setProperty("--exclude-top", `${excludeTop}px`);
    stage.style.setProperty("--exclude-bottom", `${excludeBottom}px`);
    stage.classList.toggle("exclude-disabled", !excludeEnabled);
  });
  el.pixelFigmaImage.style.opacity = String(opacity / 100);
  el.pixelFigmaImage.style.transform = `translate(${x}px, ${y}px) scale(${scale / 100})`;
  el.pixelFigmaImage.style.clipPath = excludeEnabled ? `inset(${excludeTop}px 0 ${excludeBottom}px 0)` : "none";
  el.pixelReadout.textContent = `X ${x}px · Y ${y}px · Scale ${scale}% · Opacity ${opacity}% · Viewport ${viewport.width} × ${viewport.height} · Diff ${viewport.width} × ${compareHeight}`;
}

function pixelNodeId() {
  return el.pixelFrameSelect.value || (state.pixelParsed && state.pixelParsed.nodeId) || "";
}

async function loadPixelFrame(frame, pageCheck, pageUrl) {
  frame.removeAttribute("src");
  frame.removeAttribute("srcdoc");
  if (pageCheck.embeddable) {
    frame.src = pageUrl;
    return;
  }
  const response = await fetch(pageCheck.proxyUrl, { method: "GET", cache: "no-store" });
  const html = await response.text();
  if (!response.ok) {
    throw new Error(html || "PixelAudit 프록시 화면을 불러오지 못했습니다.");
  }
  frame.srcdoc = html;
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
  showPixelMessage("Figma Frame 이미지를 생성하는 중입니다.");
  try {
    if (!state.pixelParsed) {
      state.pixelParsed = await apiPost("/api/pixel/figma-parse", { figmaUrl });
    }
    const data = await apiPost("/api/pixel/figma-render", {
      figmaUrl,
      nodeId: pixelNodeId(),
    });
    state.pixelImageDataUrl = data.imageDataUrl;
    el.pixelFigmaImage.src = state.pixelImageDataUrl;
    el.pixelFigmaOnlyImage.src = state.pixelImageDataUrl;
    const pageCheck = await apiPost("/api/pixel/page-check", { url: pageUrl });
    await Promise.all([
      loadPixelFrame(el.pixelPageFrame, pageCheck, pageUrl),
      loadPixelFrame(el.pixelActualFrame, pageCheck, pageUrl),
    ]);
    el.pixelEmptyState.classList.add("hidden");
    el.pixelCompareGrid.classList.remove("hidden");
    applyPixelStage();
    el.pixelMeta.textContent = `${data.frameName || data.nodeId} · ${pixelViewport().width} × ${pixelViewport().height}`;
    if (pageCheck.embeddable) {
      showPixelMessage("비교 화면을 준비했습니다.", "success");
    } else {
      showPixelMessage(`iframe 차단 헤더(${pageCheck.xFrameOptions || "CSP"})가 감지되어 PixelAudit 프록시로 표시합니다.`, "success");
    }
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
el.embedType.addEventListener("change", updateEmbedTypeFields);
el.embedVersion.addEventListener("input", updateEmbedTypeFields);
el.generateEmbedBtn.addEventListener("click", generateEmbedHtml);
el.loadTargetVersionsBtn.addEventListener("click", loadEmbedTargetVersions);
el.copyEmbedHtmlBtn.addEventListener("click", () => copyText(state.embedHtml, "HTML"));
el.downloadEmbedHtmlBtn.addEventListener("click", downloadEmbedHtml);
el.pixelViewportPreset.addEventListener("change", updatePixelViewportFromPreset);
el.pixelWidth.addEventListener("input", applyPixelStage);
el.pixelHeight.addEventListener("input", applyPixelStage);
el.pixelOpacity.addEventListener("input", applyPixelStage);
el.pixelOffsetX.addEventListener("input", applyPixelStage);
el.pixelOffsetY.addEventListener("input", applyPixelStage);
el.pixelScale.addEventListener("input", applyPixelStage);
el.pixelLoadFramesBtn.addEventListener("click", pixelLoadFrames);
el.pixelRenderBtn.addEventListener("click", pixelRender);
el.pixelDeviceBtn.addEventListener("click", pixelOpenDevice);
el.pixelOpenUrlBtn.addEventListener("click", pixelOpenUrl);
el.pixelExcludeChrome.addEventListener("change", applyPixelStage);
el.pixelExcludeTop.addEventListener("input", applyPixelStage);
el.pixelExcludeBottom.addEventListener("input", applyPixelStage);
el.loginForm.addEventListener("submit", login);
el.notionUrl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") analyze();
});

updateEmbedTypeFields();
applyPixelStage();
syncButtons();
bootApp();
