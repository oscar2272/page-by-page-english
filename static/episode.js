const episode = document.querySelector('#episode');
const stream = document.querySelector('#episode-stream');
if (episode && stream && stream.dataset.annotatable === '1') {
  const notes = new Map(JSON.parse(document.querySelector('#episode-annotations').textContent).map(note => [Number(note.id), note]));
  const panel = document.querySelector('#episode-note-panel');
  const form = document.querySelector('#episode-note-form');
  const feedback = document.querySelector('#note-feedback');
  const idInput = document.querySelector('#annotation-id');
  const body = document.querySelector('#annotation-body');
  let placing = false, dirty = false;
  const setFeedback = (message, error = false) => { feedback.textContent = message; feedback.classList.toggle('error', error); };
  const setPlacing = value => {
    placing = value;
    stream.classList.toggle('placing-note', value);
    document.querySelectorAll('#place-note,#place-note-floating').forEach(button => button.setAttribute('aria-pressed', String(value)));
  };
  const openPanel = note => {
    panel.hidden = false; episode.classList.add('note-open'); form.reset(); dirty = false;
    idInput.value = note.id || '';
    for (const field of ['photo_id', 'anchor_y', 'anchor_block', 'block_y']) {
      document.querySelector(`#annotation-${field.replaceAll('_', '-')}`).value = note[field] ?? '';
    }
    body.value = note.body || '';
    document.querySelector('#note-position').textContent = note.id ? '이 위치의 메모 수정' : '선택한 위치에 새 메모';
    document.querySelector('#delete-annotation').hidden = !note.id;
    setFeedback('');
  };
  const closePanel = () => {
    if (dirty && !confirm('저장하지 않은 메모를 버릴까요?')) return;
    panel.hidden = true; episode.classList.remove('note-open');
  };
  const renderMarkers = () => {
    stream.querySelectorAll('.episode-marker').forEach(marker => marker.remove());
    for (const note of notes.values()) {
      const segment = stream.querySelector(`[data-photo-id="${Number(note.photo_id)}"]`);
      if (!segment) continue;
      const anchor = note.anchor_block == null ? segment : segment.querySelector(`[data-block-index="${Number(note.anchor_block)}"]`) || segment;
      const marker = document.createElement('button');
      marker.type = 'button'; marker.className = 'episode-marker';
      marker.style.top = `${Number(anchor === segment ? note.anchor_y : note.block_y) / 100}%`;
      marker.textContent = '✎'; marker.title = note.body || '키보드 메모';
      marker.setAttribute('aria-label', '이 위치의 메모 열기');
      marker.addEventListener('click', event => { event.stopPropagation(); setPlacing(false); openPanel(note); });
      anchor.appendChild(marker);
    }
  };
  renderMarkers();
  document.querySelectorAll('#place-note,#place-note-floating').forEach(button => button.addEventListener('click', () => {
    document.dispatchEvent(new CustomEvent('episode:read-mode'));
    setPlacing(!placing);
  }));
  stream.addEventListener('click', event => {
    if (!placing) return;
    const segment = event.target.closest('.episode-segment');
    if (!segment) return;
    event.preventDefault(); event.stopPropagation();
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
  body.addEventListener('input', () => { dirty = true; });
  form.addEventListener('submit', async event => {
    event.preventDefault(); setFeedback('저장 중…');
    try {
      const response = await fetch(episode.dataset.saveUrl, {method: 'POST', body: new FormData(form), credentials: 'same-origin'});
      if (!response.ok) { setFeedback('저장하지 못했습니다.', true); return; }
      const saved = await response.json(); notes.set(Number(saved.id), saved);
      renderMarkers(); openPanel(saved); setFeedback('저장했습니다. ✎ 표시를 누르면 다시 볼 수 있습니다.');
    } catch { setFeedback('연결이 끊겨 저장하지 못했습니다.', true); }
  });
  document.querySelector('#delete-annotation').addEventListener('click', async () => {
    if (!idInput.value || !confirm('이 위치의 메모를 삭제할까요?')) return;
    const payload = new FormData(); payload.append('_csrf', episode.dataset.csrf);
    try {
      const response = await fetch(`/annotations/${idInput.value}/delete`, {method: 'POST', body: payload, credentials: 'same-origin'});
      if (!response.ok) { setFeedback('삭제하지 못했습니다.', true); return; }
      notes.delete(Number(idInput.value)); renderMarkers(); dirty = false; closePanel();
    } catch { setFeedback('연결이 끊겨 삭제하지 못했습니다.', true); }
  });
}
