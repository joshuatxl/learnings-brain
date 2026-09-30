const WORKER_URL = "https://learnings-brain.joshuatxl.workers.dev";

const THINKING_PHRASES = ["Thinking…", "Recalling…", "Still thinking…", "Trying to remember…"];
const THINKING_INTERVAL_MS = 5000;

const thread = document.getElementById("thread");
const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const submitBtn = document.getElementById("submit");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Escape first, so nothing in the model's answer can inject markup -- only
// then apply a small, fixed set of markdown transforms to the safe string.
function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function inlineMarkdown(escaped) {
  return escaped
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

// Answers are plain prose, occasional bullet lists, **bold** and `code` --
// not full markdown (no links, tables, nested lists), so a small hand-rolled
// renderer covers it without pulling in a library.
function renderAnswer(text) {
  const blocks = [];
  let list = null;
  for (const raw of (text || "").split("\n")) {
    const line = raw.trim();
    const bullet = line.match(/^[-*]\s+(.+)/);
    if (bullet) {
      if (!list) blocks.push((list = []));
      list.push(`<li>${inlineMarkdown(escapeHtml(bullet[1]))}</li>`);
    } else {
      list = null;
      if (line) blocks.push(`<p>${inlineMarkdown(escapeHtml(line))}</p>`);
    }
  }
  return blocks.map((b) => (Array.isArray(b) ? `<ul>${b.join("")}</ul>` : b)).join("");
}

function renderCitations(citations) {
  const facts = citations?.facts ?? [];
  const notes = citations?.notes ?? [];
  if (!facts.length && !notes.length) return null;

  const details = el("details", "citations");
  details.appendChild(el("summary", null, `Sources (${facts.length} fact${facts.length === 1 ? "" : "s"}, ${notes.length} note${notes.length === 1 ? "" : "s"})`));

  if (facts.length) {
    const group = el("div", "cite-group");
    group.appendChild(el("h4", null, "Facts"));
    for (const f of facts) {
      group.appendChild(el("span", "chip", f.topic ? `${f.text} · ${f.topic}` : f.text));
    }
    details.appendChild(group);
  }
  if (notes.length) {
    const group = el("div", "cite-group");
    group.appendChild(el("h4", null, "Notes"));
    for (const n of notes) {
      group.appendChild(el("p", "note-line", n));
    }
    details.appendChild(group);
  }
  return details;
}

async function ask(question) {
  const turn = el("div", "turn");
  turn.appendChild(el("p", "q", question));
  const answerEl = el("div", "a pending", THINKING_PHRASES[0]);
  turn.appendChild(answerEl);
  thread.appendChild(turn);
  turn.scrollIntoView({ behavior: "smooth", block: "end" });

  input.value = "";
  input.disabled = true;
  submitBtn.disabled = true;

  let phraseIndex = 0;
  const thinkingTimer = setInterval(() => {
    phraseIndex = (phraseIndex + 1) % THINKING_PHRASES.length;
    answerEl.textContent = THINKING_PHRASES[phraseIndex];
  }, THINKING_INTERVAL_MS);

  try {
    const res = await fetch(`${WORKER_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    const data = await res.json();
    answerEl.classList.remove("pending");

    if (!res.ok) {
      answerEl.classList.add("error");
      answerEl.textContent = data.error || "Something went wrong. Please try again later.";
    } else {
      answerEl.innerHTML = renderAnswer(data.answer) || "(empty answer)";
      const cites = renderCitations(data.citations);
      if (cites) turn.appendChild(cites);
    }
  } catch (err) {
    answerEl.classList.remove("pending");
    answerEl.classList.add("error");
    answerEl.textContent = `Couldn't reach the brain: ${err.message}`;
  } finally {
    clearInterval(thinkingTimer);
    input.disabled = false;
    submitBtn.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  ask(question);
});
