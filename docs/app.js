const TOPICS = [
  { key: "forehand", label: "Форхенд" },
  { key: "backhand", label: "Бэкхэнд" },
  { key: "serve", label: "Подача" },
  { key: "return", label: "Приём" },
  { key: "movement", label: "Движение" },
  { key: "net", label: "Игра у сетки" },
];

const state = {
  activeBundle: null,
  oura: null,
  flow: null,
  toastTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function apiUrl() {
  return (localStorage.getItem("tennisCoachApiUrl") || window.TENNIS_COACH_DEFAULT_API_URL || "").replace(/\/$/, "");
}

function apiKey() {
  return localStorage.getItem("tennisCoachApiKey") || "";
}

async function apiFetch(path, options = {}) {
  if (!apiUrl()) throw new Error("Укажите адрес API в настройках");
  if (!apiKey() && path !== "/api/health") throw new Error("Сохраните личный API-ключ в настройках");

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeout || 60000);
  try {
    const response = await fetch(`${apiUrl()}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey()}`,
        ...(options.headers || {}),
      },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body?.error?.message || `Ошибка сервиса (${response.status})`);
    }
    $("#connection-dot").classList.add("online");
    return body;
  } catch (error) {
    $("#connection-dot").classList.remove("online");
    if (error.name === "AbortError") throw new Error("Сервис отвечает слишком долго. Попробуйте ещё раз");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => { toast.hidden = true; }, 4200);
}

function setBusy(button, busy, busyText = "Подождите…") {
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? busyText : button.dataset.label;
}

function voiceCard(label, text, kind) {
  const card = document.createElement("article");
  card.className = `voice-card voice-card-${kind}`;
  const title = document.createElement("p");
  title.className = "voice-label";
  title.textContent = label;
  const body = document.createElement("p");
  body.textContent = text;
  card.append(title, body);
  return card;
}

function renderVoices(container, technical, mental) {
  const cards = [];
  if (technical) cards.push(voiceCard("Тренер", technical, "coach"));
  if (mental) cards.push(voiceCard("Психолог", mental, "psychologist"));
  container.replaceChildren(...cards);
}

function renderReviewSummary(container, summary, showHistoryButton = false) {
  container.hidden = false;
  container.replaceChildren();
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "ВЫВОДЫ НА БУДУЩЕЕ";
  const title = document.createElement("h3");
  title.textContent = "Разбор матча";
  const voices = document.createElement("div");
  voices.className = "voice-grid";
  renderVoices(voices, summary.technical, summary.mental);
  container.append(eyebrow, title, voices);

  if (showHistoryButton) {
    const historyButton = document.createElement("button");
    historyButton.type = "button";
    historyButton.className = "primary-button";
    historyButton.textContent = "В историю";
    historyButton.addEventListener("click", () => {
      container.hidden = true;
      renderActiveBundle(null);
      showScreen("history");
    });
    container.append(historyButton);
  }
}

function renderReviewForm(container, matchId, showHistoryButton = false) {
  container.hidden = false;
  container.innerHTML = `
    <p class="eyebrow">ПОСЛЕ МАТЧА</p>
    <h3>Что забираем с собой?</h3>
    <p class="muted">Отдельно посмотрим на игру и на то, что происходило внутри.</p>
    <form class="stack-form review-form">
      <fieldset>
        <legend>Тренер</legend>
        <label>Физическое состояние <output data-rating-output="physical">3 / 5</output>
          <input name="physical_rating" data-rating="physical" type="range" min="1" max="5" value="3">
        </label>
        <label>Техника, физика и тактика
          <textarea name="technical_comment" maxlength="500" required placeholder="Что работало, что не получалось, где не хватило сил?"></textarea>
        </label>
      </fieldset>
      <fieldset>
        <legend>Психолог</legend>
        <label>Устойчивость и фокус <output data-rating-output="mental">3 / 5</output>
          <input name="mental_rating" data-rating="mental" type="range" min="1" max="5" value="3">
        </label>
        <label>Эмоции и концентрация
          <textarea name="mental_comment" maxlength="500" required placeholder="Что происходило после ошибок и сложных эпизодов?"></textarea>
        </label>
      </fieldset>
      <button class="primary-button" type="submit">Получить разбор</button>
    </form>`;

  container.querySelectorAll("[data-rating]").forEach((input) => {
    input.addEventListener("input", () => {
      container.querySelector(`[data-rating-output="${input.dataset.rating}"]`).textContent = `${input.value} / 5`;
    });
  });
  container.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button");
    const formData = new FormData(event.currentTarget);
    const payload = Object.fromEntries(formData.entries());
    payload.physical_rating = Number(payload.physical_rating);
    payload.mental_rating = Number(payload.mental_rating);
    setBusy(button, true, "Разбираю…");
    try {
      const result = await apiFetch(`/api/matches/${matchId}/review`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      renderReviewSummary(container, result.summary, showHistoryButton);
      container.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showToast(error.message);
      setBusy(button, false);
    }
  });
}

