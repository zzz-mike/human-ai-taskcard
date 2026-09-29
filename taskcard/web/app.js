const state = { cards: [], selected: null };

const statusLabels = {
  draft: "讨论中",
  ready: "可执行",
  in_progress: "执行中",
  waiting_approval: "等待确认",
  blocked: "已阻塞",
  completed: "已完成",
  cancelled: "已取消",
};

const escapeHtml = (value = "") =>
  String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));

const list = (items, render, empty = "暂无") =>
  items.length ? items.map(render).join("") : `<p class="muted">${empty}</p>`;

function renderList() {
  const root = document.querySelector("#card-list");
  document.querySelector("#card-count").textContent = state.cards.length;
  root.innerHTML = state.cards.map((card) => {
    const active = card.id === state.selected ? "active" : "";
    const verified = card.acceptance_criteria.filter((x) => x.status === "verified").length;
    return `<button class="task-row ${active}" data-id="${escapeHtml(card.id)}">
      <span class="row-top"><strong>${escapeHtml(card.title)}</strong><i class="dot ${card.status}"></i></span>
      <span class="row-meta">${statusLabels[card.status] || card.status} · 验收 ${verified}/${card.acceptance_criteria.length}</span>
    </button>`;
  }).join("");
  root.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => selectCard(button.dataset.id)));
}

function progress(card) {
  const total = card.pending_work.length || 1;
  const done = card.pending_work.filter((x) => x.status === "done").length;
  return Math.round(done * 100 / total);
}

function renderDetail(card) {
  const root = document.querySelector("#detail");
  root.className = "detail";
  const approvals = card.approvals.filter((x) => x.status === "pending");
  const pct = progress(card);
  root.innerHTML = `
    <div class="hero">
      <div>
        <p class="eyebrow">${escapeHtml(card.id)}</p>
        <h2>${escapeHtml(card.title)}</h2>
      </div>
      <span class="badge ${card.status}">${statusLabels[card.status] || card.status}</span>
    </div>
    <div class="progress"><span style="width:${pct}%"></span></div>
    <div class="progress-label"><span>执行进度</span><strong>${pct}%</strong></div>

    ${approvals.length ? `<section class="approval-panel"><p class="eyebrow">HUMAN CHECKPOINT</p><h3>等待你的确认</h3>${list(approvals, (a) => `<article><strong>${escapeHtml(a.action)}</strong><p>${escapeHtml(a.risk)}</p><code>${escapeHtml(a.id)}</code></article>`)}</section>` : ""}

    <div class="grid two">
      <section><p class="eyebrow">OUTCOME</p><h3>最终目的</h3><p>${escapeHtml(card.purpose)}</p></section>
      <section><p class="eyebrow">LIVE STATE</p><h3>当前情况</h3><p>${escapeHtml(card.current_state)}</p></section>
    </div>

    <section><p class="eyebrow">WORK</p><h3>尚未完成与已完成工作</h3><div class="work-list">${list(card.pending_work, (item) => `<article class="work-item ${item.status}"><span class="check">${item.status === "done" ? "✓" : item.status === "in_progress" ? "→" : "·"}</span><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.result || (item.approval_required ? "此项需要人工确认" : "尚无结果记录"))}</p></div><code>${escapeHtml(item.id)}</code></article>`)}</div></section>

    <div class="grid two">
      <section><p class="eyebrow">BOUNDARIES</p><h3>不可违反</h3>${list(card.constraints, (x) => `<p class="line">${escapeHtml(x)}</p>`)}</section>
      <section><p class="eyebrow">AUTHORITY</p><h3>人工确认边界</h3>${list(card.autonomy.requires_confirmation, (x) => `<p class="line warning">${escapeHtml(x)}</p>`)}</section>
    </div>

    <section><p class="eyebrow">ACCEPTANCE</p><h3>真实完成门槛</h3><div class="criteria">${list(card.acceptance_criteria, (item) => `<article><span class="criterion-state ${item.status}">${item.status === "verified" ? "已验证" : item.status === "failed" ? "失败" : "待验证"}</span><div><strong>${escapeHtml(item.description)}</strong><p>${item.evidence_ids.length} 条证据 · ${escapeHtml(item.id)}</p></div></article>`)}</div></section>

    <section><p class="eyebrow">EXECUTION LOG</p><h3>阶段记录</h3><div class="timeline">${list([...card.checkpoints].reverse(), (item) => `<article><time>${escapeHtml(item.at)}</time><strong>${escapeHtml(item.summary)}</strong><p>${escapeHtml(item.verified)}</p></article>`, "尚未开始执行")}</div></section>

    <section><p class="eyebrow">RESOURCES</p><h3>需要读取的真实资源</h3>${list(card.resources, (item) => `<p class="resource"><span>${escapeHtml(item.kind)}</span><strong>${escapeHtml(item.label)}</strong><code>${escapeHtml(item.locator)}</code></p>`)}</section>
  `;
}

async function selectCard(id) {
  state.selected = id;
  renderList();
  const response = await fetch(`/api/cards/${encodeURIComponent(id)}`);
  renderDetail(await response.json());
  history.replaceState(null, "", `#${encodeURIComponent(id)}`);
}

async function boot() {
  try {
    const health = await fetch("/api/health").then((r) => r.json());
    document.querySelector("#system-state").textContent = health.ok ? "本地事实源已连接" : "本地状态异常";
    state.cards = await fetch("/api/cards").then((r) => r.json());
    renderList();
    const requested = decodeURIComponent(location.hash.slice(1));
    if (state.cards.length) selectCard(state.cards.some((x) => x.id === requested) ? requested : state.cards[0].id);
  } catch (error) {
    document.querySelector("#system-state").textContent = "无法连接本地任务状态";
    document.querySelector("#detail").innerHTML = `<h2>服务不可用</h2><p>${escapeHtml(error.message)}</p>`;
  }
}

boot();

