(() => {
  const root = document.documentElement;
  const sections = [...document.querySelectorAll('.screen')];
  const navItems = [...document.querySelectorAll('.nav-item[data-screen]')];
  const crumb = document.getElementById('crumb-current');
  const toast = document.getElementById('toast');
  const themeToggle = document.getElementById('theme-toggle');
  const langButtons = [...document.querySelectorAll('#lang-toggle [data-lang]')];

  const params = new URLSearchParams(location.search);
  if (params.get('static') === '1') root.classList.add('static');
  const store = {
    get(key, fallback) {
      try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, value); } catch { /* file:// or private mode */ }
    }
  };

  let lang = params.get('lang') || store.get('vl-lang', 'en');
  let currentScreen = 'overview';
  let toastTimer;

  // Theme is applied before paint via the query parameter when present.
  const initialTheme = params.get('theme') || store.get('vl-theme', 'dark');
  root.dataset.theme = initialTheme === 'light' ? 'light' : 'dark';

  function titleFor(id) {
    const el = document.getElementById(id);
    if (!el) return id;
    return lang === 'zh' ? (el.dataset.titleZh || el.dataset.title || id) : (el.dataset.title || id);
  }

  function applyLanguage(next, push = true) {
    lang = next === 'zh' ? 'zh' : 'en';
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    store.set('vl-lang', lang);
    langButtons.forEach((b) => {
      const active = b.dataset.lang === lang;
      b.classList.toggle('active', active);
      b.setAttribute('aria-pressed', String(active));
    });

    document.querySelectorAll('[data-zh]').forEach((el) => {
      if (el.dataset.en === undefined) el.dataset.en = el.textContent.trim();
      el.textContent = lang === 'zh' ? el.dataset.zh : el.dataset.en;
    });

    document.querySelectorAll('[data-zh-placeholder]').forEach((el) => {
      if (el.dataset.enPlaceholder === undefined) el.dataset.enPlaceholder = el.placeholder;
      el.placeholder = lang === 'zh' ? el.dataset.zhPlaceholder : el.dataset.enPlaceholder;
    });

    updateChromeLabels();

    if (crumb) crumb.textContent = titleFor(currentScreen);
    document.title = `VeilLab · ${titleFor(currentScreen)}`;

    if (push) {
      const url = new URL(location.href);
      url.searchParams.set('lang', lang);
      try { history.replaceState(null, '', url); } catch { /* file:// */ }
    }
  }

  function applyTheme(next, push = true) {
    const theme = next === 'light' ? 'light' : 'dark';
    root.dataset.theme = theme;
    store.set('vl-theme', theme);
    if (themeToggle) themeToggle.setAttribute('aria-pressed', String(theme === 'light'));
    updateChromeLabels();
    if (push) {
      const url = new URL(location.href);
      url.searchParams.set('theme', theme);
      try { history.replaceState(null, '', url); } catch { /* file:// */ }
    }
  }

  function showScreen(id, push = true) {
    if (!document.getElementById(id)) id = 'overview';
    currentScreen = id;
    sections.forEach((s) => s.classList.toggle('active', s.id === id));
    navItems.forEach((n) => {
      const active = n.dataset.screen === id;
      n.classList.toggle('active', active);
      if (active) n.setAttribute('aria-current', 'page');
      else n.removeAttribute('aria-current');
    });
    if (crumb) crumb.textContent = titleFor(id);
    document.title = `VeilLab · ${titleFor(id)}`;
    if (push) {
      const url = new URL(location.href);
      url.searchParams.set('screen', id);
      try { history.replaceState(null, '', url); } catch { location.hash = id; }
    }
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  function notify(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 2200);
  }

  function updateChromeLabels() {
    const themeLabel = document.getElementById('theme-label');
    const langLabel = document.getElementById('lang-label');
    if (themeLabel) {
      themeLabel.textContent = root.dataset.theme === 'light'
        ? (lang === 'zh' ? '浅色' : 'Light')
        : (lang === 'zh' ? '深色' : 'Dark');
    }
    if (langLabel) langLabel.textContent = lang === 'zh' ? '中文' : 'English';
  }

  navItems.forEach((item) => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      showScreen(item.dataset.screen);
    });
  });

  document.querySelectorAll('[data-screen]').forEach((el) => {
    if (el.classList.contains('nav-item')) return;
    el.addEventListener('click', (e) => {
      e.preventDefault();
      showScreen(el.dataset.screen);
    });
  });

  langButtons.forEach((button) => {
    button.addEventListener('click', () => applyLanguage(button.dataset.lang));
  });

  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      applyTheme(root.dataset.theme === 'light' ? 'dark' : 'light');
    });
  }

  document.querySelectorAll('.tabs').forEach((tabs) => {
    tabs.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        tabs.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
      });
    });
  });

  document.querySelectorAll('[data-toast]').forEach((el) => {
    el.addEventListener('click', (e) => {
      if (el.tagName === 'A') e.preventDefault();
      notify(lang === 'zh' ? '原型交互：暂未连接后端。' : (el.dataset.toast || 'Prototype interaction.'));
    });
  });

  const backupConfirm = document.getElementById('backup-confirm');
  const confirmDeposit = document.getElementById('confirm-deposit');
  if (backupConfirm && confirmDeposit) {
    backupConfirm.addEventListener('change', () => {
      confirmDeposit.disabled = !backupConfirm.checked;
    });
  }

  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      notify(lang === 'zh' ? '命令面板：原型交互。' : 'Command palette: prototype interaction.');
    }
  });

  // Subtle ambient light follows the pointer; static screenshots use CSS defaults.
  document.addEventListener('pointermove', (e) => {
    const x = Math.max(0, Math.min(100, (e.clientX / window.innerWidth) * 100));
    const y = Math.max(0, Math.min(100, (e.clientY / window.innerHeight) * 100));
    root.style.setProperty('--glow-x', `${x}%`);
    root.style.setProperty('--glow-y', `${y}%`);
  }, { passive: true });

  applyLanguage(lang, false);
  applyTheme(root.dataset.theme, false);
  showScreen(params.get('screen') || location.hash.replace('#', '') || 'overview', false);
})();
