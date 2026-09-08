"use strict";
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const h = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const SELF_ISSUES = [
  ["many_errors", "Много ошибок"],
  ["overhitting", "Рискую"],
  ["short_balls", "Коротко играю"],
  ["slow_movement", "Не двигаюсь"],
  ["tight", "Зажался"],
  ["emotionally_drained", "Морально устал"],
];
const OPPONENT_ACTIONS = [
  ["slice", "Режет"],
  ["drop_shots", "Укорачивает"],
  ["gets_everything_back", "Возвращает всё"],
  ["baseline_pressure", "Давит с задней"],
  ["flat_hitting", "Плоско"],
  ["comes_to_net", "К сетке"],
];
const OPPONENT_STYLE_CHIPS = [
  "Силовая игра с задней линии",
  "Укороты и игра у сетки",
  "Защита, много подбирает",
  "Тяжёлый топспин",
  "Плоский быстрый удар",
  "Много слайсов",
];
const LABELS = Object.fromEntries([
  ...SELF_ISSUES,
  ...OPPONENT_ACTIONS,
  ["ahead", "Веду"],
  ["even", "Ровно"],
  ["behind", "Проигрываю"],
  ["early", "Начало"],
  ["middle", "Середина"],
  ["late", "Концовка"],
]);
const SURFACES = {
  hard: "хард",
  clay: "грунт",
  grass: "трава",
  carpet: "ковёр",
  other: "другое",
};
const state = {
  screen: "prep",
  activeBundle: null,
  detail: null,
  back: null,
  flow: "changeover",
  reviewId: null,
  advice: null,
  history: {
    month: localMonth(),
    items: [],
    next: null,
    loaded: false,
    scroll: 0,
  },
  dossier: null,
  dossierBack: "history",
  busy: new Set(),
};
function localMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function apiUrl() {
  return (
    localStorage.getItem("tennisCoachApiUrl") ||
    window.TENNIS_COACH_DEFAULT_API_URL ||
    ""
  ).replace(/\/$/, "");
}
function apiKey() {
  return localStorage.getItem("tennisCoachApiKey") || "";
}
async function apiFetch(path, options = {}) {
  if (!apiUrl() || !apiKey())
    throw new Error("Укажи адрес API и личный ключ в настройках");
  const controller = new AbortController(),
    timeout = setTimeout(() => controller.abort(), 60000);
  const suffix = path.includes("?") ? "&" : "?";
  try {
    const response = await fetch(
      apiUrl() + path + suffix + "contract_version=2",
      {
        ...options,
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey()}`,
        },
      },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(
        body.error?.message || `Ошибка сервиса (${response.status})`,
      );
      error.code = body.error?.code;
      throw error;
    }
    return body;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error(
        "Сервис отвечает слишком долго. Ввод сохранён — повтори запрос",
      );
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
function showToast(text) {
  $("#toast").textContent = text;
  $("#toast").hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => ($("#toast").hidden = true), 5000);
}
function eventTime(value) {
  return value
    ? new Intl.DateTimeFormat("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "";
}
function formatDate(value) {
  return value
    ? new Intl.DateTimeFormat("ru-RU", {
        day: "numeric",
        month: "short",
      }).format(new Date(value.length === 10 ? value + "T12:00:00" : value))
    : "—";
}
function button(label, action, cls = "primary-button", extra = "") {
  return `<button type="button" class="${cls}" data-action="${action}" ${extra}>${label}</button>`;
}
function hero(title, sub = "") {
  return `<div class="hero"><h1>${h(title)}</h1>${sub ? `<p>${h(sub)}</p>` : ""}</div>`;
}
function input(label, name, value = "", opts = {}) {
  return `<label>${h(label)}<input name="${name}" value="${h(value)}" type="${opts.type || "text"}" maxlength="${opts.max || 200}" ${opts.required ? "required" : ""} ${opts.extra || ""} placeholder="${h(opts.placeholder || "")}"></label>`;
}
function textarea(label, name, placeholder = "", required = false, max = 500) {
  return `<label>${h(label)}<textarea name="${name}" maxlength="${max}" ${required ? "required" : ""} placeholder="${h(placeholder)}"></textarea></label>`;
}
function select(label, name, items) {
  return `<label>${label}<select name="${name}">${items.map(([v, t]) => `<option value="${v}">${h(t)}</option>`).join("")}</select></label>`;
}
function choices(name, items, cls = "segments", multiple = false) {
  return `<div class="${cls} ${items.length === 2 ? "two-options" : ""}" role="group" aria-label="${h(name)}">${items.map(([value, label]) => `<label class="choice ${cls === "style-grid" ? "observation-chip" : ""}"><input type="${multiple ? "checkbox" : "radio"}" name="${name}" value="${h(value)}"><span>${h(label)}</span></label>`).join("")}</div>`;
}
function rating(label, name, low = "минимум", high = "максимум") {
  return `<div class="stack"><p class="eyebrow">${label}</p>${choices(
    name,
    [1, 2, 3, 4, 5].map((n) => [n, n]),
    "rating",
  )}<div class="scale-labels"><span>${low}</span><span>${high}</span></div></div>`;
}
function formError() {
  return '<p class="error-message" role="alert" hidden></p>';
}
function errorIn(form, error) {
  let target = form.querySelector(".error-message");
  if (target) {
    target.textContent = error.message;
    target.hidden = false;
  } else showToast(error.message);
}
function draftKey(kind, id = "new") {
  return `tennisCoachDraft:v2:${encodeURIComponent(apiUrl())}:${kind}:${id}`;
}
function readDraft(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}
function putDraft(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    showToast("Не удалось сохранить черновик на устройстве");
  }
}
function formValues(form) {
  const data = {};
  for (const [key, value] of new FormData(form)) {
    if (["own_issues", "opponent_actions", "opponent_styles"].includes(key)) {
      (data[key] ??= []).push(value);
    } else data[key] = value;
  }
  return data;
}
function saveDraft(form) {
  if (!form?.dataset.draft || form.dataset.busy === "true") return;
  const old = readDraft(form.dataset.draft) || {};
  putDraft(form.dataset.draft, {
    ...old,
    values: formValues(form),
    updated: new Date().toISOString(),
  });
}
function restoreForm(form, values) {
  for (const field of form.elements) {
    if (!field.name || !(field.name in values)) continue;
    const v = values[field.name];
    if (["checkbox", "radio"].includes(field.type))
      field.checked = Array.isArray(v)
        ? v.includes(field.value)
        : String(v) === field.value;
    else field.value = v ?? "";
  }
}
function useDraft(form, kind, id = "new", defaults = {}) {
  const key = draftKey(kind, id),
    draft = readDraft(key);
  form.dataset.draft = key;
  restoreForm(form, draft?.values || defaults);
  if (draft?.values) {
    form.insertAdjacentHTML(
      "afterbegin",
      `<div class="card draft-banner"><div class="row"><span>Черновик восстановлен на этом устройстве</span>${button("Сбросить", "reset-draft", "text-button")}</div></div>`,
    );
  }
  return draft;
}
function persistScreen() {
  const form = $(`#screen-${state.screen} form[data-draft]`);
  saveDraft(form);
  if (state.screen === "finish") saveScoreDraft();
  if (state.screen === "history")
    state.history.scroll = $("#content").scrollTop;
}
function shell(screen, back = null) {
  persistScreen();
  state.screen = screen;
  state.back = back;
  $$(".screen").forEach((el) => (el.hidden = el.id !== `screen-${screen}`));
  $("#actions").hidden = true;
  $("#actions").innerHTML = "";
  $("#actions").className = "action-footer";
  $("#back").hidden = !back;
  $("#content").scrollTop = 0;
  const tabs = {
    plan: "prep",
    observation: "match",
    advice: "match",
    finish: "match",
    review: "match",
    details: "history",
    dossier: "history",
    error: "settings",
  };
  $$("[data-tab]").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === (tabs[screen] || screen));
    b.setAttribute(
      "aria-current",
      b.classList.contains("active") ? "page" : "false",
    );
  });
  const titles = {
    prep: "Подготовка",
    plan: "Шпаргалка",
    match: "На корте",
    observation: "На лавке",
    advice: "Совет",
    finish: "Завершение",
    review: "После матча",
    history: "Журнал",
    details: "Матч",
    dossier: "Досье",
    profile: "Я",
    settings: "Это устройство",
    error: "Подключение",
  };
  $("#crumb").textContent = titles[screen];
  $("#context").textContent = [
    "prep",
    "plan",
    "match",
    "observation",
    "advice",
    "finish",
  ].includes(screen)
    ? state.activeBundle?.match?.opponent_name || ""
    : "";
}
function mount(screen, html, back = null) {
  shell(screen, back);
  const el = $(`#screen-${screen}`);
  el.innerHTML = html;
  return el;
}
function footer(html, single = false) {
  $("#actions").innerHTML = html;
  $("#actions").hidden = false;
  $("#actions").classList.toggle("single", single);
  $("#actions").classList.toggle("primary-first", state.screen === "plan");
  $("#actions").classList.toggle(
    "observation-actions",
    state.screen === "observation",
  );
}
function renderMatchPlan(plan, prep = {}) {
  if (plan && Array.isArray(plan.tactics) && plan.tactics.length === 3) {
    return `<div class="slab"><p class="eyebrow">Фокус</p><p class="plan-focus">${h(plan.focus)}</p></div><ol class="plan-tactics">${plan.tactics.map((t) => `<li>${h(t)}</li>`).join("")}</ol><div class="field-row"><div class="card"><p class="eyebrow">Тело</p><p class="body-text">${h(plan.body)}</p></div><div class="card"><p class="eyebrow">Между розыгрышами</p><p class="body-text">${h(plan.reset)}</p></div></div><div class="card"><p class="eyebrow">Соперник</p><p>${h(plan.opponent_cue)}</p></div>`;
  }
  return voices(
    prep.generated_brief_technical || "План не сохранён",
    prep.generated_brief_mental || "",
  );
}
function voices(technical, mental) {
  return `<article class="card voice-card"><p class="eyebrow">Тренер</p><p class="body-text">${h(technical)}</p></article><article class="card voice-card mental"><p class="eyebrow">Психолог</p><p class="body-text">${h(mental)}</p></article>`;
}
function renderPrep(edit = false) {
  const bundle = state.activeBundle;
  if (bundle && !edit) {
    renderPlan();
    return;
  }
  if (bundle?.match.status === "in_progress") {
    renderPlan();
    return;
  }
  const defaults = bundle
    ? { ...bundle.match, ...bundle.prep }
    : { energy_level: 3 };
  mount(
    "prep",
    hero(
      edit ? "Обновим план" : "Соберём план на матч",
      "Три ориентира, нагрузка и ритуал между розыгрышами.",
    ) +
      `<form id="prep-form" class="stack-form"><fieldset><legend>Матч</legend><div class="field-row">${select(
        "Тип",
        "match_type",
        [
          ["singles", "Одиночка"],
          ["doubles", "Пара"],
        ],
      )}${select("Покрытие", "surface", Object.entries(SURFACES))}</div>${input("Логин соперника · необязательно", "opponent_name", "", { max: 100, extra: 'id="prep-opponent-name" autocomplete="off"', placeholder: "Начни вводить логин" })}<div id="prep-suggestions" class="search-results" hidden></div><aside id="opponent-card" hidden></aside>${input("Уровень соперника", "opponent_level", "", { required: true, max: 100, placeholder: "Равный, сильнее, клубный 4.0…" })}${input("Стиль соперника · свободно", "opponent_style")}<div class="field-row">${select(
        "Событие",
        "session_type",
        [
          ["friendly", "Товарищеский"],
          ["tournament", "Турнир"],
          ["practice", "Тренировка"],
        ],
      )}${select("Длительность", "session_duration", [
        ["unlimited", "Без лимита"],
        ["1h", "1 час"],
        ["1_5h", "1,5 часа"],
        ["2h", "2 часа"],
      ])}</div>${input("Погода", "weather")}</fieldset><fieldset><legend>Состояние</legend>${rating("Энергия", "energy_level", "выжат", "полон сил")}${input("Когда и что ел", "last_meal")}${textarea("Тело · обязательно", "physical_state", "Как спина, колени, ноги, дыхание?", true, 300)}${textarea("Настрой · обязательно", "mindset", "Спокоен, зажат, мотивирован…", true, 300)}</fieldset>${formError()}<button class="primary-button" type="submit">${edit ? "Обновить план" : "Получить план"}</button>${edit ? button("Вернуться к сохранённому плану", "plan", "text-button") : ""}</form>`,
    edit ? "plan" : null,
  );
  const form = $("#prep-form");
  form.dataset.matchId = bundle?.match.id || "";
  form.dataset.revision = bundle?.prep.revision || 1;
  useDraft(form, "prep", bundle?.match.id || "new", defaults);
  if (form.elements.opponent_name.value)
    scheduleSearch(form.elements.opponent_name.value, "prep");
}
function renderPlan() {
  const b = state.activeBundle;
  if (!b) {
    renderPrep();
    return;
  }
  const started = b.match.status === "in_progress";
  mount(
    "plan",
    `<div id="prep-plan" class="stack">${renderMatchPlan(b.prep?.generated_game_plan, b.prep || {})}</div>${started ? '<p class="muted">Анкета и план зафиксированы. Новые наблюдения — через переход и новый сет.</p>' : ""}<details class="card"><summary>Исходная анкета</summary>${prepFacts(b)}</details><p class="error-message" id="plan-error" role="alert" hidden></p>${button("Отменить этот матч", "cancel", "text-button danger-button")}`,
  );
  footer(
    button(
      started ? "Вернуться в матч" : "На корт",
      started ? "match" : "start",
    ) + (started ? "" : button("Изменить", "edit-prep", "secondary-button")),
    started,
  );
}
function prepFacts(b) {
  const m = b.prep?.match_context_snapshot || b.match,
    p = b.prep || {};
  const fields = [
    ["Соперник", m.opponent_name || "Без логина"],
    ["Тип", m.match_type === "doubles" ? "Пара" : "Одиночка"],
    ["Покрытие", SURFACES[m.surface] || m.surface],
    ["Уровень соперника", m.opponent_level],
    ["Исходный стиль", m.opponent_style],
    [
      "Событие",
      {
        friendly: "Товарищеский",
        tournament: "Турнир",
        practice: "Тренировка",
      }[m.session_type] || m.session_format,
    ],
    [
      "Длительность",
      {
        "1h": "1 час",
        "1_5h": "1,5 часа",
        "2h": "2 часа",
        unlimited: "Без лимита",
      }[m.session_duration],
    ],
    ["Погода", m.weather],
    ["Энергия", p.energy_level ? `${p.energy_level}/5` : ""],
    ["Еда", p.last_meal],
    ["Тело", p.physical_state],
    ["Настрой", p.mindset],
  ];
  const profile = p.player_profile_snapshot || {};
  return `<div class="stack readonly">${fields.map(([label, value]) => `<p><strong>${label}:</strong> ${h(value || "—")}</p>`).join("")}${
    Object.keys(profile).length
      ? `<details class="card"><summary>Профиль на момент подготовки</summary>${[
          ["level", "Уровень"],
          ["experience", "Опыт"],
          ["playing_style", "Стиль"],
          ["strengths", "Сильные стороны"],
          ["mental_pattern", "Реакция под давлением"],
          ["medical_context", "Здоровье и ограничения"],
        ]
          .map(
            ([k, l]) => `<p><strong>${l}:</strong> ${h(profile[k] || "—")}</p>`,
          )
          .join("")}</details>`
      : ""
  }${!p.match_context_snapshot ? '<p class="muted">Старая запись: исходный контекст мог уточняться по ходу матча.</p>' : ""}</div>`;
}
function renderMatch() {
  const b = state.activeBundle;
  if (!b) {
    mount(
      "match",
      `<div class="empty-state">${hero("Активного матча нет", "Сначала собери план на матч.")}${button("К подготовке", "prep")}</div>`,
    );
    return;
  }
  if (b.match.status === "preparing") {
    renderPlan();
    return;
  }
  const ev = b.events?.at(-1);
  mount(
    "match",
    `${ev ? `<div class="slab"><p class="eyebrow">${ev.event_type === "new_set" ? "План на сет" : "Последний совет"} · ${h(eventTime(ev.created_at))}</p><p class="advice-text">${h(ev.generated_advice)}</p></div><details class="card"><summary>Исходный план</summary><div class="stack">${renderMatchPlan(b.prep?.generated_game_plan, b.prep || {})}</div></details>` : `<div class="stack">${renderMatchPlan(b.prep?.generated_game_plan, b.prep || {})}</div>`}${ev?.score_state ? `<p class="muted">На последнем переходе: ${h(LABELS[ev.score_state])} · ${h(LABELS[ev.set_stage])}</p>` : ""}<div class="grow"></div>${button("Завершить матч", "finish", "text-button")}`,
  );
  footer(
    button("Переход", "changeover") +
      button("Новый сет", "new-set", "secondary-button"),
  );
}
function observationChips(items, name, opponent = false) {
  return items
    .map(
      ([key, label]) =>
        `<label class="choice observation-chip ${opponent ? "opponent-chip" : ""}"><input type="checkbox" name="${name}" value="${key}"><span>${label}</span></label>`,
    )
    .join("");
}
function renderObservation(kind) {
  state.flow = kind;
  const isSet = kind === "new_set";
  mount(
    "observation",
    `<div class="slab observation-title"><p class="eyebrow">${isSet ? "Новый сет" : "Переход"}</p><strong>${isSet ? "Что было в прошлом сете?" : "Отметь главное"}</strong></div><form id="observation-form" class="stack-form"><div class="observation-columns"><div><p class="eyebrow">Я</p>${observationChips(SELF_ISSUES, "own_issues")}</div><div><p class="eyebrow">Он</p>${observationChips(OPPONENT_ACTIONS, "opponent_actions", true)}</div></div>${
      isSet
        ? `<p class="eyebrow">Прошлый сет</p>${choices("completed_set_result", [
            ["won", "Выиграл сет"],
            ["lost", "Проиграл сет"],
          ])}${rating("Запас сил", "energy_level", "выжат", "полон сил")}`
        : `<p class="eyebrow">В текущем сете</p>${choices("score_state", [
            ["ahead", "Веду"],
            ["even", "Ровно"],
            ["behind", "Проигрываю"],
          ])}<p class="eyebrow">Стадия сета</p>${choices("set_stage", [
            ["early", "Начало"],
            ["middle", "Середина"],
            ["late", "Концовка"],
          ])}`
    }<details class="card compact"><summary>Комментарий · необязательно</summary>${textarea("Если чипов не хватило", "comment", "Что важно учесть?", false, 300)}</details>${formError()}</form>`,
    "match",
  );
  useDraft($("#observation-form"), kind, state.activeBundle.match.id);
  footer(
    button("Отмена", "match", "secondary-button") +
      `<button class="lime-button" form="observation-form" type="submit">${isSet ? "План на сет" : "Один совет"}</button>`,
  );
}
function renderAdvice() {
  const ev = state.advice || state.activeBundle?.events?.at(-1);
  if (!ev) {
    renderMatch();
    return;
  }
  const labels = [...(ev.own_issues || []), ...(ev.opponent_actions || [])].map(
    (k) => LABELS[k] || k,
  );
  mount(
    "advice",
    `<div class="grow"></div><div class="slab"><p class="eyebrow">${ev.event_type === "new_set" ? "План на следующий сет" : "Следующий фокус"}</p><p class="advice-text">${h(ev.generated_advice)}</p></div>${labels.length ? `<div class="card"><p class="eyebrow">Ты отметил</p><p>${h(labels.join(" · "))}</p></div>` : ""}<div class="grow"></div>`,
    "match",
  );
  footer(button("На корт", "match"), true);
}
function createScoreWheel(side, value, onChange) {
  const wheel = document.createElement("div");
  wheel.className = "score-wheel";
  wheel.tabIndex = 0;
  wheel.setAttribute("role", "listbox");
  wheel.setAttribute(
    "aria-label",
    side === "self" ? "Мои геймы" : "Геймы соперника",
  );
  const max = Math.max(12, Number(value) || 0);
  wheel.dataset.value = value;
  wheel.innerHTML =
    '<div class="score-wheel-spacer" aria-hidden="true"></div>' +
    Array.from(
      { length: max + 1 },
      (_, n) =>
        `<button type="button" class="score-wheel-option${n === value ? " is-selected" : ""}" role="option" aria-selected="${n === value}" data-value="${n}">${n}</button>`,
    ).join("") +
    '<div class="score-wheel-spacer" aria-hidden="true"></div>';
  let ready = false;
  function mark(n) {
    wheel.dataset.value = n;
    wheel.querySelectorAll("[role=option]").forEach((b) => {
      b.classList.toggle("is-selected", Number(b.dataset.value) === n);
      b.setAttribute(
        "aria-selected",
        Number(b.dataset.value) === n ? "true" : "false",
      );
    });
    onChange(n);
  }
  wheel.addEventListener("click", (e) => {
    const b = e.target.closest("[data-value]");
    if (b && b !== wheel) {
      mark(Number(b.dataset.value));
      wheel.scrollTo({ top: Number(b.dataset.value) * 44, behavior: "smooth" });
    }
  });
  wheel.addEventListener(
    "scroll",
    () => {
      if (ready)
        mark(Math.max(0, Math.min(max, Math.round(wheel.scrollTop / 44))));
    },
    { passive: true },
  );
  wheel.addEventListener("keydown", (e) => {
    if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const v = Number(wheel.dataset.value);
    const n =
      e.key === "Home"
        ? 0
        : e.key === "End"
          ? max
          : Math.max(0, Math.min(max, v + (e.key === "ArrowDown" ? 1 : -1)));
    mark(n);
    wheel.scrollTo({ top: n * 44, behavior: "auto" });
  });
  requestAnimationFrame(() => {
    wheel.scrollTop = value * 44;
    requestAnimationFrame(() => (ready = true));
  });
  return wheel;
}
function saveScoreDraft() {
  if (!state.sets || !state.activeBundle) return;
  const key = draftKey("finish", state.activeBundle.match.id);
  putDraft(key, {
    ...(readDraft(key) || {}),
    sets: state.sets,
    updated: new Date().toISOString(),
  });
}
function finishProblem() {
  if (state.sets.some(([a, b]) => a === b))
    return "Заполни или убери строки с равным счётом";
  const n = state.sets.reduce((n, [a, b]) => n + (a > b ? 1 : -1), 0);
  return n ? "" : "Победитель матча не определён — проверь сеты";
}
function finishLine() {
  return state.sets.map(([a, b]) => `${a}-${b}`).join(" ");
}
function drawWheels() {
  const rows = $("#finish-set-score-rows");
  rows.replaceChildren();
  state.sets.forEach(([a, b], i) => {
    const row = document.createElement("div");
    row.className = "set-score-row";
    row.innerHTML = `<span class="set-score-row-title">${i + 1} сет</span>`;
    const change = (side) => (n) => {
      state.sets[i][side] = n;
      saveScoreDraft();
      updateFinishResult();
    };
    row.append(createScoreWheel("self", a, change(0)));
    const divider = document.createElement("span");
    divider.className = "set-score-divider";
    row.append(divider, createScoreWheel("opponent", b, change(1)));
    rows.append(row);
  });
  updateFinishResult();
}
function updateFinishResult() {
  const label = $("#finish-result");
  if (!label) return;
  const problem = finishProblem();
  label.textContent =
    problem ||
    `${finishLine().replaceAll("-", "–")} · ${state.sets.reduce((n, [a, b]) => n + (a > b ? 1 : -1), 0) > 0 ? "победа" : "поражение"}`;
  $("#remove-set").disabled = state.sets.length <= 1;
  $("#add-set").disabled = state.sets.length >= 5;
}
function renderFinish() {
  const key = draftKey("finish", state.activeBundle.match.id);
  state.sets = readDraft(key)?.sets || [[0, 0]];
  mount(
    "finish",
    hero("Итоговый счёт", "Крути цифры вверх или вниз · сначала мой счёт") +
      `<form id="finish-form" class="stack-form"><div class="card"><div class="wheel-labels"><span></span><span>Я</span><span></span><span>Соперник</span></div><div id="finish-set-score-rows"></div><div class="row">${button("＋ Добавить сет", "add-set", "text-button", 'id="add-set"')}${button("Убрать последний", "remove-set", "text-button", 'id="remove-set"')}</div></div><div class="slab"><p class="eyebrow">Результат</p><p id="finish-result" class="scoreline"></p></div>${formError()}<button class="primary-button" type="submit" name="finish_mode" value="review">Завершить и разобрать</button><button class="secondary-button" type="submit" name="finish_mode" value="later">Сохранить, разобрать позже</button></form>${button("Отменить этот матч", "cancel", "text-button danger-button")}`,
    "match",
  );
  drawWheels();
}
function renderReview(matchId) {
  state.reviewId = matchId;
  mount(
    "review",
    hero(
      "Что забираем с собой?",
      "Заполни то, что есть сказать. Достаточно одного наблюдения словами.",
    ) +
      `<form id="review-form" class="stack-form"><fieldset><legend>Моя игра</legend>${rating("Физическое состояние", "physical_rating", "тяжело", "отлично")}${textarea("Мои ошибки", "own_errors", "Где ошибался и почему?")}</fieldset><fieldset><legend>Моё состояние</legend>${rating("Психологическое состояние", "mental_rating", "не справлялся", "устойчиво")}${textarea("Эмоции и концентрация", "emotional_state", "Что происходило после ошибок?")}</fieldset><fieldset><legend>Соперник</legend><p class="muted">Стиль · можно несколько</p>${choices(
        "opponent_styles",
        OPPONENT_STYLE_CHIPS.map((t) => [t, t]),
        "style-grid",
        true,
      )}${textarea("Уточнение стиля", "opponent_style_note", "Например: слева режет, справа атакует")}${textarea("Что против него работало", "opponent_what_worked", "Например: глубоко под бэкхэнд")}${textarea("На чём он ошибался", "opponent_errors", "Например: не успевал к высокому мячу")}</fieldset><fieldset><legend>Польза</legend><p>Приложение помогло тебе в этом матче?</p>${choices(
        "app_helpful",
        [
          ["true", "Да"],
          ["false", "Нет"],
        ],
      )}</fieldset>${formError()}<button class="primary-button" type="submit">Получить разбор</button></form>`,
    "details",
  );
  useDraft($("#review-form"), "review", matchId);
}
function historyQuery() {
  return state.history.month
    ? `month=${encodeURIComponent(state.history.month)}&`
    : "";
}
function matchRow(m) {
  const status =
    m.status === "preparing"
      ? "План"
      : m.status === "in_progress"
        ? "Идёт"
        : !m.has_review
          ? "Без разбора"
          : "";
  const result = scoreOutcome(m.final_score);
  return `<button class="match-list-item result-${result || "neutral"}" data-action="detail" data-id="${h(m.id)}"><span class="muted">${h(formatDate(m.match_date))}</span><span><strong>${h(m.opponent_name || "Без логина")}</strong><span class="muted">${status ? `<br>${status}` : ""}</span></span><span class="score">${h(m.final_score?.replaceAll("-", "–") || status || "—")}</span></button>`;
}
function scoreOutcome(score) {
  const parts = String(score || "")
    .trim()
    .split(/\s+/)
    .map((t) => t.match(/^(\d+)[-–—:](\d+)(?:\(\d+\))?[,;]?$/));
  if (!parts.length || parts.some((p) => !p || p[1] === p[2])) return null;
  const n = parts.reduce(
    (n, p) => n + (Number(p[1]) > Number(p[2]) ? 1 : -1),
    0,
  );
  return n > 0 ? "win" : n < 0 ? "loss" : null;
}
function renderHistory() {
  mount(
    "history",
    hero("Журнал") +
      `<div class="card"><label>Найти соперника<input id="history-search" autocomplete="off" placeholder="Логин или старое имя"></label><div id="history-suggestions" class="search-results" hidden></div></div><div class="field-row"><label>Месяц<input type="month" id="history-month" value="${h(state.history.month || localMonth())}"></label>${button("За всё время", "all-time", "secondary-button")}</div><p class="muted" id="history-period">${state.history.month ? h(state.history.month) : "За всё время"}</p><div id="history-stats"></div><div id="matches-list" class="match-list"></div><p id="history-error" class="error-message" role="alert" hidden></p><div class="row">${button("Обновить", "refresh-history", "secondary-button")}${button("Ещё матчи", "more-history", "secondary-button", 'id="more-history" hidden')}</div>`,
  );
  $("#history-search").value = state.history.search || "";
  if (state.history.loaded) {
    paintHistory();
    $("#content").scrollTop = state.history.scroll;
  } else loadHistory();
}
function paintHistory() {
  if (state.screen !== "history") return;
  $("#matches-list").innerHTML = state.history.items.length
    ? state.history.items.map(matchRow).join("")
    : '<p class="card muted">Здесь появятся твои матчи.</p>';
  $("#more-history").hidden = state.history.next === null;
  const s = state.history.stats;
  if (s)
    $("#history-stats").innerHTML =
      `<div class="stats-grid"><div class="card"><p class="eyebrow">Завершено</p><p class="stat-number">${s.completed}</p></div><div class="card"><p class="eyebrow">Победы — поражения</p><p class="stat-number">${s.wins}–${s.losses}</p>${s.unknown ? `<p class="muted">${s.unknown} без исхода</p>` : ""}</div></div><div class="card"><p>Приложение помогло</p><strong>${s.helpful_total ? `${s.helpful_yes} из ${s.helpful_total} · ${s.helpful_percent}%` : "Пока нет ответов"}</strong></div>`;
}
async function loadHistory(more = false) {
  const month = state.history.month,
    offset = more ? state.history.next : 0;
  if (offset === null) return;
  try {
    const [res, stats] = await Promise.all([
      apiFetch(`/api/matches?${historyQuery()}offset=${offset}`),
      apiFetch(`/api/matches/stats?${historyQuery()}`),
    ]);
    if (month !== state.history.month) return;
    state.history.items = more
      ? [...state.history.items, ...res.matches]
      : res.matches;
    state.history.next = res.next_offset;
    state.history.stats = stats;
    state.history.loaded = true;
    paintHistory();
  } catch (error) {
    if (state.screen === "history") {
      const e = $("#history-error");
      e.textContent = error.message;
      e.hidden = false;
    }
  }
}
async function openDetail(id, back = "history") {
  mount("details", '<p class="loading-note">Загружаю матч…</p>', back);
  try {
    const b = await apiFetch(`/api/matches/${id}`);
    if (state.screen !== "details") return;
    state.detail = b;
    renderDetails(back);
  } catch (e) {
    if (state.screen === "details")
      $("#screen-details").innerHTML =
        `<p class="error-message">${h(e.message)}</p>${button("Повторить", "detail", "secondary-button", `data-id="${h(id)}"`)}`;
  }
}
function eventCard(ev) {
  const labels = [...(ev.own_issues || []), ...(ev.opponent_actions || [])].map(
    (k) => LABELS[k] || k,
  );
  const context = ev.completed_set_result
    ? `${ev.completed_set_result === "won" ? "Сет выигран" : "Сет проигран"} · силы ${ev.energy_level}/5`
    : ev.score_state
      ? `${LABELS[ev.score_state]} · ${LABELS[ev.set_stage]}`
      : JSON.stringify(ev.score_at_event || {});
  return `<details class="card"><summary>${ev.event_type === "new_set" ? "Новый сет" : "Переход"} · ${h(eventTime(ev.created_at))}</summary><p class="muted">${h(context)}</p><div class="tags">${labels.map((l) => `<span class="tag">${h(l)}</span>`).join("")}</div><p class="body-text">${h(ev.observation_comment || ev.how_feeling || "")}</p>${ev.working_well?.length ? `<p>Получалось: ${h(ev.working_well.join(" · "))}</p>` : ""}${ev.not_working?.length ? `<p>Не получалось: ${h(ev.not_working.join(" · "))}</p>` : ""}<p class="body-text">${h(ev.generated_advice)}</p></details>`;
}
function renderDetails(back = state.back || "history") {
  const b = state.detail;
  if (!b) {
    renderHistory();
    return;
  }
  const r = b.review;
  mount(
    "details",
    hero(
      b.match.opponent_name || "Матч",
      `${formatDate(b.match.match_date)} · ${b.match.final_score || "Без результата"}`,
    ) +
      `<details class="card"><summary>Подготовка и исходный план</summary><div class="stack">${prepFacts(b)}${renderMatchPlan(b.prep?.generated_game_plan, b.prep || {})}</div></details><div class="timeline">${(b.events || []).map(eventCard).join("")}${(b.context_updates || []).map((u) => `<div class="card"><p class="eyebrow">Уточнение стиля · ${h(eventTime(u.created_at))}</p><p>${h(u.opponent_style)}</p></div>`).join("")}</div>${r ? `${voices(r.generated_technical_summary, r.generated_mental_summary)}<details class="card"><summary>Мои записи после матча</summary><div class="stack"><p>Тело ${h(r.physical_rating)}/5 · состояние ${h(r.mental_rating)}/5</p>${["own_errors", "emotional_state", "opponent_style", "opponent_what_worked", "opponent_errors"].map((k, i) => `<p><strong>${["Мои ошибки", "Эмоции", "Стиль соперника", "Работало", "Ошибки соперника"][i]}:</strong> ${h(r[k] || (["own_errors", "emotional_state"].includes(k) ? r[k === "own_errors" ? "technical_comment" : "mental_comment"] : "") || "—")}</p>`).join("")}<p>${typeof r.app_helpful === "boolean" ? `Приложение помогло: ${r.app_helpful ? "Да" : "Нет"}` : typeof r.advice_changed_play === "boolean" ? `Совет изменил игру (старый вопрос): ${r.advice_changed_play ? "Да" : "Нет"}` : "Ответ о пользе не сохранён"}</p></div></details>` : b.match.status === "completed" ? button("Разобрать матч", "review") : button("Продолжить матч", "resume")}<div class="history-actions">${b.match.opponent_name ? button("Досье соперника", "dossier", "secondary-button", `data-name="${h(b.match.opponent_name)}"`) : ""}${b.match.status === "completed" ? button("Удалить матч из истории", "delete-match", "text-button danger-button") : ""}</div>`,
    back,
  );
}
function summaryHTML(d) {
  if (!d.summary)
    return `<p class="muted">${d.source_count ? "Сводка ещё не собрана. Исходные записи доступны ниже." : "Сводка появится после первого разбора с наблюдениями."}</p>`;
  return `<dl class="memory-grid">${[
    ["style", "Стиль"],
    ["what_worked", "Работает"],
    ["errors", "Ошибается"],
  ]
    .map(
      ([k, l]) =>
        `<dt>${l}</dt><dd>${h(d.summary[k]?.text || "Нет наблюдений")}<div>${(d.summary[k]?.match_ids || []).map((id, i) => `<a href="#" data-action="detail" data-id="${h(id)}">Источник ${i + 1}</a>`).join("")}</div></dd>`,
    )
    .join("")}</dl>`;
}
function paintDossier() {
  if (state.screen !== "dossier") return;
  const d = state.dossier;
  $("#screen-dossier").innerHTML =
    `<div class="slab"><div class="row"><p class="eyebrow">Досье</p><p class="muted">${d.stats.completed} встреч · ${d.stats.wins}–${d.stats.losses}${d.stats.unknown ? ` · ${d.stats.unknown} без исхода` : ""}</p></div><h1>${h(d.opponent_name)}</h1><p class="eyebrow">AI-сводка</p><p class="muted">${d.stale ? "Есть новые записи" : d.updated_at ? `Обновлено ${formatDate(d.updated_at)}` : "Пока нет сводки"}</p>${summaryHTML(d)}<p class="muted">По ${d.source_count} матчам с наблюдениями</p></div><div id="dossier-update-status" class="muted" role="status"></div>${d.source_count ? button("Обновить сводку", "refresh-dossier", "secondary-button") : ""}<p class="eyebrow">Исходные записи</p>${d.records.map((r) => `<button class="card full-width" data-action="detail" data-id="${h(r.match_id)}"><span class="row"><strong>${h(formatDate(r.match_date))}</strong><span>${h(r.final_score || "Исход не указан")}</span></span><span class="body-text">${h(r.has_review ? [r.opponent_style, r.opponent_what_worked && "Работало: " + r.opponent_what_worked, r.opponent_errors && "Ошибался: " + r.opponent_errors].filter(Boolean).join(" · ") || "В разборе нет наблюдений о сопернике" : "Наблюдений нет — разбор не заполнен")}</span></button>`).join("") || '<p class="card muted">Завершённых встреч пока нет.</p>'}${d.next_offset !== null ? button("Ещё встречи", "more-dossier", "secondary-button") : ""}`;
}
async function openDossier(name, back = state.screen) {
  state.dossierBack = back;
  mount(
    "dossier",
    '<p class="loading-note">Поднимаю историю соперника…</p>',
    back,
  );
  try {
    const d = await apiFetch(
      `/api/opponents/dossier?opponent_name=${encodeURIComponent(name)}`,
    );
    if (state.screen !== "dossier") return;
    state.dossier = d;
    paintDossier();
    if (d.stale) refreshDossier();
  } catch (e) {
    if (state.screen === "dossier")
      $("#screen-dossier").innerHTML =
        `<p class="error-message">${h(e.message)}</p>${button("Повторить", "dossier", "secondary-button", `data-name="${h(name)}"`)}`;
  }
}
async function refreshDossier() {
  const d = state.dossier;
  if (!d || state.refreshingDossier) return;
  state.refreshingDossier = true;
  const status = $("#dossier-update-status");
  if (status) status.textContent = "Обновляю сводку…";
  try {
    await apiFetch("/api/opponents/dossier/refresh", {
      method: "POST",
      body: JSON.stringify({ opponent_name: d.opponent_name }),
    });
    const fresh = await apiFetch(
      `/api/opponents/dossier?opponent_name=${encodeURIComponent(d.opponent_name)}`,
    );
    if (
      state.screen === "dossier" &&
      state.dossier.opponent_name === d.opponent_name
    ) {
      state.dossier = fresh;
      paintDossier();
    }
  } catch (e) {
    if (state.screen === "dossier" && $("#dossier-update-status"))
      $("#dossier-update-status").textContent = e.message;
  } finally {
    state.refreshingDossier = false;
  }
}
async function moreDossier() {
  const d = state.dossier;
  if (d.next_offset === null) return;
  try {
    const more = await apiFetch(
      `/api/opponents/dossier?opponent_name=${encodeURIComponent(d.opponent_name)}&offset=${d.next_offset}`,
    );
    if (state.dossier === d) {
      d.records.push(...more.records);
      d.next_offset = more.next_offset;
      paintDossier();
    }
  } catch (e) {
    showToast(e.message);
  }
}
function scheduleSearch(query, where) {
  clearTimeout(state[where + "SearchTimer"]);
  const serial = (state[where + "SearchSerial"] || 0) + 1;
  state[where + "SearchSerial"] = serial;
  state[where + "SearchTimer"] = setTimeout(
    () => searchOpponents(query, where, serial),
    450,
  );
}
async function searchOpponents(query, where, serial) {
  const host = $(`#${where}-suggestions`);
  if (!host) return;
  const name = query.trim();
  if (!name) {
    host.hidden = true;
    if (where === "prep") $("#opponent-card").hidden = true;
    return;
  }
  try {
    const result = await apiFetch(
      `/api/opponents?query=${encodeURIComponent(name)}`,
    );
    if (state[where + "SearchSerial"] !== serial || !host.isConnected) return;
    host.innerHTML =
      result.opponents
        .map((n) =>
          button(
            h(n),
            where === "prep" ? "pick-opponent" : "dossier",
            "",
            `data-name="${h(n)}"`,
          ),
        )
        .join("") || '<p class="card muted">Совпадений нет</p>';
    host.hidden = false;
    if (where === "prep") {
      const d = await apiFetch(
        `/api/opponents/dossier?opponent_name=${encodeURIComponent(name)}`,
      );
      if (state[where + "SearchSerial"] !== serial || !$("#opponent-card"))
        return;
      const card = $("#opponent-card");
      card.hidden = false;
      card.className = "slab compact";
      card.innerHTML = `<p class="eyebrow">Досье · ${d.stats.completed} встреч</p>${summaryHTML(d)}${button("Открыть полное досье", "dossier", "secondary-button", `data-name="${h(name)}"`)}`;
      if (d.stale) {
        apiFetch("/api/opponents/dossier/refresh", {
          method: "POST",
          body: JSON.stringify({ opponent_name: name }),
        })
          .then(() => {
            if (
              state.screen === "prep" &&
              $("#prep-opponent-name")?.value.trim() === name
            )
              scheduleSearch(name, "prep");
          })
          .catch(() => {});
      }
    }
  } catch (e) {
    if (host.isConnected) {
      host.innerHTML = `<p class="muted">Поиск недоступен. Можно ввести точный логин вручную.</p>`;
      host.hidden = false;
    }
  }
}
async function renderProfile() {
  mount(
    "profile",
    hero("Мой профиль", "Постоянный контекст для новых планов.") +
      `<form id="profile-form" class="stack-form"><fieldset><legend>Моя игра</legend>${input("Уровень", "level", "", { max: 100 })}${input("Опыт", "experience")}${textarea("Стиль игры", "playing_style")}${textarea("Сильные стороны", "strengths")}</fieldset><fieldset><legend>Психологический паттерн</legend>${textarea("Типичная реакция под давлением", "mental_pattern")}<p class="form-note">Устойчивая особенность, а не сегодняшнее настроение.</p></fieldset><fieldset><legend>Здоровье и ограничения</legend>${textarea("Постоянный медицинский контекст", "medical_context", "", false, 1000)}<p class="form-note">Используется только для безопасной дозировки нагрузки.</p></fieldset>${formError()}<button type="submit" class="primary-button">Сохранить профиль</button><p id="profile-status" role="status"></p></form>`,
  );
  const form = $("#profile-form");
  [...form.elements].forEach((field) => (field.disabled = true));
  try {
    const res = await apiFetch("/api/profile");
    if (!form.isConnected) return;
    restoreForm(form, res.profile || {});
    [...form.elements].forEach((field) => (field.disabled = false));
  } catch (e) {
    if (form.isConnected) errorIn(form, e);
  }
}
function renderSettings() {
  mount(
    "settings",
    hero("Подключение", "Ключ хранится только на этом устройстве.") +
      `<form id="settings-form" class="stack-form"><fieldset><legend>Это устройство</legend>${input("Адрес API", "url", apiUrl(), { type: "url", required: true, max: 500 })}${input("Личный API-ключ", "key", apiKey(), { type: "password", required: true, max: 500, extra: 'autocomplete="current-password"' })}<p id="settings-status" class="muted" role="status">Подключение не проверено</p></fieldset>${formError()}<button type="submit" class="primary-button">Сохранить и проверить</button></form><div class="card switch-row"><div><strong>Ночная тема</strong><p class="muted">Для матчей при искусственном свете</p></div><button type="button" class="switch" data-action="theme" role="switch" aria-label="Ночная тема" aria-checked="${document.documentElement.dataset.theme === "dark"}"></button></div><p class="card muted">Если для подключения нужен VPN, включи его перед заполнением анкеты.</p>`,
  );
}
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector("meta[name=theme-color]").content =
    theme === "dark" ? "#17170f" : "#f3efe6";
}
async function restoreActiveMatch(navigate = true) {
  try {
    const result = await apiFetch("/api/matches/active");
    state.activeBundle = result.active_match;
    if (navigate) {
      if (state.activeBundle)
        state.activeBundle.match.status === "preparing"
          ? renderPlan()
          : renderMatch();
      else renderPrep();
    }
  } catch (e) {
    if (navigate)
      mount(
        "error",
        `<div class="empty-state">${hero("Не удалось загрузить матч", e.message)}${button("Повторить", "restore")}${button("Проверить подключение", "settings", "secondary-button")}</div>`,
      );
    else throw e;
  }
}
function payloadNumbers(values) {
  const p = { ...values };
  for (const k of ["energy_level", "physical_rating", "mental_rating"])
    if (k in p) p[k] = Number(p[k]);
  if ("app_helpful" in p) p.app_helpful = p.app_helpful === "true";
  return p;
}
async function performOperation(key, path, method, payload) {
  const scope = apiUrl();
  let draft = readDraft(key) || {},
    op = draft.operation;
  const body = { ...payload, contract_version: 2 };
  if (op) {
    const status = await apiFetch(`/api/operations/${op.body.idempotency_key}`);
    if (scope !== apiUrl())
      throw new Error(
        "Подключение изменилось. Открой предыдущий сервер для проверки результата.",
      );
    const same = JSON.stringify(op.input) === JSON.stringify(body);
    if (status.status === "succeeded") {
      if (!same) {
        throw new Error(
          "Предыдущие данные уже сохранены. Открой сохранённый матч перед новой отправкой.",
        );
      }
      localStorage.removeItem(key);
      return status.result;
    }
    if (status.status === "pending")
      throw new Error(
        "Предыдущий запрос ещё выполняется. Повтори через несколько секунд.",
      );
    if (!same) op = null;
  }
  if (!op) {
    op = {
      path,
      method,
      input: body,
      body: { ...body, idempotency_key: crypto.randomUUID() },
    };
    putDraft(key, { ...draft, operation: op });
  }
  const result = await apiFetch(op.path, {
    method: op.method,
    body: JSON.stringify(op.body),
  });
  localStorage.removeItem(key);
  if (scope !== apiUrl())
    throw new Error(
      "Результат сохранён на предыдущем сервере. Открой его подключение для просмотра.",
    );
  return result;
}
async function submitForm(form, event) {
  const screen = state.screen;
  const id = form.id;
  if (state.busy.has(id)) return;
  saveDraft(form);
  const values = payloadNumbers(formValues(form));
  const finishMode = event.submitter?.value;
  state.busy.add(id);
  form.dataset.busy = "true";
  const controls = [...form.elements, ...$$(`#actions [form="${id}"]`)];
  controls.forEach((c) => (c.disabled = true));
  const error = form.querySelector(".error-message");
  if (error) error.hidden = true;
  const submitting = event.submitter,
    original = submitting?.textContent;
  if (submitting) submitting.textContent = "Сохраняю…";
  try {
    if (id === "prep-form") {
      if (!values.energy_level) throw new Error("Выбери энергию");
      const matchId = form.dataset.matchId;
      const result = await performOperation(
        form.dataset.draft,
        matchId ? `/api/matches/${matchId}/prep` : "/api/matches/prep",
        matchId ? "PUT" : "POST",
        {
          ...values,
          ...(matchId ? { revision: Number(form.dataset.revision) } : {}),
        },
      );
      state.activeBundle = result;
      state.history.loaded = false;
      if (state.screen === screen) renderPlan();
      else showToast("План сохранён");
    }
    if (id === "observation-form") {
      if (
        !values.own_issues?.length &&
        !values.opponent_actions?.length &&
        !values.comment?.trim()
      )
        throw new Error("Отметь хотя бы одно наблюдение");
      if (
        state.flow === "new_set"
          ? !values.completed_set_result || !values.energy_level
          : !values.score_state || !values.set_stage
      )
        throw new Error(
          state.flow === "new_set"
            ? "Выбери результат сета и запас сил"
            : "Выбери положение в сете и стадию",
        );
      const result = await performOperation(
        form.dataset.draft,
        `/api/matches/${state.activeBundle.match.id}/events`,
        "POST",
        {
          ...values,
          event_type: state.flow,
          own_issues: values.own_issues || [],
          opponent_actions: values.opponent_actions || [],
        },
      );
      if (!state.activeBundle.events.some((e) => e.id === result.event.id))
        state.activeBundle.events.push(result.event);
      state.advice = result.event;
      if (state.screen === screen) renderAdvice();
      else showToast("Совет готов — открой матч");
    }
    if (id === "finish-form") {
      if (finishProblem()) throw new Error(finishProblem());
      const matchId = state.activeBundle.match.id;
      const result = await performOperation(
        draftKey("finish", matchId),
        `/api/matches/${matchId}/finish`,
        "POST",
        { final_score: finishLine() },
      );
      state.detail = { ...state.activeBundle, match: result.match };
      state.activeBundle = null;
      state.history.loaded = false;
      if (state.screen === screen) {
        if (finishMode === "review") renderReview(matchId);
        else renderDetails("history");
      } else showToast("Результат сохранён");
    }
    if (id === "review-form") {
      if (!values.physical_rating || !values.mental_rating)
        throw new Error("Поставь обе оценки");
      if (typeof values.app_helpful !== "boolean")
        throw new Error("Ответь, помогло ли приложение");
      if (
        ![
          "own_errors",
          "emotional_state",
          "opponent_style_note",
          "opponent_what_worked",
          "opponent_errors",
        ].some((k) => values[k]?.trim())
      )
        throw new Error("Добавь хотя бы одно наблюдение словами");
      const matchId = state.reviewId;
      await performOperation(
        form.dataset.draft,
        `/api/matches/${matchId}/review`,
        "POST",
        { ...values, opponent_styles: values.opponent_styles || [] },
      );
      state.history.loaded = false;
      if (state.screen === screen) await openDetail(matchId);
      else showToast("Разбор сохранён");
    }
    if (id === "profile-form") {
      await apiFetch("/api/profile", {
        method: "PUT",
        body: JSON.stringify(values),
      });
      if (form.isConnected)
        $("#profile-status").textContent = "Профиль сохранён";
    }
    if (id === "settings-form") {
      localStorage.setItem(
        "tennisCoachApiUrl",
        values.url.trim().replace(/\/$/, ""),
      );
      localStorage.setItem("tennisCoachApiKey", values.key.trim());
      state.activeBundle = null;
      state.detail = null;
      state.history.loaded = false;
      await restoreActiveMatch(false);
      if (form.isConnected)
        $("#settings-status").textContent = "Подключение работает";
    }
  } catch (e) {
    if (form.isConnected && state.screen === screen) errorIn(form, e);
    else showToast(e.message);
  } finally {
    state.busy.delete(id);
    form.dataset.busy = "false";
    controls.forEach((c) => (c.disabled = false));
    if (submitting) submitting.textContent = original;
  }
}
async function handleAction(action, el) {
  if (action === "prep") return renderPrep();
  if (action === "plan") return renderPlan();
  if (action === "edit-prep") return renderPrep(true);
  if (action === "match") return renderMatch();
  if (action === "changeover") return renderObservation("changeover");
  if (action === "new-set") return renderObservation("new_set");
  if (action === "finish") return renderFinish();
  if (action === "review") return renderReview(state.detail.match.id);
  if (action === "history") return renderHistory();
  if (action === "profile") return renderProfile();
  if (action === "settings") return renderSettings();
  if (action === "restore") return restoreActiveMatch();
  if (action === "start") {
    el.disabled = true;
    try {
      const result = await apiFetch(
        `/api/matches/${state.activeBundle.match.id}/start`,
        {
          method: "POST",
          body: JSON.stringify({
            contract_version: 2,
            revision: state.activeBundle.prep.revision || 1,
          }),
        },
      );
      state.activeBundle.match = result.match;
      state.history.loaded = false;
      if (state.screen === "plan") renderMatch();
    } catch (e) {
      const target = $("#plan-error");
      if (target) {
        target.textContent = e.message;
        target.hidden = false;
      }
    } finally {
      el.disabled = false;
    }
    return;
  }
  if (action === "resume") {
    await restoreActiveMatch();
    return;
  }
  if (action === "cancel") {
    if (
      !window.confirm(
        "Отменить этот матч? Записи сохранятся, матч перестанет быть активным.",
      )
    )
      return;
    await apiFetch(`/api/matches/${state.activeBundle.match.id}`, {
      method: "DELETE",
    });
    state.activeBundle = null;
    state.history.loaded = false;
    renderPrep();
    return;
  }
  if (action === "delete-match") {
    if (
      !window.confirm(
        "Удалить матч и все его записи из истории навсегда? Это действие нельзя отменить.",
      )
    )
      return;
    await apiFetch(`/api/matches/${state.detail.match.id}/permanent`, {
      method: "DELETE",
    });
    state.detail = null;
    state.history.loaded = false;
    renderHistory();
    return;
  }
  if (action === "detail")
    return openDetail(
      el.dataset.id,
      state.screen === "dossier" ? "dossier" : "history",
    );
  if (action === "dossier")
    return openDossier(
      el.dataset.name,
      state.screen === "dossier" ? state.dossierBack : state.screen,
    );
  if (action === "refresh-dossier") return refreshDossier();
  if (action === "more-dossier") return moreDossier();
  if (action === "pick-opponent") {
    const form = $("#prep-form");
    form.elements.opponent_name.value = el.dataset.name;
    saveDraft(form);
    $("#prep-suggestions").hidden = true;
    scheduleSearch(el.dataset.name, "prep");
    return;
  }
  if (action === "reset-draft") {
    const form = el.closest("form"),
      draft = readDraft(form.dataset.draft);
    if (draft?.operation) {
      const op = await apiFetch(
        `/api/operations/${draft.operation.body.idempotency_key}`,
      );
      if (op.status === "pending")
        throw new Error("Запрос ещё выполняется. Сначала дождись результата.");
    }
    if (!window.confirm("Сбросить незавершённую анкету на этом устройстве?"))
      return;
    localStorage.removeItem(form.dataset.draft);
    form.removeAttribute("data-draft");
    if (form.id === "prep-form") renderPrep(Boolean(state.activeBundle));
    else if (form.id === "review-form") renderReview(state.reviewId);
    else renderObservation(state.flow);
    return;
  }
  if (action === "add-set" || action === "remove-set") {
    if (action === "add-set" && state.sets.length < 5) state.sets.push([0, 0]);
    if (action === "remove-set" && state.sets.length > 1) state.sets.pop();
    drawWheels();
    saveScoreDraft();
    return;
  }
  if (action === "theme") {
    const theme =
      document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("tennisCoachTheme", theme);
    applyTheme(theme);
    el.setAttribute("aria-checked", String(theme === "dark"));
    return;
  }
  if (action === "all-time") {
    state.history.month = "";
    state.history.loaded = false;
    renderHistory();
    return;
  }
  if (action === "refresh-history") {
    state.history.loaded = false;
    return loadHistory();
  }
  if (action === "more-history") return loadHistory(true);
}
function goBack() {
  const back = state.back;
  if (back === "details") return renderDetails("history");
  if (back === "dossier") {
    shell("dossier", state.dossierBack);
    paintDossier();
    return;
  }
  if (back === "prep") return renderPrep(Boolean(state.activeBundle));
  if (back) handleAction(back, {});
}
document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-action],[data-tab],#back");
  if (!el) return;
  if (el.tagName === "A") event.preventDefault();
  Promise.resolve()
    .then(() => {
      if (el.id === "back") return goBack();
      if (el.dataset.tab) {
        const tab = el.dataset.tab;
        if (tab === "match" && state.activeBundle?.match.status === "preparing")
          return renderPlan();
        return handleAction(tab, el);
      }
      return handleAction(el.dataset.action, el);
    })
    .catch((e) => showToast(e.message));
});
document.addEventListener("submit", (event) => {
  if (!event.target.matches("form")) return;
  event.preventDefault();
  submitForm(event.target, event);
});
document.addEventListener("input", (event) => {
  saveDraft(event.target.closest("form"));
  if (event.target.id === "prep-opponent-name")
    scheduleSearch(event.target.value, "prep");
  if (event.target.id === "history-search") {
    state.history.search = event.target.value;
    scheduleSearch(event.target.value, "history");
  }
});
document.addEventListener("change", (event) => {
  saveDraft(event.target.closest("form"));
  if (event.target.id === "history-month") {
    state.history.month = event.target.value;
    state.history.loaded = false;
    renderHistory();
  }
});
window.addEventListener("pagehide", persistScreen);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") persistScreen();
});
function viewportHeight() {
  if (window.visualViewport)
    document.documentElement.style.setProperty(
      "--app-height",
      `${window.visualViewport.height}px`,
    );
}
window.visualViewport?.addEventListener("resize", viewportHeight);
viewportHeight();
function applyLinkCredentials() {
  const params = new URLSearchParams(location.search);
  const key = params.get("key"),
    url = params.get("api");
  if (key) localStorage.setItem("tennisCoachApiKey", key);
  if (url) localStorage.setItem("tennisCoachApiUrl", url);
  if (key || url) {
    params.delete("key");
    params.delete("api");
    window.history.replaceState(
      {},
      "",
      location.pathname + (params.size ? "?" + params : "") + location.hash,
    );
  }
}

