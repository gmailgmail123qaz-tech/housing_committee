/* main.js — Жилищный комитет */

(function () {
  'use strict';

  /* ── Mobile nav toggle ── */
  const navToggle = document.getElementById('navToggle');
  const navMenu = document.getElementById('navMenu');
  if (navToggle && navMenu) {
    navToggle.addEventListener('click', () => {
      navMenu.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', navMenu.classList.contains('open'));
    });
    /* Close on outside click */
    document.addEventListener('click', (e) => {
      if (!navToggle.contains(e.target) && !navMenu.contains(e.target)) {
        navMenu.classList.remove('open');
      }
    });
  }

  /* ── Flash message auto-dismiss ── */
  const flashes = document.querySelectorAll('.flash');
  flashes.forEach((el) => {
    setTimeout(() => {
      el.style.transition = 'opacity .5s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    }, 4000);
    const btn = el.querySelector('.flash-close');
    if (btn) btn.addEventListener('click', () => el.remove());
  });

  /* ── FAQ accordion keyboard support ── */
  document.querySelectorAll('.faq-item summary').forEach((summary) => {
    summary.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        summary.click();
      }
    });
  });

  /* ── Search input: clear button ── */
  const searchInput = document.getElementById('q');
  if (searchInput && searchInput.value) {
    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'search-clear';
    clearBtn.innerHTML = '&times;';
    clearBtn.setAttribute('aria-label', 'Очистить поиск');
    searchInput.parentNode.style.position = 'relative';
    searchInput.parentNode.appendChild(clearBtn);
    clearBtn.addEventListener('click', () => {
      searchInput.value = '';
      searchInput.focus();
      clearBtn.remove();
    });
  }

  /* ── Smooth scroll for anchor links ── */
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener('click', (e) => {
      const target = document.querySelector(anchor.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  /* ── Back-to-top button ── */
  const backTop = document.getElementById('backTop');
  if (backTop) {
    window.addEventListener('scroll', () => {
      backTop.style.opacity = window.scrollY > 400 ? '1' : '0';
      backTop.style.pointerEvents = window.scrollY > 400 ? 'auto' : 'none';
    });
    backTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  }

  /* ── Character counter for textarea ── */
  document.querySelectorAll('textarea[maxlength]').forEach((ta) => {
    const max = parseInt(ta.getAttribute('maxlength'));
    const counter = document.createElement('div');
    counter.className = 'char-counter';
    counter.textContent = `0 / ${max}`;
    ta.after(counter);
    ta.addEventListener('input', () => {
      counter.textContent = `${ta.value.length} / ${max}`;
      counter.style.color = ta.value.length > max * 0.9 ? '#dc2626' : '';
    });
  });

  /* ── Form: prevent double-submit ── */
  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', function () {
      const btn = form.querySelector('[type="submit"]');
      if (btn) {
        setTimeout(() => {
          btn.disabled = true;
          btn.textContent = 'Отправка…';
        }, 10);
      }
    });
  });

  /* ── Active nav highlight ── */
  const path = window.location.pathname;
  document.querySelectorAll('.nav-link').forEach((link) => {
    const href = link.getAttribute('href');
    if (href && href !== '/' && path.startsWith(href)) {
      link.classList.add('active');
    } else if (href === '/' && path === '/') {
      link.classList.add('active');
    }
  });

  /* ── Table: row click → open link ── */
  document.querySelectorAll('tr[data-href]').forEach((row) => {
    row.style.cursor = 'pointer';
    row.addEventListener('click', () => {
      window.location.href = row.dataset.href;
    });
  });

})();
