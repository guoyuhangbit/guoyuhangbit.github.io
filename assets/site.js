document.documentElement.classList.add('js-ready');
const menu = document.querySelector('.menu-button');
const navigation = document.querySelector('.nav');
menu?.addEventListener('click', () => {
  const expanded = menu.getAttribute('aria-expanded') !== 'true';
  menu.setAttribute('aria-expanded', String(expanded));
  menu.textContent = expanded ? '收起' : '菜单';
  navigation.classList.toggle('open', expanded);
});
navigation?.addEventListener('click', (event) => {
  if (event.target.closest('a')) {
    navigation.classList.remove('open');
    menu.setAttribute('aria-expanded', 'false');
    menu.textContent = '菜单';
  }
});
document.querySelectorAll('[data-contact]').forEach(button => {
  button.addEventListener('click', () => {
    const address = atob(button.dataset.contact);
    const result = document.getElementById(button.getAttribute('aria-controls'));
    const link = document.createElement('a');
    link.href = 'mailto:' + address;
    link.textContent = address;
    link.className = 'inline-link';
    result.replaceChildren(link);
    button.hidden = true;
    link.focus();
  });
});