async function reconcileDrafts() {
  const prefix = `tennisCoachDraft:v2:${encodeURIComponent(apiUrl())}:`;
  const keys = Object.keys(localStorage).filter((k) => k.startsWith(prefix));
  await Promise.allSettled(
    keys.map(async (key) => {
      const draft = readDraft(key);
      if (!draft?.operation) return;
      const op = await apiFetch(
        `/api/operations/${draft.operation.body.idempotency_key}`,
      );
      if (op.status !== "succeeded") return;
      const unchanged = Object.entries(draft.values || {}).every(([k, v]) =>
        Array.isArray(v)
          ? JSON.stringify(v) === JSON.stringify(draft.operation.input[k])
          : String(v) === String(draft.operation.input[k] ?? ""),
      );
      if (unchanged || key.includes(":finish:")) localStorage.removeItem(key);
      else {
        delete draft.operation;
        const newMatch = op.result?.match?.id;
        const target =
          key.endsWith(":prep:new") && newMatch
            ? draftKey("prep", newMatch)
            : key;
        putDraft(target, draft);
        if (target !== key) localStorage.removeItem(key);
      }
    }),
  );
}

async function boot() {
  applyLinkCredentials();
  applyTheme(localStorage.getItem("tennisCoachTheme") || "light");
  if ("serviceWorker" in navigator)
    navigator.serviceWorker.register("sw.js").catch(() => {});
  if (!apiKey()) renderSettings();
  else {
    mount(
      "prep",
      '<div class="spinner" aria-hidden="true"></div><p class="loading-note" role="status">Восстанавливаю матч…</p>',
    );
    await reconcileDrafts();
    await restoreActiveMatch();
  }
}
boot();