function showScreen(name) {
  $$(".screen").forEach((screen) => { screen.hidden = screen.id !== `screen-${name}`; });
  $$(".bottom-nav button").forEach((button) => button.classList.toggle("active", button.dataset.screen === name));
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (name === "history") loadHistory();
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", year: "numeric" })
    .format(new Date(`${String(value).slice(0, 10)}T12:00:00`));
}

function displayScore(score) {
  if (!score) return "0–0";
  return [score.sets, score.game].filter(Boolean).join(" · ") || "0–0";
}

function currentScore() {
  return {
    sets: $("#score-sets").value.trim(),
    game: $("#score-game").value,
    serving: $("#score-serving").value,
  };
}

function setScoreFields(score = {}) {
  $("#score-sets").value = score.sets || "";
  $("#score-game").value = score.game || "0-0";
  $("#score-serving").value = score.serving || "unknown";
  $("#score-display").textContent = displayScore(score);
}

function renderOura(oura) {
  state.oura = oura;
  const card = $("#oura-card");
  const checkbox = $("#use-oura");
  card.classList.toggle("stale", Boolean(oura?.is_stale));

  if (!oura) {
    $("#oura-title").textContent = "Данных пока нет";
    $("#oura-meta").textContent = "Бриф можно получить без показателей Oura.";
    $("#oura-metrics").replaceChildren();
    checkbox.checked = false;
    checkbox.disabled = true;
    return;
  }

  checkbox.disabled = false;
  checkbox.checked = !oura.is_stale;
  $("#oura-title").textContent = oura.is_stale ? "Есть данные, но они устарели" : "Данные готовы";
  $("#oura-meta").textContent = `${formatDate(oura.date)} · ${oura.age_days === 0 ? "сегодня" : `${oura.age_days} дн. назад`}`;
  const metrics = [
    [oura.readiness ?? "—", "Readiness"],
    [oura.sleep_score ?? "—", "Sleep"],
    [oura.average_hrv != null ? `${Math.round(oura.average_hrv)}` : "—", "HRV, мс"],
  ];
  const container = $("#oura-metrics");
  container.replaceChildren(...metrics.map(([value, label]) => {
    const item = document.createElement("div");
    item.className = "metric";
    const strong = document.createElement("strong");
    strong.textContent = value;
    const span = document.createElement("span");
    span.textContent = label;
    item.append(strong, span);
    return item;
  }));
}

async function loadOura() {
  if (!apiKey()) return renderOura(null);
  try {
    const result = await apiFetch("/api/oura/latest");
    renderOura(result.oura);
  } catch (error) {
    renderOura(null);
    showToast(error.message);
  }
}

function renderActiveBundle(bundle) {
  state.activeBundle = bundle;
  const hasActive = Boolean(bundle?.match);
  $("#no-active-match").hidden = hasActive;
  $("#active-match").hidden = !hasActive;
  if (!hasActive) return;

  $("#post-match-review").hidden = true;

  const match = bundle.match;
  $("#match-opponent").textContent = match.opponent_name
    ? `Матч с ${match.opponent_name}`
    : `Матч · ${match.opponent_level}`;
  setScoreFields(match.current_score || {});
  const started = match.status === "in_progress";
  $("#changeover-button").disabled = !started;
  $("#new-set-button").disabled = !started;

  $("#prep-form").hidden = true;
  $("#prep-result").hidden = false;
  renderVoices(
    $("#prep-voices"),
    bundle.prep?.generated_brief_technical || "Бриф готов.",
    bundle.prep?.generated_brief_mental || "",
  );
  $("#start-match").textContent = started ? "Вернуться в матч" : "Начать матч";
  $("#start-match").dataset.label = $("#start-match").textContent;

  const latestEvent = bundle.events?.at(-1);
  if (latestEvent) {
    $("#advice-result").hidden = false;
    $("#advice-text").textContent = latestEvent.generated_advice;
  }
}

