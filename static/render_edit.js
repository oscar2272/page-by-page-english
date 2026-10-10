const blocks = document.querySelector('#render-blocks');
const add = document.querySelector('#add-render-block');
const template = document.querySelector('#render-block-template');
if (blocks && add && template) {
  let nextIndex = Math.max(0, ...[...blocks.querySelectorAll('[name="block_key"]')].map(input => Number(input.value) + 1));
  add.addEventListener('click', () => {
    if (blocks.children.length >= 80) return;
    const index = nextIndex++;
    blocks.insertAdjacentHTML('beforeend', template.innerHTML.replaceAll('__INDEX__', String(index)));
    if (document.querySelector('#render-edit-form').dataset.layoutVersion === '2') {
      blocks.lastElementChild.querySelector('[name^="block_appearance_"]').closest('label').remove();
      const fields = document.createElement('fieldset');
      fields.className = 'render-layout-fields';
      fields.innerHTML = `<legend>원본 영역 구조</legend><label>영역 종류<select name="block_region_${index}"><option value="body">본문</option><option value="callout">설명 상자</option><option value="table">표</option><option value="list">목록</option></select></label><label>영역 번호<input name="block_group_${index}" type="number" min="0" value="${index}"></label><label>원본 배경색 (#RRGGBB)<input name="block_background_${index}"></label><label>글자 스타일<select name="block_text_style_${index}"><option value="normal">기본</option><option value="bold">굵게</option><option value="italic">기울임</option><option value="underline">밑줄</option></select></label><label>표 칸 (탭으로 구분)<textarea name="block_cells_${index}" rows="2"></textarea></label><label class="check-row"><input type="checkbox" name="block_border_${index}" value="1"> 테두리</label>`;
      blocks.lastElementChild.querySelector('[name^="block_text_"]').closest('label').before(fields);
    }
    blocks.lastElementChild.querySelector('textarea').focus();
  });
  blocks.addEventListener('click', event => {
    const button = event.target.closest('.remove-render-block');
    if (button) button.closest('.render-block-editor').remove();
  });
}
