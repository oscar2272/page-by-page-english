document.querySelectorAll('form[enctype="multipart/form-data"]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (event.defaultPrevented || form.dataset.uploadSubmitting === 'true') return;

    form.dataset.uploadSubmitting = 'true';
    form.setAttribute('aria-busy', 'true');

    const status = document.createElement('div');
    status.className = 'upload-progress';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.innerHTML = '<span class="ai-spinner" aria-hidden="true"></span><span>사진을 올리고 저장하는 중입니다. 완료될 때까지 기다려 주세요.</span>';

    const submitter = event.submitter;
    if (submitter && submitter.form === form) {
      submitter.insertAdjacentElement('beforebegin', status);
    } else {
      form.append(status);
    }
    status.hidden = false;

    form.querySelectorAll('button[type="submit"], button:not([type])').forEach((button) => {
      button.disabled = true;
      button.setAttribute('aria-disabled', 'true');
    });
  });
});