async function restoreActiveMatch() {
  if (!apiKey()) return;
  try {
    const result = await apiFetch("/api/matches/active");
    renderActiveBundle(result.active_match);
  } catch (error) {
    showToast(error.message);
  }
}

async function submitPrep(event) {
  event.preventDefault();
  const button = $("#prep-submit");
  setBusy(button, true, "Собираю план…");
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  payload.energy_level = Number(payload.energy_level);
  payload.use_oura = $("#use-oura").checked;

  try {
    const result = await apiFetch("/api/matches/prep", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.activeBundle = { match: result.match, prep: result.prep, events: [] };
    renderVoices($("#prep-voices"), result.brief.technical, result.brief.mental);
    $("#prep-result").hidden = false;
    $("#prep-result").scrollIntoView({ behavior: "smooth", block: "center" });
    renderActiveBundle(state.activeBundle);
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(button, false);
  }
}

async function startMatch() {
  if (!state.activeBundle?.match) return;
  if (state.activeBundle.match.status === "in_progress") {
    showScreen("match");
    return;
  }
  const button = $("#start-match");
  setBusy(button, true, "Начинаю…");
  try {
    const result = await apiFetch(`/api/matches/${state.activeBundle.match.id}/start`, { method: "POST", body: "{}" });
    state.activeBundle.match = result.match;
    renderActiveBundle(state.activeBundle);
    showScreen("match");
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(button, false);
  }
}

async function saveScore(event) {
  event.preventDefault();
  if (!state.activeBundle?.match) return;
  const button = event.currentTarget.querySelector("button");
  setBusy(button, true);
  try {
    const result = await apiFetch(`/api/matches/${state.activeBundle.match.id}/score`, {
      method: "PATCH",
      body: JSON.stringify({ score: currentScore() }),
    });
    state.activeBundle.match = result.match;
    setScoreFields(result.match.current_score);
    showToast("Счёт сохранён");
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(button, false);
  }
}

function startCardFlow(eventType) {
  state.flow = {
    eventType,
    index: 0,
    working: [],
    notWorking: [],
    idempotencyKey: crypto.randomUUID(),
  };
  $("#advice-result").hidden = true;
  $("#card-flow").hidden = false;
  renderTopicCard();
  $("#card-flow").scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderProgress(current, total) {
  return `<div class="flow-progress" aria-label="Шаг ${current} из ${total}"><span style="width:${Math.min((current / total) * 100, 100)}%"></span></div>`;
}

function renderTopicCard() {
  const flow = state.flow;
  if (flow.index >= TOPICS.length) return renderFeelingStep();
  const topic = TOPICS[flow.index];
  const container = $("#card-flow");
  container.innerHTML = `
    ${renderProgress(flow.index + 1, TOPICS.length + 1)}
    <div class="topic-card">${topic.label}</div>
    <div class="choice-buttons">
      <button type="button" class="choice-good" data-choice="good">✓ Идёт</button>
      <button type="button" class="choice-bad" data-choice="bad">× Не идёт</button>
      <button type="button" class="choice-skip" data-choice="skip">— Пропустить</button>
    </div>`;
  container.querySelectorAll("[data-choice]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.choice === "good") flow.working.push(topic.key);
      if (button.dataset.choice === "bad") flow.notWorking.push(topic.key);
      flow.index += 1;
      renderTopicCard();
    });
  });
}

