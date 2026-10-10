const packetList = document.querySelector('#packet-list');
const addPacketButton = document.querySelector('#add-packet');
const packetTemplate = document.querySelector('#packet-template');

if (packetList && addPacketButton && packetTemplate) {
  let nextIndex = 1;
  const staged = new WeakMap();

  function allPhotoCount() {
    return [...packetList.querySelectorAll('.packet-form-card')]
      .reduce((count, card) => count + (staged.get(card)?.length || 0), 0);
  }

  function syncFiles(card) {
    const input = card.querySelector('input[type="file"]');
    const transfer = new DataTransfer();
    for (const file of staged.get(card) || []) transfer.items.add(file);
    input.files = transfer.files;
  }

  function showPhotos(card) {
    const files = staged.get(card) || [];
    const list = card.querySelector('.packet-photo-list');
    card.querySelector('.packet-photo-count').textContent = files.length
      ? `${files.length}장 선택 · 아래 순서대로 저장됩니다.` : '선택한 사진이 없습니다.';
    list.replaceChildren();
    files.forEach((file, index) => {
      const row = document.createElement('li');
      row.className = 'packet-photo-row';
      const preview = document.createElement('img');
      preview.alt = `${index + 1}번째 사진 미리보기`;
      preview.loading = 'lazy';
      if (file.type.startsWith('image/')) {
        const url = URL.createObjectURL(file);
        preview.src = url;
        preview.addEventListener('load', () => URL.revokeObjectURL(url), { once: true });
        preview.addEventListener('error', () => URL.revokeObjectURL(url), { once: true });
      }
      const label = document.createElement('span');
      label.className = 'packet-photo-name';
      label.textContent = `${index + 1}쪽 · ${file.name}`;
      const actions = document.createElement('div');
      actions.className = 'packet-photo-actions';
      for (const [action, text, disabled] of [
        ['up', '↑ 순서 올리기', index === 0],
        ['down', '↓ 순서 내리기', index === files.length - 1],
        ['remove', '삭제', false],
      ]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = action === 'remove' ? 'text-button danger' : 'text-button';
        button.dataset.photoAction = action;
        button.dataset.photoIndex = String(index);
        button.textContent = text;
        button.disabled = disabled;
        actions.append(button);
      }
      row.append(preview, label, actions);
      list.append(row);
    });
  }

  function refresh(card) {
    syncFiles(card);
    showPhotos(card);
  }

  packetList.addEventListener('change', (event) => {
    const input = event.target.closest('input[type="file"]');
    if (!input) return;
    const card = input.closest('.packet-form-card');
    const chosen = [...input.files];
    const prior = staged.get(card) || [];
    if (allPhotoCount() + chosen.length > 12) {
      alert('한 번에 올릴 수 있는 사진은 전체 묶음 합계 12장입니다.');
      refresh(card);
      return;
    }
    if (chosen.some(file => file.size > 12 * 1024 * 1024)) {
      alert('사진은 한 장당 12MB 이하로 올려 주세요.');
      refresh(card);
      return;
    }
    staged.set(card, [...prior, ...chosen]);
    refresh(card);
  });

  packetList.addEventListener('click', (event) => {
    const action = event.target.closest('[data-photo-action]');
    if (action) {
      const card = action.closest('.packet-form-card');
      const files = [...(staged.get(card) || [])];
      const index = Number(action.dataset.photoIndex);
      if (action.dataset.photoAction === 'remove') files.splice(index, 1);
      if (action.dataset.photoAction === 'up' && index > 0) {
        [files[index - 1], files[index]] = [files[index], files[index - 1]];
      }
      if (action.dataset.photoAction === 'down' && index < files.length - 1) {
        [files[index + 1], files[index]] = [files[index], files[index + 1]];
      }
      staged.set(card, files);
      refresh(card);
      return;
    }
    const removeButton = event.target.closest('.remove-packet');
    if (!removeButton) return;
    removeButton.closest('.packet-form-card').remove();
    addPacketButton.disabled = false;
    packetList.querySelectorAll('.packet-form-card-head strong').forEach((heading, index) => {
      heading.textContent = `묶음 ${index + 1}`;
    });
  });

  addPacketButton.addEventListener('click', () => {
    if (packetList.children.length >= 12) return;
    const markup = packetTemplate.innerHTML
      .replaceAll('__INDEX__', String(nextIndex))
      .replaceAll('__NUMBER__', String(packetList.children.length + 1));
    packetList.insertAdjacentHTML('beforeend', markup);
    nextIndex += 1;
    if (packetList.children.length >= 12) addPacketButton.disabled = true;
    packetList.lastElementChild.querySelector('input[name^="packet_title_"]').focus();
  });
}
