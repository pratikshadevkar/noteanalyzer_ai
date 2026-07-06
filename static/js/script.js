let currentSessionId = null;
let activeNotesFile = null;

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

async function handlePdfUpload() {
  const pdfInput = document.getElementById('pdfInput');
  if (!pdfInput.files || pdfInput.files.length === 0) return;
  
  const file = pdfInput.files[0];
  document.getElementById('pdfName').innerText = file.name;
  document.getElementById('pdfSize').innerText = formatSize(file.size);
  document.getElementById('pdfPreview').classList.add('show');
  
  // Send data instantly to background context initialization engine
  const formData = new FormData();
  formData.append('pdf', file);
  
  showLoading("Locking Reference Document Cache...");
  try {
    const response = await fetch('/init_session', { method: 'POST', body: formData });
    const data = await response.json();
    
    if (data.error) {
      showError(data.error);
      return;
    }
    
    currentSessionId = data.session_id;
    document.getElementById('sessionStatus').innerText = "Session Token Locked";
    document.getElementById('sessionStatus').style.background = "rgba(16,185,129,0.2)";
    document.getElementById('sessionBanner').style.display = "block";
    document.getElementById('pdfZone').style.display = "none";
    
    if (data.pdf_preview) {
      const img = document.getElementById('pdfPreviewImg');
      img.src = "data:image/jpeg;base64," + data.pdf_preview;
      img.style.display = "block";
    }
    document.getElementById('pdfTextPreview').innerText = data.pdf_text_preview;
    hideLoading();
    checkButtonState();
  } catch (err) {
    showError("Network exception mapping memory cache.");
    hideLoading();
  }
}

function handleNotesSelected() {
  const notesInput = document.getElementById('notesInput');
  if (!notesInput.files || notesInput.files.length === 0) return;
  
  activeNotesFile = notesInput.files[0];
  document.getElementById('notesName').innerText = activeNotesFile.name;
  document.getElementById('notesSize').innerText = formatSize(activeNotesFile.size);
  document.getElementById('notesPreview').classList.add('show');
  checkButtonState();
}

function removeNotesFile() {
  activeNotesFile = null;
  document.getElementById('notesInput').value = "";
  document.getElementById('notesPreview').classList.remove('show');
  checkButtonState();
}

function clearSession() {
  currentSessionId = null;
  activeNotesFile = null;
  document.getElementById('pdfInput').value = "";
  document.getElementById('notesInput').value = "";
  document.getElementById('pdfPreview').classList.remove('show');
  document.getElementById('notesPreview').classList.remove('show');
  document.getElementById('pdfZone').style.display = "block";
  document.getElementById('sessionBanner').style.display = "none";
  document.getElementById('sessionStatus').innerText = "Status: No Session Uploaded";
  document.getElementById('sessionStatus').style.background = "linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(168, 85, 247, 0.15))";
  document.getElementById('results').style.display = "none";
  checkButtonState();
}

function checkButtonState() {
  const btn = document.getElementById('analyzeBtn');
  btn.disabled = !(currentSessionId && activeNotesFile);
}

async function analyzeNotes() {
  if (!currentSessionId || !activeNotesFile) return;
  
  const formData = new FormData();
  formData.append('session_id', currentSessionId);
  formData.append('notes', activeNotesFile);
  formData.append('extractionMode', document.getElementById('extractionMode').value);
  formData.append('deepMatch', document.getElementById('deepMatch').checked);
  
  showLoading("Running OCR against notes template...");
  document.getElementById('errorMsg').style.display = "none";
  
  try {
    const response = await fetch('/analyze_notes', { method: 'POST', body: formData });
    const data = await response.json();
    
    hideLoading();
    if (data.error) {
       showError(data.error);
       return;
    }
    
    renderDashboardMetrics(data);
  } catch (err) {
    showError("Analysis execution anomaly.");
    hideLoading();
  }
}

function renderDashboardMetrics(data) {
  document.getElementById('results').style.display = "block";
  document.getElementById('scoreNumber').innerText = data.composite_score + "%";
  
  const offset = 502 - (502 * data.composite_score) / 100;
  document.getElementById('scoreRingFill').style.strokeDashoffset = offset;
  
  const badge = document.getElementById('gradeBadge');
  badge.innerText = data.grade;
  badge.style.borderColor = data.grade_color;
  badge.style.color = data.grade_color;
  
  document.getElementById('scoreFeedback').innerText = data.feedback;
  document.getElementById('pdfWords').innerText = data.pdf_word_count;
  document.getElementById('notesWords').innerText = data.notes_word_count;
  document.getElementById('matchedKwCount').innerText = data.matched_keywords.length;
  
  // Update Individual Metric Sub-bars
  document.getElementById('tfidfScore').innerText = data.metrics.tfidf_similarity + "%";
  document.getElementById('tfidfBar').style.width = data.metrics.tfidf_similarity + "%";
  
  document.getElementById('kwScore').innerText = data.metrics.keyword_coverage + "%";
  document.getElementById('kwBar').style.width = data.metrics.keyword_coverage + "%";
  
  document.getElementById('topicScore').innerText = data.metrics.topic_coverage + "%";
  document.getElementById('topicBar').style.width = data.metrics.topic_coverage + "%";
  
  document.getElementById('seqScore').innerText = data.metrics.sequence_similarity + "%";
  document.getElementById('seqBar').style.width = data.metrics.sequence_similarity + "%";
  
  // Map Lists elements
  mapListContainer('matchedKwList', data.matched_keywords, 'matched');
  mapListContainer('missingKwList', data.missing_keywords, 'missing');
  
  mapTopics('coveredTopics', data.covered_topics, 'cov');
  mapTopics('uncoveredTopics', data.uncovered_topics, 'mis');
  
  if (data.notes_preview) {
    const img = document.getElementById('notesPreviewImg');
    img.src = "data:image/jpeg;base64," + data.notes_preview;
    img.style.display = "block";
  }
  document.getElementById('notesTextPreview').innerText = data.notes_text_preview;
  
  // Auto-scroll context element focus smoothly onto dashboard data output
  document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
}

function mapListContainer(id, data, style) {
  const container = document.getElementById(id);
  container.innerHTML = "";
  data.forEach(word => {
    const el = document.createElement('span');
    el.className = `kw-tag ${style}`;
    el.innerText = word;
    container.appendChild(el);
  });
}

function mapTopics(id, data, className) {
  const container = document.getElementById(id);
  container.innerHTML = "";
  data.forEach(topic => {
     const div = document.createElement('div');
     div.className = `topic-item ${className}`;
     div.innerHTML = `<span class="topic-dot">🔹</span> <span>${topic}</span>`;
     container.appendChild(div);
  });
}

function showLoading(txt) {
  document.getElementById('loadingText').innerText = txt;
  document.getElementById('loading').style.display = "block";
}
function hideLoading() { document.getElementById('loading').style.display = "none"; }
function showError(msg) {
  const err = document.getElementById('errorMsg');
  err.innerText = msg;
  err.style.display = "block";
}