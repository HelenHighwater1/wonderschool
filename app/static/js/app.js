// Launchpad Program Coach — welcome, intake, loading, roadmap, and chat.

(function () {
  // -------------------------------------------------------------------------
  // Screen routing (only elements with class .screen)
  // -------------------------------------------------------------------------
  const screens = Array.from(document.querySelectorAll(".screen"));

  function show(screenId) {
    for (const el of screens) {
      el.classList.toggle("screen--active", el.id === screenId);
    }
    const inner = document.querySelector(`#${screenId} .screen__inner`);
    if (inner) {
      inner.style.animation = "none";
      void inner.offsetWidth;
      inner.style.animation = "";
    }
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // -------------------------------------------------------------------------
  // Intake state
  // -------------------------------------------------------------------------
  const answers = {
    state: "",
    home_type: "",
    ages: "",
    stage: "",
    concern: "",
  };

  const HOME_LABELS = {
    apartment: "an apartment",
    condo: "a condo",
    single_family: "a single family home",
    other: "another type of home",
  };
  const AGES_LABELS = {
    infants: "infants",
    toddlers: "toddlers",
    preschool: "preschoolers",
    mixed: "mixed ages",
  };
  const STAGE_LABELS = {
    exploring: "just exploring",
    ready: "ready to start",
    started: "already started",
  };
  const CONCERN_LABELS = {
    licensing: "licensing",
    money: "money and finances",
    finding_families: "finding families",
    space: "setting up your space",
    all: "everything at once",
  };

  const stateSelect = document.getElementById("answer-state");
  const buildBtn = document.getElementById("cta-build");
  const surpriseBtn = document.getElementById("surprise-me");

  function syncBuildButton() {
    const ready = Boolean(answers.state);
    buildBtn.disabled = !ready;
    buildBtn.setAttribute("aria-disabled", String(!ready));
    buildBtn.classList.toggle("cta--disabled", !ready);
  }

  function selectPill(questionKey, value, { animate = true } = {}) {
    const group = document.querySelectorAll(`.pill[data-question="${questionKey}"]`);
    let target = null;
    for (const pill of group) {
      const isTarget = pill.dataset.value === value;
      pill.setAttribute("aria-checked", String(isTarget));
      if (isTarget) target = pill;
    }
    answers[questionKey] = value;
    if (animate && target) flashPill(target);
  }

  function clearPill(questionKey) {
    const group = document.querySelectorAll(`.pill[data-question="${questionKey}"]`);
    for (const pill of group) pill.setAttribute("aria-checked", "false");
    answers[questionKey] = "";
  }

  function flashPill(pill) {
    pill.classList.remove("pill--just-selected");
    void pill.offsetWidth;
    pill.classList.add("pill--just-selected");
    pill.addEventListener(
      "animationend",
      () => pill.classList.remove("pill--just-selected"),
      { once: true }
    );
  }

  document.querySelectorAll(".pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      const q = pill.dataset.question;
      const v = pill.dataset.value;
      const alreadySelected = pill.getAttribute("aria-checked") === "true";
      if (alreadySelected) clearPill(q);
      else selectPill(q, v);
    });
  });

  function setState(value, { animate = true } = {}) {
    stateSelect.value = value;
    answers.state = value;
    stateSelect.classList.toggle("is-set", Boolean(value));
    syncBuildButton();
    if (animate && value) flashSelect();
  }

  function flashSelect() {
    const wrapper = stateSelect.closest(".select");
    if (!wrapper) return;
    wrapper.classList.remove("select--just-set");
    void wrapper.offsetWidth;
    wrapper.classList.add("select--just-set");
    setTimeout(() => wrapper.classList.remove("select--just-set"), 600);
  }

  stateSelect.addEventListener("change", () => {
    setState(stateSelect.value, { animate: false });
  });

  function pickRandom(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function surpriseMe() {
    const stateOptions = Array.from(stateSelect.options)
      .map((o) => o.value)
      .filter(Boolean);
    const weighted = [
      ...stateOptions,
      "California",
      "California",
      "California",
      "Texas",
      "Texas",
      "Texas",
      "Florida",
      "Florida",
      "New York",
      "New York",
      "Washington",
      "Maryland",
      "North Carolina",
    ];
    const plan = [
      { delay: 0, apply: () => setState(pickRandom(weighted)) },
      { delay: 220, apply: () => selectPill("home_type", pickRandom(["apartment", "condo", "single_family", "other"])) },
      { delay: 440, apply: () => selectPill("ages", pickRandom(["infants", "toddlers", "preschool", "mixed"])) },
      { delay: 660, apply: () => selectPill("stage", pickRandom(["exploring", "ready", "started"])) },
      { delay: 880, apply: () => selectPill("concern", pickRandom(["licensing", "money", "finding_families", "space", "all"])) },
    ];
    surpriseBtn.disabled = true;
    for (const step of plan) setTimeout(step.apply, step.delay);
    setTimeout(() => {
      surpriseBtn.disabled = false;
    }, plan[plan.length - 1].delay + 500);
  }

  surpriseBtn.addEventListener("click", surpriseMe);

  const ctaStart = document.getElementById("cta-start");
  if (ctaStart) ctaStart.addEventListener("click", () => show("screen-intake"));

  // -------------------------------------------------------------------------
  // Toast
  // -------------------------------------------------------------------------
  const toastEl = document.getElementById("toast");

  function showToast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.hidden = false;
    toastEl.classList.add("toast--visible");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => {
      toastEl.classList.remove("toast--visible");
      setTimeout(() => {
        toastEl.hidden = true;
      }, 320);
    }, 4200);
  }

  // -------------------------------------------------------------------------
  // API
  // -------------------------------------------------------------------------
  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = {};
    try {
      data = await res.json();
    } catch {
      /* ignore */
    }
    if (!res.ok) {
      let msg = "Something went wrong.";
      if (typeof data.detail === "string") msg = data.detail;
      else if (Array.isArray(data.detail))
        msg = data.detail.map((d) => d.msg || JSON.stringify(d)).join(" ");
      throw new Error(msg);
    }
    return data;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // -------------------------------------------------------------------------
  // Roadmap + loading
  // -------------------------------------------------------------------------
  let loadingInterval = null;

  const loadingStatus = document.getElementById("loading-status");
  const loadingProgress = document.getElementById("loading-progress");

  function startLoadingAnimation(state) {
    if (loadingInterval) clearInterval(loadingInterval);
    const messages = [
      `Looking up ${state}-specific information…`,
      "Picking the steps that match your situation…",
      "Putting it all together…",
    ];
    let i = 0;
    if (loadingStatus) loadingStatus.textContent = messages[0];
    loadingInterval = setInterval(() => {
      i = (i + 1) % messages.length;
      if (loadingStatus) loadingStatus.textContent = messages[i];
    }, 2400);

    if (loadingProgress) {
      loadingProgress.classList.remove("loading__bar-fill--running", "loading__bar-fill--done");
      loadingProgress.style.width = "0%";
      void loadingProgress.offsetWidth;
      requestAnimationFrame(() => {
        loadingProgress.classList.add("loading__bar-fill--running");
      });
    }
  }

  function finishLoadingAnimation() {
    if (loadingInterval) {
      clearInterval(loadingInterval);
      loadingInterval = null;
    }
    if (loadingProgress) {
      loadingProgress.classList.remove("loading__bar-fill--running");
      loadingProgress.classList.add("loading__bar-fill--done");
    }
  }

  function buildRecapLine() {
    const state = answers.state || "your state";
    const home = answers.home_type
      ? HOME_LABELS[answers.home_type] || "your home"
      : "someone planning a home daycare";
    const stage = answers.stage
      ? STAGE_LABELS[answers.stage] || answers.stage
      : "still figuring out where you are in the process";
    const concern = answers.concern
      ? CONCERN_LABELS[answers.concern] || answers.concern
      : "not sure yet what worries you most";
    if (!answers.home_type && !answers.stage && !answers.concern) {
      return `You're in ${state} and left the rest open — we'll keep the roadmap broad.`;
    }
    return `For ${home} in ${state} who's ${stage} and most focused on ${concern}.`;
  }

  function renderRoadmap(data) {
    const stateName = document.getElementById("roadmap-state-name");
    const recap = document.getElementById("roadmap-recap");
    const list = document.getElementById("step-list");
    if (stateName) stateName.textContent = data.state || answers.state;
    if (recap) recap.textContent = buildRecapLine();
    if (!list) return;
    list.innerHTML = "";
    (data.steps || []).forEach((step, idx) => {
      const li = document.createElement("li");
      li.className = "step-card";
      const citeBlock =
        step.source_url && step.source_title
          ? `<div class="step-card__meta"><a class="step-card__cite" href="${escapeHtml(step.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
              step.source_title
            )}</a></div>`
          : `<div class="step-card__meta"><span class="step-card__badge">General guidance</span></div>`;
      li.innerHTML = `
        <span class="step-card__num" aria-hidden="true">${idx + 1}</span>
        <h3 class="step-card__name">${escapeHtml(step.name)}</h3>
        <p class="step-card__body">${escapeHtml(step.body)}</p>
        ${citeBlock}
      `;
      list.appendChild(li);
    });
  }

  async function runRoadmap() {
    if (buildBtn.disabled) return;
    chatHistory = [];
    if (chatMessages) chatMessages.innerHTML = "";
    if (chatSuggestions) {
      chatSuggestions.innerHTML = "";
      chatSuggestions.classList.remove("chat-suggestions--hidden");
    }
    show("screen-loading");
    startLoadingAnimation(answers.state);
    const minDelay = wait(1800);
    try {
      const dataPromise = postJSON("/api/roadmap", answers);
      const data = await Promise.all([dataPromise, minDelay]).then(([d]) => d);
      finishLoadingAnimation();
      await wait(380);
      renderRoadmap(data);
      seedChatSuggestions(data.suggestions || []);
      show("screen-roadmap");
    } catch (e) {
      finishLoadingAnimation();
      showToast(e.message || "We had trouble building your roadmap. Try again.");
      show("screen-intake");
    }
  }

  buildBtn.addEventListener("click", runRoadmap);

  document.getElementById("cta-start-over")?.addEventListener("click", () => {
    closeChat();
    show("screen-intake");
  });

  // -------------------------------------------------------------------------
  // Chat
  // -------------------------------------------------------------------------
  const chatPanel = document.getElementById("chat-panel");
  const chatBackdrop = document.getElementById("chat-backdrop");
  const chatClose = document.getElementById("chat-close");
  const chatSuggestions = document.getElementById("chat-suggestions");
  const chatMessages = document.getElementById("chat-messages");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatSend = document.getElementById("chat-send");

  let chatHistory = [];

  function openChat() {
    if (!chatPanel) return;
    chatPanel.classList.add("chat-panel--open");
    chatPanel.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    setTimeout(() => chatInput?.focus(), 50);
  }

  function closeChat() {
    if (!chatPanel) return;
    chatPanel.classList.remove("chat-panel--open");
    chatPanel.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  document.getElementById("cta-followup")?.addEventListener("click", openChat);
  chatClose?.addEventListener("click", closeChat);
  chatBackdrop?.addEventListener("click", closeChat);

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && chatPanel?.classList.contains("chat-panel--open")) {
      closeChat();
    }
  });

  function seedChatSuggestions(suggestions) {
    if (!chatSuggestions) return;
    chatSuggestions.innerHTML = "";
    chatSuggestions.classList.remove("chat-suggestions--hidden");
    for (const text of suggestions.slice(0, 3)) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chat-suggestion";
      btn.textContent = text;
      btn.addEventListener("click", () => sendChatMessage(text));
      chatSuggestions.appendChild(btn);
    }
  }

  function hideSuggestionsRow() {
    chatSuggestions?.classList.add("chat-suggestions--hidden");
  }

  function appendUserBubble(text) {
    const row = document.createElement("div");
    row.className = "chat-row chat-row--user";
    const b = document.createElement("div");
    b.className = "chat-bubble chat-bubble--user";
    b.textContent = text;
    row.appendChild(b);
    chatMessages?.appendChild(row);
    chatMessages?.scrollTo({ top: chatMessages.scrollHeight, behavior: "smooth" });
  }

  function appendAssistantBubble(answer, citations) {
    const row = document.createElement("div");
    row.className = "chat-row";
    const b = document.createElement("div");
    b.className = "chat-bubble chat-bubble--assistant";
    b.textContent = answer;
    row.appendChild(b);
    if (citations && citations.length) {
      const cites = document.createElement("div");
      cites.className = "chat-cites";
      for (const c of citations) {
        const a = document.createElement("a");
        a.className = "chat-cite";
        a.href = c.source_url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = c.source_title || "Source";
        cites.appendChild(a);
      }
      row.appendChild(cites);
    }
    chatMessages?.appendChild(row);
    chatMessages?.scrollTo({ top: chatMessages.scrollHeight, behavior: "smooth" });
  }

  function showTyping() {
    const row = document.createElement("div");
    row.className = "chat-row";
    row.id = "chat-typing-row";
    row.innerHTML =
      '<div class="chat-typing" aria-label="Thinking"><span></span><span></span><span></span></div>';
    chatMessages?.appendChild(row);
    chatMessages?.scrollTo({ top: chatMessages.scrollHeight, behavior: "smooth" });
  }

  function removeTyping() {
    document.getElementById("chat-typing-row")?.remove();
  }

  async function sendChatMessage(text) {
    const q = (text || "").trim();
    if (!q || !chatMessages) return;
    hideSuggestionsRow();
    appendUserBubble(q);
    showTyping();
    chatInput.value = "";
    const priorHistory = chatHistory.slice(-12);
    try {
      const payload = {
        question: q,
        intake: answers,
        history: priorHistory,
      };
      const res = await postJSON("/api/chat", payload);
      removeTyping();
      appendAssistantBubble(res.answer, res.citations || []);
      chatHistory.push({ role: "user", content: q });
      chatHistory.push({ role: "assistant", content: res.answer });
    } catch (e) {
      removeTyping();
      const errText = e.message || "We couldn't answer that right now. Try again.";
      appendAssistantBubble(errText, []);
      chatHistory.push({ role: "user", content: q });
      chatHistory.push({ role: "assistant", content: errText });
    }
  }

  chatForm?.addEventListener("submit", (ev) => {
    ev.preventDefault();
    sendChatMessage(chatInput.value);
  });

  syncBuildButton();

  window.Launchpad = {
    show,
    answers,
    setState,
    selectPill,
    surpriseMe,
    runRoadmap,
    openChat,
    closeChat,
  };
})();
