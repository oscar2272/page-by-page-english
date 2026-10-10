const episode = document.querySelector('#episode');
const stream = document.querySelector('#episode-stream');
if (episode && stream && stream.dataset.annotatable === '1') {
  const notes = new Map(JSON.parse(document.querySelector('#episode-annotations').textContent).map(note => [Number(note.id), note]));
  const panel = document.querySelector('#episode-note-panel');
  const form = document.querySelector('#episode-note-form');
  const canvas = document.querySelector('#annotation-canvas');
  const ctx = canvas.getContext('2d');
  const feedback = document.querySelector('#note-feedback');
  const photoInput = document.querySelector('#annotation-photo-id');
  const anchorInput = document.querySelector('#annotation-anchor-y');
  const blockInput = document.querySelector('#annotation-anchor-block');
  const blockYInput = document.querySelector('#annotation-block-y');
  const idInput = document.querySelector('#annotation-id');
  const body = document.querySelector('#annotation-body');
  const recognized = document.querySelector('#annotation-recognized');
  const dataInput = document.querySelector('#annotation-drawing-data');
  const clearInput = document.querySelector('#annotation-clear-drawing');
  const pen = document.querySelector('#annotation-pen');
  const eraser = document.querySelector('#annotation-eraser');
  const undo = document.querySelector('#annotation-undo');
  const clear = document.querySelector('#annotation-clear');
  const history = [];
  let placing = false, drawing = false, drawingDirty = false, formDirty = false, mode = 'pen';
  const white = () => { ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); };
  const remember = () => { history.push(ctx.getImageData(0, 0, canvas.width, canvas.height)); if (history.length > 10) history.shift(); };
  const setFeedback = (message, error = false) => { feedback.textContent = message; feedback.classList.toggle('error', error); };
  const setPlacing = (value) => {
    placing = value;
    stream.classList.toggle('placing-note', value);
    document.querySelectorAll('#place-note,#place-note-floating').forEach(button => button.setAttribute('aria-pressed', String(value)));
  };
  const openPanel = (note) => {
    panel.hidden = false;
    episode.classList.add('note-open');
    form.reset();
    white();
    history.length = 0;
    drawingDirty = false;
    formDirty = false;
    clearInput.value = '0';
    dataInput.value = '';
    idInput.value = note.id || '';
    photoInput.value = note.photo_id;
    anchorInput.value = note.anchor_y;
    blockInput.value = note.anchor_block ?? '';
    blockYInput.value = note.block_y ?? '';
    body.value = note.body || '';
    recognized.value = note.recognized_text || '';
    document.querySelector('#note-position').textContent = note.id ? '이 위치의 메모 수정' : '선택한 위치에 새 메모';
    document.querySelector('#delete-annotation').hidden = !note.id;
    document.querySelector('#recognize-annotation').disabled = !note.id || !note.drawing_url || episode.dataset.aiReady !== '1';
    setFeedback('');
    if (note.drawing_url) {
      const image = new Image();
      image.onload = () => { if (String(note.id) === idInput.value) ctx.drawImage(image, 0, 0, canvas.width, canvas.height); };
      image.src = note.drawing_url + '?v=' + Date.now();
    }
  };
  const closePanel = () => {
    if (formDirty || drawingDirty || clearInput.value === '1') {
      if (!confirm('저장하지 않은 메모를 버릴까요?')) return;
    }
    panel.hidden = true;
    episode.classList.remove('note-open');
  };
  const renderMarkers = () => {
    stream.querySelectorAll('.episode-marker').forEach(marker => marker.remove());
    for (const note of notes.values()) {
      const segment = stream.querySelector(`[data-photo-id="${Number(note.photo_id)}"]`);
      if (!segment) continue;
      const anchor = note.anchor_block == null ? segment :
        segment.querySelector(`[data-block-index="${Number(note.anchor_block)}"]`) || segment;
      const marker = document.createElement('button');
      marker.type = 'button';
      marker.className = 'episode-marker';
      marker.style.top = `${Number(anchor === segment ? note.anchor_y : note.block_y) / 100}%`;
      marker.textContent = '✎';
      marker.title = note.body || note.recognized_text || '필기 메모';
      marker.setAttribute('aria-label', '이 위치의 메모 열기');
      marker.addEventListener('click', event => { event.stopPropagation(); setPlacing(false); openPanel(note); });
      anchor.appendChild(marker);
    }
  };
  renderMarkers();
  document.querySelectorAll('#place-note,#place-note-floating').forEach(button => button.addEventListener('click', () => {
    setPlacing(!placing);
    if (placing) setFeedback('회차 본문에서 메모할 위치를 누르세요.');
  }));
  stream.addEventListener('click', event => {
    if (!placing) return;
    const segment = event.target.closest('.episode-segment');
    if (!segment) return;
    event.preventDefault();
    event.stopPropagation();
    const rect = segment.getBoundingClientRect();
    const anchor = Math.max(0, Math.min(10000, Math.round((event.clientY - rect.top) / rect.height * 10000)));
    const block = event.target.closest('.episode-block');
    const blockRect = block && block.closest('.episode-segment') === segment ? block.getBoundingClientRect() : null;
    const blockY = blockRect ? Math.max(0, Math.min(10000, Math.round((event.clientY - blockRect.top) / blockRect.height * 10000))) : null;
    setPlacing(false);
    openPanel({photo_id: Number(segment.dataset.photoId), anchor_y: anchor,
      anchor_block: blockRect ? Number(block.dataset.blockIndex) : null, block_y: blockY});
    if (window.innerWidth < 850) panel.scrollIntoView({behavior: 'smooth', block: 'start'});
  }, true);
  document.querySelector('#close-note').addEventListener('click', closePanel);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') { setPlacing(false); if (!panel.hidden) closePanel(); } });
  [body, recognized].forEach(field => field.addEventListener('input', () => { formDirty = true; }));
  const point = event => { const rect = canvas.getBoundingClientRect(); return {
    x: (event.clientX - rect.left) * canvas.width / rect.width,
    y: (event.clientY - rect.top) * canvas.height / rect.height,
  }; };
  white();
  canvas.addEventListener('pointerdown', event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    event.preventDefault(); remember(); drawing = true; canvas.setPointerCapture(event.pointerId);
    const p = point(event); ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + .1, p.y + .1);
    ctx.strokeStyle = mode === 'eraser' ? '#fff' : '#111';
    ctx.lineWidth = mode === 'eraser' ? 30 : Math.max(3, 5 * (event.pressure || .5));
    ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.stroke();
    drawingDirty = true; clearInput.value = '0';
  });
  canvas.addEventListener('pointermove', event => {
    if (!drawing) return;
    event.preventDefault(); const p = point(event); ctx.lineTo(p.x, p.y); ctx.stroke();
  });
  const stop = () => { drawing = false; ctx.closePath(); };
  canvas.addEventListener('pointerup', stop);
  canvas.addEventListener('pointercancel', stop);
  pen.addEventListener('click', () => { mode = 'pen'; pen.setAttribute('aria-pressed', 'true'); eraser.setAttribute('aria-pressed', 'false'); });
  eraser.addEventListener('click', () => { mode = 'eraser'; eraser.setAttribute('aria-pressed', 'true'); pen.setAttribute('aria-pressed', 'false'); });
  undo.addEventListener('click', () => { if (history.length) { ctx.putImageData(history.pop(), 0, 0); drawingDirty = true; clearInput.value = '0'; } });
  clear.addEventListener('click', () => { remember(); white(); drawingDirty = false; clearInput.value = '1'; formDirty = true; });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (drawingDirty) dataInput.value = canvas.toDataURL('image/png');
    setFeedback('저장 중…');
    try {
      const response = await fetch(episode.dataset.saveUrl, {method: 'POST', body: new FormData(form), credentials: 'same-origin'});
      if (!response.ok) { setFeedback('저장하지 못했습니다. 메모 내용과 연결 상태를 확인해 주세요.', true); return; }
      const saved = await response.json();
      notes.set(Number(saved.id), saved);
      renderMarkers();
      openPanel(saved);
      setFeedback('저장했습니다. 이 위치의 ✎ 표시를 누르면 다시 볼 수 있습니다.');
    } catch { setFeedback('연결이 끊겨 저장하지 못했습니다. 다시 시도해 주세요.', true); }
  });
  document.querySelector('#recognize-annotation').addEventListener('click', async () => {
    if (drawingDirty || formDirty) { setFeedback('먼저 현재 메모를 저장해 주세요.', true); return; }
    if (!idInput.value) return;
    const payload = new FormData(); payload.append('_csrf', episode.dataset.csrf);
    setFeedback('필기를 읽는 중…');
    try {
      const response = await fetch(`/annotations/${idInput.value}/recognize`, {method: 'POST', body: payload, credentials: 'same-origin'});
      const result = await response.json();
      if (!response.ok) { setFeedback(result.error || '필기를 읽지 못했습니다.', true); return; }
      recognized.value = result.recognized_text;
      notes.get(Number(idInput.value)).recognized_text = result.recognized_text;
      setFeedback('필기를 읽었습니다. 확인하고 필요하면 고쳐 저장해 주세요.');
    } catch { setFeedback('연결이 끊겨 필기를 읽지 못했습니다.', true); }
  });
  document.querySelector('#delete-annotation').addEventListener('click', async () => {
    if (!idInput.value || !confirm('이 위치의 메모를 삭제할까요?')) return;
    const payload = new FormData(); payload.append('_csrf', episode.dataset.csrf);
    try {
      const response = await fetch(`/annotations/${idInput.value}/delete`, {method: 'POST', body: payload, credentials: 'same-origin'});
      if (!response.ok) { setFeedback('삭제하지 못했습니다.', true); return; }
      notes.delete(Number(idInput.value)); renderMarkers(); formDirty = false; drawingDirty = false; clearInput.value = '0'; closePanel();
    } catch { setFeedback('연결이 끊겨 삭제하지 못했습니다.', true); }
  });
}
