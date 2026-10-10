const inkEpisode = document.querySelector('#episode');
const inkCanvases = [...document.querySelectorAll('.episode-ink-layer')];
if (inkEpisode && inkCanvases.length) {
  const initial = JSON.parse(document.querySelector('#episode-ink-data').textContent);
  const status = document.querySelector('#ink-status');
  const review = document.querySelector('#ink-review');
  const recognized = document.querySelector('#ink-recognized');
  const states = new Map();
  let tool = 'read', active = null, currentStroke = null;
  const visibleState = () => active || [...states.values()].sort((a, b) =>
    Math.abs(a.canvas.getBoundingClientRect().top - innerHeight / 2) -
    Math.abs(b.canvas.getBoundingClientRect().top - innerHeight / 2))[0];
  const setStatus = message => { status.textContent = message; };
  const point = (event, canvas) => {
    const box = canvas.getBoundingClientRect();
    return [Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)),
      Math.max(0, Math.min(1, (event.clientY - box.top) / box.height))];
  };
  const drawStroke = (ctx, stroke, width, height) => {
    const points = stroke.points;
    if (!points.length) return;
    ctx.save();
    ctx.globalCompositeOperation = stroke.tool === 'eraser' ? 'destination-out' : 'source-over';
    ctx.lineWidth = (stroke.tool === 'eraser' ? 18 : 3) * width / 800;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#171717';
    ctx.beginPath(); ctx.moveTo(points[0][0] * width, points[0][1] * height);
    if (points.length === 1) ctx.lineTo(points[0][0] * width + .1, points[0][1] * height + .1);
    else for (const item of points.slice(1)) ctx.lineTo(item[0] * width, item[1] * height);
    ctx.stroke(); ctx.restore();
  };
  const repaint = state => {
    const canvas = state.canvas;
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(rect.width * ratio));
    const height = Math.max(1, Math.round(rect.height * ratio));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, width, height);
    for (const stroke of state.strokes) drawStroke(ctx, stroke, width, height);
  };
  const setTool = next => {
    tool = next;
    document.querySelector('#episode-stream').classList.toggle('inking', next !== 'read');
    for (const state of states.values()) state.canvas.style.pointerEvents = next === 'read' ? 'none' : 'auto';
    document.querySelector('#ink-pen').setAttribute('aria-pressed', String(next === 'pen'));
    document.querySelector('#ink-eraser').setAttribute('aria-pressed', String(next === 'eraser'));
    setStatus(next === 'read' ? '읽기 모드' : 'Pencil로 본문 위에 쓰세요. 손가락으로는 스크롤합니다.');
  };
  const save = async state => {
    const version = JSON.stringify(state.strokes);
    const payload = new FormData();
    payload.append('_csrf', inkEpisode.dataset.csrf);
    payload.append('strokes', version);
    payload.append('recognized_text', state.recognized);
    setStatus('필기 저장 중…');
    try {
      const response = await fetch(state.canvas.dataset.saveUrl, {method: 'POST', body: payload, credentials: 'same-origin'});
      if (!response.ok) throw Error('저장 실패');
      const data = await response.json();
      state.saved = version; state.recognized = data.recognized_text;
      setStatus('필기 저장됨');
    } catch { setStatus('필기 저장 실패 · 되돌리거나 다시 쓰면 재시도합니다.'); }
  };
  const queueSave = state => {
    state.pending = true;
    if (state.saving) return;
    state.saving = (async () => {
      while (state.pending) { state.pending = false; await save(state); }
      state.saving = null;
    })();
  };
  for (const canvas of inkCanvases) {
    const photoId = canvas.closest('.episode-segment').dataset.photoId;
    const data = initial[photoId] || {strokes: [], recognized_text: ''};
    const state = {canvas, strokes: data.strokes, recognized: data.recognized_text, pending: false, saving: null};
    states.set(photoId, state);
    let fingerY = null;
    canvas.addEventListener('pointerdown', event => {
      if (event.pointerType === 'touch') { fingerY = event.clientY; canvas.setPointerCapture(event.pointerId); return; }
      if (tool === 'read' || (event.pointerType === 'mouse' && event.button !== 0)) return;
      event.preventDefault(); active = state;
      currentStroke = {tool, points: [point(event, canvas)]};
      state.strokes.push(currentStroke); canvas.setPointerCapture(event.pointerId); repaint(state);
    });
    canvas.addEventListener('pointermove', event => {
      if (event.pointerType === 'touch' && fingerY !== null) {
        window.scrollBy(0, fingerY - event.clientY); fingerY = event.clientY; return;
      }
      if (!currentStroke || active !== state) return;
      event.preventDefault(); currentStroke.points.push(point(event, canvas)); repaint(state);
    });
    const finish = () => {
      fingerY = null;
      if (!currentStroke || active !== state) return;
      currentStroke = null; queueSave(state);
    };
    canvas.addEventListener('pointerup', finish);
    canvas.addEventListener('pointercancel', finish);
    const observer = new ResizeObserver(() => repaint(state)); observer.observe(canvas);
    repaint(state);
  }
  document.querySelector('#ink-pen').addEventListener('click', () => setTool('pen'));
  document.querySelector('#ink-eraser').addEventListener('click', () => setTool('eraser'));
  document.querySelector('#ink-done').addEventListener('click', () => setTool('read'));
  document.addEventListener('episode:read-mode', () => setTool('read'));
  document.querySelector('#ink-undo').addEventListener('click', () => {
    active = visibleState();
    if (!active || !active.strokes.length) return;
    active.strokes.pop(); repaint(active); queueSave(active);
  });
  document.querySelector('#ink-review-open').addEventListener('click', () => {
    active = visibleState();
    if (!active) { setStatus('먼저 필기할 쪽을 선택해 주세요.'); return; }
    review.hidden = false; recognized.value = active.recognized;
  });
  document.querySelector('#ink-review-close').addEventListener('click', () => { review.hidden = true; });
  document.querySelector('#ink-save-text').addEventListener('click', async () => {
    if (!active) return;
    active.recognized = recognized.value.trim();
    queueSave(active); review.hidden = true;
  });
  document.querySelector('#ink-recognize').addEventListener('click', async () => {
    if (!active || !active.strokes.length) return;
    if (active.saving) await active.saving;
    const canvas = document.createElement('canvas');
    const rect = active.canvas.getBoundingClientRect();
    const scale = Math.min(1800 / rect.width, 2400 / rect.height, 2);
    canvas.width = Math.round(rect.width * scale); canvas.height = Math.round(rect.height * scale);
    const ctx = canvas.getContext('2d'); ctx.fillStyle = 'white'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (const stroke of active.strokes) {
      if (stroke.tool === 'eraser') {
        ctx.strokeStyle = 'white'; ctx.lineWidth = 18 * canvas.width / 800;
        ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        const points = stroke.points; ctx.beginPath(); ctx.moveTo(points[0][0] * canvas.width, points[0][1] * canvas.height);
        for (const item of points.slice(1)) ctx.lineTo(item[0] * canvas.width, item[1] * canvas.height);
        ctx.stroke();
      } else drawStroke(ctx, stroke, canvas.width, canvas.height);
    }
    const payload = new FormData(); payload.append('_csrf', inkEpisode.dataset.csrf);
    payload.append('drawing_data', canvas.toDataURL('image/png'));
    setStatus('필기 읽는 중…');
    try {
      const response = await fetch(active.canvas.dataset.recognizeUrl, {method: 'POST', body: payload, credentials: 'same-origin'});
      const result = await response.json();
      if (!response.ok) throw Error(result.error || '읽기 실패');
      active.recognized = result.recognized_text; recognized.value = result.recognized_text;
      setStatus('필기를 읽었습니다. 내용을 확인하고 수정할 수 있습니다.');
    } catch (error) { setStatus(error.message); }
  });
  setTool('read');
}
