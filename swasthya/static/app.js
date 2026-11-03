const loginScreen = document.querySelector("#login-screen");
const appShell = document.querySelector("#app-shell");
const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const caseList = document.querySelector("#case-list");
const emptyState = document.querySelector("#empty-state");
const searchInput = document.querySelector("#search-input");
const riskFilter = document.querySelector("#risk-filter");
const toast = document.querySelector("#toast");
const replyPanel = document.querySelector("#reply-panel");
let demoCases = [];
let toastTimer;

document.querySelector("#today-label").textContent = new Intl.DateTimeFormat("en-IN", {
  weekday: "long", day: "2-digit", month: "long", year: "numeric",
}).format(new Date()).toLocaleUpperCase();

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.hidden = true; }, 3200);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.detail || "Something went wrong. Please try again.");
    error.status = response.status;
    throw error;
  }
  return body;
}

function riskLabel(risk) {
  return risk === "critical" ? "Urgent review" : risk === "follow-up" ? "Follow-up" : "Routine";
}

function renderCases() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  const selectedRisk = riskFilter.value;
  const filtered = demoCases.filter((item) => {
    const matchesSearch = `${item.label} ${item.language} ${item.signal} ${item.summary}`.toLocaleLowerCase().includes(query);
    return matchesSearch && (selectedRisk === "all" || item.risk === selectedRisk);
  });

  caseList.replaceChildren();
  emptyState.hidden = filtered.length !== 0;
  for (const item of filtered) {
    const row = document.createElement("article");
    row.className = "case-row";
    const identity = document.createElement("div");
    identity.className = "case-identity";
    const avatar = document.createElement("span");
    avatar.className = `case-avatar avatar-${item.risk}`;
    avatar.textContent = item.label.slice(-2);
    const title = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = item.label;
    const stage = document.createElement("small");
    stage.textContent = `${item.id} · ${item.day}`;
    title.append(name, stage);
    identity.append(avatar, title);

    const language = document.createElement("span");
    language.className = "case-language";
    language.textContent = item.language;
    const risk = document.createElement("span");
    risk.className = `risk-badge risk-${item.risk}`;
    const riskDot = document.createElement("i");
    riskDot.setAttribute("aria-hidden", "true");
    risk.append(riskDot, document.createTextNode(riskLabel(item.risk)));
    const action = document.createElement("button");
    action.className = "case-action";
    action.type = "button";
    action.textContent = "Review →";
    action.setAttribute("aria-label", `Review ${item.label}`);
    action.addEventListener("click", () => selectCase(item));
    row.append(identity, language, risk, action);

    const details = document.createElement("div");
    details.className = "case-details";
    const signal = document.createElement("span");
    signal.textContent = item.signal;
    const summary = document.createElement("span");
    summary.textContent = item.summary;
    details.append(signal, summary);
    row.append(details);
    caseList.append(row);
  }
}

function selectCase(item) {
  document.querySelectorAll(".case-row").forEach((row) => row.classList.remove("selected"));
  const row = [...document.querySelectorAll(".case-row")].find((candidate) => candidate.textContent.includes(item.id));
  row?.classList.add("selected");
  const isCritical = item.risk === "critical";
  document.querySelector("#reply-text").textContent = isCritical
    ? "This demo has not sent an alert. A real red-flag report must go to an on-duty human immediately."
    : "Select ‘Preview acknowledgement’ to generate a short, non-clinical language preview with Sarvam. Only synthetic demo text is used.";
  document.querySelector("#reply-source").textContent = isCritical ? "Fixed safety message · no AI call" : `${item.language} · Sarvam 105B Conversations`;
  replyPanel.hidden = false;
  replyPanel.dataset.caseId = item.id;
  replyPanel.dataset.critical = String(isCritical);
  const generateButton = document.querySelector("#generate-reply");
  generateButton.disabled = isCritical;
  generateButton.textContent = isCritical ? "Human review required" : "Preview acknowledgement";
  replyPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function loadDemo() {
  const data = await request("/api/demo/cases");
  demoCases = data.cases;
  document.querySelector("#metric-total").textContent = String(demoCases.length).padStart(2, "0");
  document.querySelector("#metric-review").textContent = String(data.counts.follow_up).padStart(2, "0");
  document.querySelector("#metric-urgent").textContent = String(data.counts.critical).padStart(2, "0");
  document.querySelector("#queue-count").textContent = `${demoCases.length.toString().padStart(2, "0")} cases`;
  document.querySelector("#nav-count").textContent = demoCases.length.toString().padStart(2, "0");
  renderCases();
}

function openWorkspace() {
  loginScreen.hidden = true;
  appShell.hidden = false;
  loginError.hidden = true;
  loadDemo().catch((error) => {
    if (error.status === 401) {
      appShell.hidden = true;
      loginScreen.hidden = false;
      showToast("Your session expired. Sign in again.");
    } else {
      showToast(error.message);
    }
  });
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = loginForm.querySelector("button[type=submit]");
  submit.disabled = true;
  loginError.hidden = true;
  try {
    await request("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: document.querySelector("#username").value,
        password: document.querySelector("#password").value,
      }),
    });
    document.querySelector("#password").value = "";
    openWorkspace();
  } catch (error) {
    loginError.textContent = error.message;
    loginError.hidden = false;
  } finally {
    submit.disabled = false;
  }
});

document.querySelector("#logout-button").addEventListener("click", async () => {
  try { await request("/api/logout", { method: "POST", body: "{}" }); } catch { /* Clear the local view regardless. */ }
  appShell.hidden = true;
  loginScreen.hidden = false;
  loginForm.reset();
  showToast("You have signed out.");
});

document.querySelector("#refresh-button").addEventListener("click", () => {
  loadDemo().then(() => showToast("Demo queue refreshed.")).catch((error) => showToast(error.message));
});
searchInput.addEventListener("input", renderCases);
riskFilter.addEventListener("change", renderCases);
document.querySelector("#close-reply").addEventListener("click", () => { replyPanel.hidden = true; });

document.querySelector("#generate-reply").addEventListener("click", async () => {
  const caseId = replyPanel.dataset.caseId;
  if (!caseId || replyPanel.dataset.critical === "true") return;
  const button = document.querySelector("#generate-reply");
  button.disabled = true;
  button.textContent = "Generating preview…";
  try {
    const result = await request("/api/demo/reply", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId }),
    });
    document.querySelector("#reply-text").textContent = result.reply;
    document.querySelector("#reply-source").textContent = `${result.source} · preview only`;
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Preview acknowledgement";
  }
});

document.querySelector("#run-voice-demo").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const resultPanel = document.querySelector("#voice-result");
  button.disabled = true;
  button.textContent = "Running 4 Sarvam steps…";
  resultPanel.hidden = true;
  document.querySelectorAll(".pipeline-step").forEach((step) => step.classList.remove("completed"));
  try {
    const result = await request("/api/demo/voice-loop", { method: "POST" });
    document.querySelector("#voice-transcript").textContent = `Transcript: ${result.transcript}`;
    document.querySelector("#voice-reply").textContent = result.reply;
    document.querySelector("#patient-audio").src = `data:audio/wav;base64,${result.patient_audio_base64}`;
    document.querySelector("#reply-audio").src = `data:audio/wav;base64,${result.reply_audio_base64}`;
    document.querySelectorAll(".pipeline-step").forEach((step) => step.classList.add("completed"));
    resultPanel.hidden = false;
    resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Run voice demo →";
  }
});
