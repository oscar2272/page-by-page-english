const blocks = document.querySelector('#render-blocks');
const add = document.querySelector('#add-render-block');
const template = document.querySelector('#render-block-template');
if (blocks && add && template) {
  let nextIndex = Math.max(0, ...[...blocks.querySelectorAll('[name="block_key"]')].map(input => Number(input.value) + 1));
  add.addEventListener('click', () => {
    if (blocks.children.length >= 80) return;
    blocks.insertAdjacentHTML('beforeend', template.innerHTML.replaceAll('__INDEX__', String(nextIndex++)));
    blocks.lastElementChild.querySelector('textarea').focus();
  });
  blocks.addEventListener('click', event => {
    const button = event.target.closest('.remove-render-block');
    if (button) button.closest('.render-block-editor').remove();
  });
}
