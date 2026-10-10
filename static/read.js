const toggle = document.querySelector('#reader-toggle');
const sheets = document.querySelectorAll('.reader-sheet img');
if (toggle) {
  let original = false;
  toggle.addEventListener('click', () => {
    original = !original;
    sheets.forEach((image) => {
      image.src = original ? image.dataset.preview : image.dataset.reading;
    });
    toggle.textContent = original ? 'A4 읽기 화면 보기' : '촬영본 보기';
  });
}
