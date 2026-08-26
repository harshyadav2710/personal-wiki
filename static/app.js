const chatForm = document.querySelector('#chatForm');
const chatInput = document.querySelector('#chatInput');
const chatLog = document.querySelector('#chatLog');
const notesGrid = document.querySelector('#notesGrid');
const noteCount = document.querySelector('#noteCount');
const noteDialog = document.querySelector('#noteDialog');
const noteForm = document.querySelector('#noteForm');
const formError = document.querySelector('#formError');
const viewDialog = document.querySelector('#viewDialog');

function cleanPreview(content) {
  return content.replace(/^#{1,6}\s*/gm, '').replace(/[>*_`#-]/g, '').replace(/\s+/g, ' ').trim().slice(0, 150);
}

function markdownToHtml(markdown) {
  const escaped = markdown.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return escaped.split('\n').map((line) => {
    if (line.startsWith('### ')) return `<h4>${line.slice(4)}</h4>`;
    if (line.startsWith('## ')) return `<h3>${line.slice(3)}</h3>`;
    if (line.startsWith('# ')) return `<h3>${line.slice(2)}</h3>`;
    if (line.startsWith('* ') || line.startsWith('- ')) return `<li>${line.slice(2)}</li>`;
    return line ? `<p>${line}</p>` : '';
  }).join('').replace(/(<li>.*?<\/li>)+/g, (list) => `<ul>${list}</ul>`);
}

function addMessage(kind, text) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${kind}`;
  if (kind === 'assistant') {
    wrapper.innerHTML = `<div class="mini-avatar">R</div><div><div class="message-meta">RECALL <span>just now</span></div><p></p></div>`;
    wrapper.querySelector('p').textContent = text;
  } else {
    const body = document.createElement('div');
    body.className = 'message-body';
    body.textContent = text;
    wrapper.append(body);
  }
  chatLog.append(wrapper);
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function askWiki(message) {
  addMessage('user', message);
  try {
    const response = await fetch('/api/chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message}) });
    const data = await response.json();
    addMessage('assistant', data.answer || data.error || 'Something went wrong.');
  } catch (error) {
    addMessage('assistant', 'I could not reach the wiki server. Check that Flask is running.');
  }
}

chatForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = '';
  chatInput.style.height = 'auto';
  askWiki(message);
});

chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = `${Math.min(chatInput.scrollHeight, 100)}px`;
});

document.querySelectorAll('[data-prompt]').forEach((button) => button.addEventListener('click', () => askWiki(button.dataset.prompt)));
document.querySelector('#clearChat').addEventListener('click', () => {
  chatLog.innerHTML = '<div class="message assistant"><div class="mini-avatar">R</div><div><div class="message-meta">RECALL <span>just now</span></div><p>Conversation cleared. What should we look up?</p></div></div>';
});

function renderNotes(notes) {
  noteCount.textContent = notes.length;
  notesGrid.innerHTML = '';
  notes.forEach((note) => {
    const card = document.createElement('article');
    card.className = 'note-card';
    card.innerHTML = `<button class="note-open" type="button"><h3></h3><p></p><div class="tags"></div><span class="open-label">Open note →</span></button>`;
    card.querySelector('h3').textContent = note.title;
    card.querySelector('p').textContent = cleanPreview(note.content);
    note.tags.forEach((tag) => {
      const badge = document.createElement('span');
      badge.className = 'tag';
      badge.textContent = `#${tag}`;
      card.querySelector('.tags').append(badge);
    });
    card.querySelector('.note-open').addEventListener('click', () => {
      document.querySelector('#viewTitle').textContent = note.title;
      document.querySelector('#viewContent').innerHTML = markdownToHtml(note.content);
      const viewTags = document.querySelector('#viewTags');
      viewTags.innerHTML = '';
      note.tags.forEach((tag) => { const badge = document.createElement('span'); badge.className = 'tag'; badge.textContent = `#${tag}`; viewTags.append(badge); });
      viewDialog.showModal();
    });
    notesGrid.append(card);
  });
}

async function loadNotes() {
  const response = await fetch('/api/notes');
  const data = await response.json();
  renderNotes(data.notes);
  if (!data.postgres_connected) document.querySelector('.sync-dot').style.background = '#d99a56';
}

document.querySelectorAll('#newNoteNav, #newNoteButton').forEach((button) => button.addEventListener('click', () => { formError.textContent = ''; noteForm.reset(); noteDialog.showModal(); }));
document.querySelector('#notesNav').addEventListener('click', () => document.querySelector('#notesSection').scrollIntoView({behavior: 'smooth'}));
document.querySelector('#closeViewer').addEventListener('click', () => viewDialog.close());
noteForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = { title: document.querySelector('#noteTitle').value, content: document.querySelector('#noteContent').value, tags: document.querySelector('#noteTags').value.split(',') };
  const response = await fetch('/api/notes', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
  const data = await response.json();
  if (!response.ok) { formError.textContent = data.error; return; }
  noteDialog.close();
  await loadNotes();
});

loadNotes().catch(() => { notesGrid.innerHTML = '<p class="muted">Notes are unavailable until the server is running.</p>'; });