function renderFeelingStep() {
  const flow = state.flow;
  const energy = flow.eventType === "new_set"
    ? `<label>Запас сил
         <select id="event-energy">
           <option value="5">5 — полно сил</option><option value="4">4 — хороший</option>
           <option value="3" selected>3 — средний</option><option value="2">2 — тяжело</option>
           <option value="1">1 — почти нет</option>
         </select>
       </label>`
    : "";
  $("#card-flow").innerHTML = `
    ${renderProgress(TOPICS.length + 1, TOPICS.length + 1)}
    <form id="feeling-form" class="feeling-form">
      <label>Как ты сейчас?
        <select id="event-feeling" required>
          <option value="спокоен и собран">Спокоен и собран</option>
          <option value="нормально">Нормально</option>
          <option value="устал, но контролирую состояние">Устал</option>
          <option value="зажат и тороплюсь">Зажат / тороплюсь</option>
          <option value="есть боль или дискомфорт">Боль / дискомфорт</option>
        </select>
      </label>
      ${energy}
      <p class="muted">Совет будет учитывать счёт ${displayScore(currentScore())}.</p>
      <button class="primary-button" type="submit">Получить совет</button>
    </form>`;
  $("#feeling-form").addEventListener("submit", submitEvent);
}

async function submitEvent(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  setBusy(button, true, "Думаю…");
  const flow = state.flow;
  const payload = {
    idempotency_key: flow.idempotencyKey,
    event_type: flow.eventType,
    working_well: flow.working,
    not_working: flow.notWorking,
    how_feeling: $("#event-feeling").value,
    score: currentScore(),
  };
  if (flow.eventType === "new_set") payload.energy_level = Number($("#event-energy").value);

  try {
    const result = await apiFetch(`/api/matches/${state.activeBundle.match.id}/events`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.activeBundle.events = [...(state.activeBundle.events || []), result.event];
    state.activeBundle.match.current_score = payload.score;
    $("#card-flow").hidden = true;
    $("#advice-text").textContent = result.advice;
    $("#advice-result").hidden = false;
    $("#advice-result").scrollIntoView({ behavior: "smooth", block: "center" });
    state.flow = null;
  } catch (error) {
    showToast(error.message);
    setBusy(button, false);
  }
}

async function finishMatch(event) {
  event.preventDefault();
  if (!state.activeBundle?.match) return;
  const button = event.currentTarget.querySelector("button");
  setBusy(button, true, "Сохраняю…");
  const finalScore = new FormData(event.currentTarget).get("final_score");
  try {
    const result = await apiFetch(`/api/matches/${state.activeBundle.match.id}/finish`, {
      method: "POST",
      body: JSON.stringify({ final_score: finalScore }),
    });
    state.activeBundle = null;
    $("#active-match").hidden = true;
    $("#no-active-match").hidden = true;
    $("#prep-form").hidden = false;
    $("#prep-result").hidden = true;
    renderReviewForm($("#post-match-review"), result.match.id, true);
    $("#post-match-review").scrollIntoView({ behavior: "smooth", block: "start" });
    showToast("Матч сохранён. Теперь короткий разбор");
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(button, false);
  }
}

async function cancelMatch() {
  if (!state.activeBundle?.match) return;
  if (!window.confirm("Отменить этот матч? Он не появится в истории.")) return;
  try {
    await apiFetch(`/api/matches/${state.activeBundle.match.id}`, { method: "DELETE" });
    state.activeBundle = null;
    renderActiveBundle(null);
    $("#prep-form").hidden = false;
    $("#prep-result").hidden = true;
    showToast("Матч отменён");
    showScreen("prep");
  } catch (error) {
    showToast(error.message);
  }
}

function matchTitle(match) {
  return match.opponent_name || match.opponent_level || "Матч";
}

function parseFinalScore(score) {
  const sets = String(score || "")
    .trim()
    .split(/\s+/)
    .map((token) => {
      const match = token.match(/^(\d+)\s*[-–—:]\s*(\d+)(\(\d+\))?[,;]?$/);
      if (!match) return null;
      return {
        self: Number(match[1]),
        opponent: Number(match[2]),
        tiebreak: match[3] || "",
      };
    })
    .filter(Boolean);

  const selfSets = sets.filter((set) => set.self > set.opponent).length;
  const opponentSets = sets.filter((set) => set.opponent > set.self).length;
  let outcome = null;
  if (selfSets > opponentSets) outcome = "win";
  if (opponentSets > selfSets) outcome = "loss";
  return { sets, outcome };
}

function matchOutcome(match) {
  if (match.status !== "completed" || !match.final_score) return null;
  return parseFinalScore(match.final_score).outcome;
}

function outcomeBadge(outcome, fallback = "") {
  const badge = document.createElement("span");
  badge.className = `outcome-badge ${outcome ? `outcome-${outcome}` : "outcome-neutral"}`;
  if (outcome === "win") {
    badge.textContent = "W";
    badge.setAttribute("aria-label", "Победа");
    badge.title = "Победа";
  } else if (outcome === "loss") {
    badge.textContent = "L";
    badge.setAttribute("aria-label", "Поражение");
    badge.title = "Поражение";
  } else {
    badge.textContent = fallback;
  }
  return badge;
}

function scoreLine(score) {
  const container = document.createElement("span");
  container.className = "scoreline";
  container.setAttribute("aria-label", `Счёт ${score}`);
  const parsed = parseFinalScore(score);

  if (!parsed.sets.length) {
    container.textContent = score;
    return container;
  }

  parsed.sets.forEach((set, index) => {
    if (index) container.append(document.createTextNode(" "));
    const setScore = document.createElement("span");
    setScore.className = "set-score";
    const self = document.createElement(set.self > set.opponent ? "strong" : "span");
    self.textContent = set.self;
    const separator = document.createElement("span");
    separator.className = "score-separator";
    separator.textContent = "–";
    const opponent = document.createElement(set.opponent > set.self ? "strong" : "span");
    opponent.textContent = set.opponent;
    setScore.append(self, separator, opponent);
    if (set.tiebreak) {
      const tiebreak = document.createElement("small");
      tiebreak.className = "set-tiebreak";
      tiebreak.textContent = set.tiebreak;
      setScore.append(tiebreak);
    }
    container.append(setScore);
  });
  return container;
}

function matchResult(match) {
  const result = document.createElement("span");
  result.className = "match-result";
  const outcome = matchOutcome(match);
  if (match.final_score) {
    result.append(outcomeBadge(outcome, "—"), scoreLine(match.final_score));
  } else if (match.status === "in_progress") {
    result.append(outcomeBadge(null, "LIVE"));
    const score = displayScore(match.current_score);
    const current = document.createElement("span");
    current.className = "scoreline";
    current.textContent = score;
    result.append(current);
  } else {
    result.append(outcomeBadge(null, "ПЛАН"));
  }
  return result;
}

async function loadHistory() {
  const list = $("#matches-list");
  $("#match-detail").hidden = true;
  list.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "muted";
  loading.textContent = "Загружаю историю…";
  list.append(loading);
  try {
    const result = await apiFetch("/api/matches");
    list.replaceChildren();
    if (!result.matches.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Здесь появятся завершённые и активные матчи.";
      return list.append(empty);
    }
    result.matches.forEach((match) => {
      const button = document.createElement("button");
      const outcome = matchOutcome(match);
      button.className = `match-list-item ${outcome ? `result-${outcome}` : "result-neutral"}`;
      const main = document.createElement("span");
      main.className = "match-list-main";
      const title = document.createElement("strong");
      title.textContent = matchTitle(match);
      const meta = document.createElement("small");
      meta.textContent = `${formatDate(match.match_date)} · ${match.surface}`;
      main.append(title, document.createElement("br"), meta);
      button.append(main, matchResult(match));
      button.addEventListener("click", () => loadMatchDetail(match.id));
      list.append(button);
    });
  } catch (error) {
    list.replaceChildren();
    showToast(error.message);
  }
}

async function loadMatchDetail(matchId) {
  const detail = $("#match-detail");
  detail.hidden = false;
  detail.textContent = "Загружаю матч…";
  try {
    const bundle = await apiFetch(`/api/matches/${matchId}`);
    detail.replaceChildren();
    const outcome = matchOutcome(bundle.match);
    detail.className = `history-detail ${outcome ? `result-${outcome}` : "result-neutral"}`;
    const heading = document.createElement("div");
    heading.className = "history-detail-heading";
    const headingTitle = document.createElement("h3");
    headingTitle.textContent = matchTitle(bundle.match);
    heading.append(headingTitle, matchResult(bundle.match));
    const briefLabel = document.createElement("p");
    briefLabel.className = "eyebrow";
    briefLabel.textContent = "БРИФ";
    const brief = document.createElement("div");
    brief.className = "voice-grid compact";
    if (bundle.prep) {
      renderVoices(
        brief,
        bundle.prep.generated_brief_technical,
        bundle.prep.generated_brief_mental,
      );
    } else {
      const missingBrief = document.createElement("p");
      missingBrief.className = "muted";
      missingBrief.textContent = "Без подготовительного брифа";
      brief.append(missingBrief);
    }
    const timeline = document.createElement("div");
    timeline.className = "timeline";
    bundle.events.forEach((event) => {
      const item = document.createElement("article");
      const title = document.createElement("strong");
      title.textContent = `${event.event_type === "new_set" ? "Новый сет" : "Переход"} · ${displayScore(event.score_at_event)}`;
      const advice = document.createElement("p");
      advice.textContent = event.generated_advice;
      item.append(title, advice);
      timeline.append(item);
    });
    const reviewSection = document.createElement("section");
    reviewSection.className = "history-review";
    if (bundle.review) {
      renderReviewSummary(reviewSection, {
        technical: bundle.review.generated_technical_summary,
        mental: bundle.review.generated_mental_summary,
      });
    } else if (bundle.match.status === "completed") {
      const reviewButton = document.createElement("button");
      reviewButton.type = "button";
      reviewButton.className = "secondary-button";
      reviewButton.textContent = "Разобрать матч";
      reviewButton.addEventListener("click", () => {
        renderReviewForm(reviewSection, bundle.match.id);
        reviewSection.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      reviewSection.append(reviewButton);
    }
    detail.append(heading, briefLabel, brief, timeline, reviewSection);
    detail.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    detail.hidden = true;
    showToast(error.message);
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const status = $("#settings-status");
  localStorage.setItem("tennisCoachApiUrl", $("#settings-api-url").value.trim().replace(/\/$/, ""));
  localStorage.setItem("tennisCoachApiKey", $("#settings-api-key").value.trim());
  setBusy(button, true, "Проверяю…");
  status.className = "status-message";
  status.textContent = "Проверяю подключение…";
  try {
    await apiFetch("/api/matches/active");
    status.className = "status-message success";
    status.textContent = "Подключение работает.";
    await Promise.all([loadOura(), restoreActiveMatch()]);
  } catch (error) {
    status.className = "status-message error";
    status.textContent = error.message;
  } finally {
    setBusy(button, false);
  }
}

function bindEvents() {
  $$(".bottom-nav button").forEach((button) => button.addEventListener("click", () => showScreen(button.dataset.screen)));
  $$('[data-go="prep"]').forEach((button) => button.addEventListener("click", () => showScreen("prep")));
  $("#prep-energy").addEventListener("input", (event) => { $("#energy-output").textContent = `${event.target.value} / 5`; });
  $("#prep-form").addEventListener("submit", submitPrep);
  $("#start-match").addEventListener("click", startMatch);
  $("#score-form").addEventListener("submit", saveScore);
  $("#score-sets").addEventListener("input", () => { $("#score-display").textContent = displayScore(currentScore()); });
  $("#score-game").addEventListener("change", () => { $("#score-display").textContent = displayScore(currentScore()); });
  $("#changeover-button").addEventListener("click", () => startCardFlow("changeover"));
  $("#new-set-button").addEventListener("click", () => startCardFlow("new_set"));
  $("#finish-form").addEventListener("submit", finishMatch);
  $("#cancel-match").addEventListener("click", cancelMatch);
  $("#refresh-history").addEventListener("click", loadHistory);
  $("#settings-form").addEventListener("submit", saveSettings);
}

function applyLinkCredentials() {
  const params = new URLSearchParams(window.location.search);
  const key = params.get("key");
  if (!key) return;
  localStorage.setItem("tennisCoachApiKey", key.trim());
  params.delete("key");
  const cleanUrl = window.location.pathname + (params.toString() ? `?${params}` : "") + window.location.hash;
  window.history.replaceState({}, "", cleanUrl);
}

async function boot() {
  applyLinkCredentials();
  bindEvents();
  $("#settings-api-url").value = apiUrl();
  $("#settings-api-key").value = apiKey();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});

  if (!apiKey()) {
    renderOura(null);
    showScreen("settings");
    $("#settings-status").textContent = "Сохраните параметры, чтобы начать.";
    return;
  }
  await Promise.all([loadOura(), restoreActiveMatch()]);
}

boot();
