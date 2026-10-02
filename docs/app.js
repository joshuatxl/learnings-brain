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

// A single short string (e.g. a fact chip) -- inline markdown only, and a
// leading "#"/"##" is treated as emphasis (bold), not a real heading, since
// there's no room for heading styles in a compact pill.
function renderInline(text) {
  const heading = (text || "").trim().match(/^#{1,6}\s+(.+)/);
  if (heading) return `<strong>${inlineMarkdown(escapeHtml(heading[1]))}</strong>`;
  return inlineMarkdown(escapeHtml(text || ""));
}

// Answers and note citations are plain prose, occasional bullet lists,
// "#"/"##" headings (rendered as bold, not real heading levels -- these are
// short inline answers, not documents), **bold**, and `code` -- not full
// markdown (no links, tables, nested lists), so a small hand-rolled renderer
// covers it without pulling in a library.
function renderAnswer(text) {
  const blocks = [];
  let list = null;
  let code = null; // non-null while inside a ``` fenced code block
  for (const raw of (text || "").split("\n")) {
    if (raw.trim().match(/^```/)) {
      if (code === null) {
        code = [];
        list = null;
      } else {
        blocks.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        code = null;
      }
      continue;
    }
    if (code !== null) {
      code.push(raw); // preserve indentation verbatim; never markdown-processed
      continue;
    }
    const line = raw.trim();
    const heading = line.match(/^#{1,6}\s+(.+)/);
    const bullet = line.match(/^[-*]\s+(.+)/);
    if (heading) {
      list = null;
      blocks.push(`<p><strong>${inlineMarkdown(escapeHtml(heading[1]))}</strong></p>`);
    } else if (bullet) {
      if (!list) blocks.push((list = []));
      list.push(`<li>${inlineMarkdown(escapeHtml(bullet[1]))}</li>`);
    } else {
      list = null;
      if (line) blocks.push(`<p>${inlineMarkdown(escapeHtml(line))}</p>`);
    }
  }
  if (code !== null) blocks.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`); // unclosed fence
  return blocks.map((b) => (Array.isArray(b) ? `<ul>${b.join("")}</ul>` : b)).join("");
}

// A note citation starts with a "[date · title § heading]" source tag the
// worker prepends (see brain-worker/src/index.ts matchedLines) -- rendered
// bold and in the accent blue on its own line, with the note's own text
// (still markdown-rendered) following below it.
function renderNote(n) {
  const match = (n || "").match(/^\[([^\]]+)\]\s*/);
  if (!match) return renderAnswer(n);
  const source = `<p class="cite-source">[${inlineMarkdown(escapeHtml(match[1]))}]</p>`;
  return source + renderAnswer(n.slice(match[0].length));
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
      const chip = el("span", "chip");
      chip.innerHTML = f.topic ? `${renderInline(f.text)} · ${renderInline(f.topic)}` : renderInline(f.text);
      group.appendChild(chip);
    }
    details.appendChild(group);
  }
  if (notes.length) {
    const group = el("div", "cite-group");
    group.appendChild(el("h4", null, "Notes"));
    for (const n of notes) {
      const note = el("div", "note-line");
      note.innerHTML = renderNote(n);
      group.appendChild(note);
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
