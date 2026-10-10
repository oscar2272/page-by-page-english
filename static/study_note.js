const canvas = document.querySelector('#note-canvas');
const form = document.querySelector('#study-note-form');
if (canvas && form) {
  const context = canvas.getContext('2d');
  const clearInput = document.querySelector('#clear-drawing');
  const dataInput = document.querySelector('#drawing-data');
  const pen = document.querySelector('#pen-tool');
  const eraser = document.querySelector('#eraser-tool');
  const undo = document.querySelector('#undo-stroke');
  const clear = document.querySelector('#clear-strokes');
  const history = [];
  let mode = 'pen';
  let active = false;
  let dirty = false;
  let textDirty = false;
  let submitting = false;
  form.querySelectorAll('textarea').forEach((field) => field.addEventListener('input', () => { textDirty = true; }));
  window.addEventListener('beforeunload', (event) => {
    if (!submitting && (dirty || textDirty || clearInput.value === '1')) { event.preventDefault(); event.returnValue = ''; }
  });
  const white = () => { context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height); };
  const remember = () => { history.push(context.getImageData(0, 0, canvas.width, canvas.height)); if (history.length > 12) history.shift(); };
  white();
  if (canvas.dataset.existing) {
    const image = new Image();
    image.onload = () => { context.drawImage(image, 0, 0, canvas.width, canvas.height); };
    image.src = canvas.dataset.existing;
  }
  const point = (event) => {
    const rect = canvas.getBoundingClientRect();
    return { x: (event.clientX - rect.left) * canvas.width / rect.width,
             y: (event.clientY - rect.top) * canvas.height / rect.height };
  };
  canvas.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 && event.pointerType === 'mouse') return;
    event.preventDefault();
    remember();
    active = true;
    canvas.setPointerCapture(event.pointerId);
    const p = point(event);
    context.beginPath();
    context.moveTo(p.x, p.y);
    context.lineTo(p.x + 0.1, p.y + 0.1);
    context.strokeStyle = mode === 'eraser' ? '#fff' : '#111';
    context.lineWidth = mode === 'eraser' ? 30 : Math.max(3, 5 * (event.pressure || 0.5));
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.stroke();
    dirty = true;
    clearInput.value = '0';
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!active) return;
    event.preventDefault();
    const p = point(event);
    context.lineTo(p.x, p.y);
    context.stroke();
  });
  const stop = () => { active = false; context.closePath(); };
  canvas.addEventListener('pointerup', stop);
  canvas.addEventListener('pointercancel', stop);
  pen.addEventListener('click', () => { mode = 'pen'; pen.setAttribute('aria-pressed', 'true'); eraser.setAttribute('aria-pressed', 'false'); });
  eraser.addEventListener('click', () => { mode = 'eraser'; eraser.setAttribute('aria-pressed', 'true'); pen.setAttribute('aria-pressed', 'false'); });
  undo.addEventListener('click', () => { if (history.length) { context.putImageData(history.pop(), 0, 0); dirty = true; clearInput.value = '0'; } });
  clear.addEventListener('click', () => { remember(); white(); dirty = false; clearInput.value = '1'; });
  form.addEventListener('submit', () => { if (dirty) dataInput.value = canvas.toDataURL('image/png'); submitting = true; });
}
