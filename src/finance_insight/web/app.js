const $ = (selector) => document.querySelector(selector);
const question = $("#question");
const form = $("#queryForm");
const submitButton = $("#submitButton");
const welcomeState = $("#welcomeState");
const loadingState = $("#loadingState");
const resultState = $("#resultState");
let lastAnswer = "";
let loadingTimer;

const labels = {
  financial_query: ["查询结构化财务库", "SQL Tool"],
  financial_analysis: ["执行财务计算", "Python Tool"],
  annual_report_search: ["检索年报依据", "RAG Tool"],
  chart_generation: ["生成趋势图", "Chart Tool"],
};

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[char]);
}

function renderMarkdown(text) {
  const lines = String(text || "").split(/\r?\n/);
  let html = "";
  let inList = false;
  for (const raw of lines) {
    const line = escapeHtml(raw);
    if (/^##\s+/.test(line)) {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<h2>${line.replace(/^##\s+/, "")}</h2>`;
    } else if (/^###\s+/.test(line)) {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<h3>${line.replace(/^###\s+/, "")}</h3>`;
    } else if (/^-\s+/.test(line)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${line.replace(/^-\s+/, "")}</li>`;
    } else if (/^&gt;\s+/.test(line)) {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<blockquote>${line.replace(/^&gt;\s+/, "")}</blockquote>`;
    } else if (!line.trim()) {
      if (inList) { html += "</ul>"; inList = false; }
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<p>${line}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function updateCount() {
  $("#charCount").textContent = `${question.value.length} / 2000`;
}

function setView(name) {
  welcomeState.classList.toggle("hidden", name !== "welcome");
  loadingState.classList.toggle("hidden", name !== "loading");
  resultState.classList.toggle("hidden", name !== "result");
}

function startLoadingAnimation() {
  const steps = [...document.querySelectorAll("#loadingSteps span")];
  let index = 0;
  steps.forEach((step, i) => step.classList.toggle("active", i === 0));
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    index = Math.min(index + 1, steps.length - 1);
    steps.forEach((step, i) => step.classList.toggle("active", i <= index));
  }, 900);
}

function stopLoadingAnimation() { clearInterval(loadingTimer); }

function statusText(status) {
  return ({ success: "分析成功", partial: "部分成功 / 已降级", error: "执行失败" })[status] || status;
}

function renderIntent(intent) {
  if (!intent) return '<div class="empty">未生成结构化意图</div>';
  const companies = intent.companies?.map((c) => `${c.company_name} ${c.stock_code}`).join("、") || "—";
  const fields = [
    ["公司", companies], ["年度", intent.period?.years?.join("—")],
    ["指标", intent.metrics?.join("、")], ["任务", intent.task_type],
    ["解析器", intent.parser], ["置信度", `${Math.round((intent.confidence || 0) * 100)}%`],
  ];
  return fields.map(([key, value]) => `<span class="intent-chip"><b>${escapeHtml(key)}</b>${escapeHtml(value || "—")}</span>`).join("");
}

function renderCitations(citations) {
  $("#citationCount").textContent = `${citations.length} 条来源`;
  if (!citations.length) return '<div class="empty">本次问题不需要文档检索，或未命中可用引用。</div>';
  return citations.map((item, index) => `
    <article class="citation">
      <strong>[${index + 1}] ${escapeHtml(item.source_file || "未知来源")}</strong>
      <span>${escapeHtml(item.company_name || "")} · ${escapeHtml(item.report_year || "")} 年 · 第 ${escapeHtml(item.page_number || "—")} 页 · Chunk ${escapeHtml(item.chunk_id || "—")}</span>
      ${item.snippet ? `<p>${escapeHtml(item.snippet)}</p>` : ""}
    </article>`).join("");
}

function renderEvidence(evidence) {
  const facts = evidence?.facts || [];
  const calculations = evidence?.calculations || {};
  const provenance = evidence?.provenance || {};
  $("#provenance").innerHTML = Object.entries(provenance).map(([key, value]) => `
    <div class="provenance-item"><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join("") || '<div class="empty">暂无证据摘要。</div>';
  if (!facts.length) {
    $("#facts").innerHTML = '<div class="empty">没有返回结构化事实，可能是无数据或核心查询失败。</div>';
  } else {
    const columns = [["company_name", "公司"], ["report_year", "年度"], ["metric_name", "指标"], ["metric_value", "数值"], ["normalized_unit", "单位"], ["source_page", "来源页"]];
    $("#facts").innerHTML = `<table><thead><tr>${columns.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead><tbody>${facts.map((row) => `<tr>${columns.map(([key]) => `<td>${escapeHtml(row[key] ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }
  const series = calculations.series || [];
  const anomalies = calculations.anomalies || [];
  $("#calculations").innerHTML = series.length
    ? series.map((item) => `<article class="calculation-item"><strong>${escapeHtml(item.metric_name || item.metric_code || "指标")}</strong><span>${(item.points || []).map((point) => `${escapeHtml(point.year)}年 ${Number(point.value).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${escapeHtml(point.unit || "")}`).join(" · ")}</span>${item.cagr_pct == null ? "" : `<small>CAGR ${Number(item.cagr_pct).toFixed(2)}%</small>`}</article>`).join("") + (anomalies.length ? `<div class="anomaly-note">检测到 ${anomalies.length} 个异常变化，原因解释必须回到年报引用核对。</div>` : "")
    : '<div class="empty">本次没有执行 Python 序列计算。</div>';
}

function renderExecutionContext(context) {
  const requested = context?.requested_backend || "—";
  const effective = context?.effective_backend || "—";
  const llm = context?.llm_requested
    ? (context?.llm_configured ? "LLM 汇总已请求" : "LLM 未配置，确定性模式")
    : "确定性模式";
  const fallback = context?.fallback_used ? "已发生降级" : "未发生降级";
  const items = [
    ["数据源", `${requested} → ${effective}`],
    ["汇总方式", llm],
    ["执行状态", fallback],
    ["工作流", `${context?.step_count ?? 0} 步 / 上限 ${context?.recursion_limit ?? "—"}`],
  ];
  if (context?.backend_fallback_reason) items.push(["降级原因", context.backend_fallback_reason]);
  $("#executionContext").innerHTML = items.map(([label, value]) => `
    <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join("");
}

function renderTrace(events) {
  $("#traceSummary").textContent = `${events.length} 次工具调用`;
  if (!events.length) return '<div class="empty">没有工具调用记录。</div>';
  return events.map((event, index) => {
    const [name, type] = labels[event.tool_name] || [event.tool_name, "Tool"];
    const details = Object.entries(event.details || {}).map(([key, value]) => `${key}=${value}`).join(" · ");
    const retry = event.retry_attempts > 1 ? `<span class="retry">重试 ${event.retry_attempts - 1} 次</span>` : "";
    const fallback = event.fallback_used ? " · fallback=true" : "";
    const error = event.error ? ` · error=${event.error}` : "";
    return `<div class="trace-item">
      <span class="trace-index">${String(index + 1).padStart(2, "0")}</span>
      <span class="trace-name"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(type)} · ${escapeHtml(event.status)}</small></span>
      <span class="trace-details">${escapeHtml(details + fallback + error) || "执行完成"}</span>
      <span class="trace-time">${Number(event.latency_ms || 0).toFixed(1)} ms${retry}</span>
    </div>`;
  }).join("");
}

function renderResult(data) {
  lastAnswer = data.answer || "";
  $("#statusBadge").className = `badge ${data.status}`;
  $("#statusBadge").textContent = statusText(data.status);
  $("#traceId").textContent = `Trace ${data.trace_id || "—"}`;
  $("#answer").innerHTML = renderMarkdown(data.answer || "没有生成报告。");
  renderEvidence(data.evidence_summary || {});
  renderExecutionContext(data.execution_context || {});
  $("#intent").innerHTML = renderIntent(data.intent);
  $("#citations").innerHTML = renderCitations(data.citations || []);
  $("#trace").innerHTML = renderTrace(data.tool_events || []);

  const errors = data.errors || [];
  $("#errorBanner").classList.toggle("hidden", !errors.length);
  $("#errorBanner").textContent = errors.length ? `降级 / 错误信息：${errors.join("；")}` : "";

  const charts = data.charts || [];
  $("#chartsSection").classList.toggle("hidden", !charts.length);
  $("#chartCount").textContent = `${charts.length} 张图`;
  $("#charts").innerHTML = charts.map((src, index) => `
    <figure class="chart-card"><img src="${escapeHtml(src)}" alt="财务趋势图 ${index + 1}" loading="lazy"></figure>
  `).join("");
  setView("result");
}

async function runQuery(event) {
  event.preventDefault();
  const value = question.value.trim();
  if (value.length < 2) return;
  submitButton.disabled = true;
  submitButton.querySelector("span:first-child").textContent = "分析执行中…";
  setView("loading");
  startLoadingAnimation();
  try {
    const sessionId = localStorage.getItem("financeInsightSession") || undefined;
    const response = await fetch("/v1/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: value, session_id: sessionId, use_llm: $("#useLlm").checked }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "请求失败");
    localStorage.setItem("financeInsightSession", data.session_id);
    renderResult(data);
  } catch (error) {
    renderResult({ status: "error", answer: `任务失败：${error.message}`, errors: [error.message], citations: [], charts: [], tool_events: [], execution_context: { fallback_used: true } });
  } finally {
    stopLoadingAnimation();
    submitButton.disabled = false;
    submitButton.querySelector("span:first-child").textContent = "运行分析";
  }
}

async function loadHealth() {
  const node = $("#systemState");
  try {
    const response = await fetch("/health");
    const data = await response.json();
    const ready = data.status === "ok";
    node.className = `system-state ${ready ? "ready" : "degraded"}`;
    const mode = data.demo_mode ? "SYNTHETIC DEMO" : (data.llm_configured ? "LLM READY" : "LOCAL MODE");
    node.querySelector("span:last-child").textContent = `${data.finance_backend_effective.toUpperCase()} · ${data.store_backend.toUpperCase()} · ${mode}`;
    $("#demoNotice").classList.toggle("hidden", !data.demo_mode);
    if (data.finance_backend_fallback_reason) node.title = data.finance_backend_fallback_reason;
  } catch {
    node.className = "system-state degraded";
    node.querySelector("span:last-child").textContent = "服务连接失败";
  }
}

function showEvaluation(data) {
  const node = $("#evalSummary");
  if (!data || data.status === "not_run") {
    node.textContent = "尚未运行评测；点击按钮验证意图、工具、数值、引用和图表。";
    return;
  }
  node.textContent = `${data.cases} 题 · 成功率 ${(data.task_success_rate * 100).toFixed(1)}% · 工具选择 ${(data.tool_selection_accuracy * 100).toFixed(1)}% · P95 ${data.latency_ms?.p95 || 0} ms`;
}

async function runEvaluation() {
  const button = $("#evalButton");
  button.disabled = true;
  button.textContent = "评测中…";
  $("#evalSummary").textContent = "正在运行 6 题确定性回归评测，不会消耗大模型额度。";
  try {
    const created = await (await fetch("/v1/evaluations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ use_llm: false })
    })).json();
    for (let i = 0; i < 120; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      const state = await (await fetch(`/v1/evaluations/${created.task_id}`)).json();
      if (state.status === "completed") { showEvaluation(state.result); return; }
      if (state.status === "failed") throw new Error(state.error || "评测失败");
    }
    throw new Error("评测超时");
  } catch (error) {
    $("#evalSummary").textContent = `评测失败：${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = "运行评测";
  }
}

question.addEventListener("input", updateCount);
form.addEventListener("submit", runQuery);
$("#evalButton").addEventListener("click", runEvaluation);
$("#copyButton").addEventListener("click", async () => {
  await navigator.clipboard.writeText(lastAnswer);
  $("#copyButton").textContent = "已复制";
  setTimeout(() => { $("#copyButton").textContent = "复制报告"; }, 1200);
});
document.querySelectorAll(".example").forEach((button) => button.addEventListener("click", () => {
  question.value = button.textContent.trim(); updateCount(); question.focus();
}));

updateCount();
loadHealth();
