/* coursekit runtime
 * Chapter navigation (with slide transitions), progress, responsive sidebar, theme switch,
 * copy buttons, tabs, quizzes, checklists and image zoom.
 *
 * Custom course scripts run after this file and can use `window.coursekit`:
 *   coursekit.onChapter(({ index, id, title, element }) => { ... })   // now + on every change
 *   coursekit.go('chapter-id' | index)   coursekit.next()   coursekit.prev()   coursekit.toast('Hi')
 * or listen to the `coursekit:chapterchange` / `coursekit:finish` events on document
 * (call event.preventDefault() in a `coursekit:finish` listener to skip the default
 * "course complete" toast or the redirect to `finish_url`).
 */
(function () {
  'use strict';

  var dataEl = document.getElementById('course-data');
  if (!dataEl) return;

  const root = document.documentElement;
  const course = JSON.parse(dataEl.textContent);
  const L = course.labels;
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const motionOK = () => !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const WIDE = 1100;   // ≥ WIDE: full sidebar (reader can collapse it to a rail)
  const NARROW = 760;  // ≥ NARROW: rail; below: hidden drawer

  // ---------------------------------------------------------------- storage (never throws)
  const read = (key) => { try { return localStorage.getItem(key); } catch (e) { return null; } };
  const write = (key, value) => {
    try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (e) { /* private mode */ }
  };
  const readJSON = (key, fallback) => { try { const v = read(key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; } };
  const writeJSON = (key, value) => write(key, JSON.stringify(value));
  const K = (name) => `coursekit:${course.id}:${name}`;

  const fmtMinutes = (n) => n >= 60
    ? L.hours_minutes.replace('{h}', Math.floor(n / 60)).replace('{m}', n % 60)
    : L.minutes.replace('{n}', n);

  // ---------------------------------------------------------------- theme
  const themeBtn = $('[data-theme-toggle]');
  if (themeBtn) {
    themeBtn.addEventListener('click', () => {
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      write('coursekit:theme', next);
    });
  }
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!read('coursekit:theme')) root.dataset.theme = e.matches ? 'dark' : 'light';
  });

  // ---------------------------------------------------------------- responsive sidebar
  const sidebar = $('#sidebar');
  const sidebarScroll = $('.sidebar-scroll');
  const sidebarBtn = $('[data-sidebar-toggle]');

  function navMode() {
    const w = window.innerWidth;
    if (w >= WIDE) return read('coursekit:sidebar') === 'collapsed' ? 'rail' : 'full';
    return w >= NARROW ? 'rail' : 'hidden';
  }
  function syncToggle() {
    if (!sidebarBtn) return;
    const expanded = root.dataset.nav === 'full' || root.dataset.drawer === 'open';
    sidebarBtn.setAttribute('aria-expanded', String(expanded));
    if (sidebar) sidebar.inert = root.dataset.nav === 'hidden' && !expanded;
  }
  function setDrawer(open) {
    if (open) root.dataset.drawer = 'open';
    else delete root.dataset.drawer;
    syncToggle();
  }
  function applyNav() {
    root.dataset.nav = navMode();
    if (root.dataset.nav === 'full') setDrawer(false);
    syncToggle();
  }
  if (sidebarBtn) {
    sidebarBtn.addEventListener('click', () => {
      if (window.innerWidth >= WIDE) {
        write('coursekit:sidebar', root.dataset.nav === 'full' ? 'collapsed' : null);
        applyNav();
        return;
      }
      const open = root.dataset.drawer !== 'open';
      setDrawer(open);
      if (open) {
        revealActiveLink();
        const active = $('.toc-link.is-active');
        if (active) active.focus({ preventScroll: true });
      }
    });
  }
  const scrim = $('[data-scrim]');
  if (scrim) scrim.addEventListener('click', () => setDrawer(false));
  [WIDE, NARROW].forEach((w) => window.matchMedia(`(min-width: ${w}px)`).addEventListener('change', applyNav));

  // collapsible parts
  $$('.toc-part-head').forEach((btn) => {
    btn.addEventListener('click', () => {
      const list = document.getElementById(btn.getAttribute('aria-controls'));
      const open = btn.getAttribute('aria-expanded') !== 'true';
      btn.setAttribute('aria-expanded', String(open));
      if (list) list.hidden = !open;
    });
  });

  // ---------------------------------------------------------------- chapters
  const chapters = $$('.chapter');
  const links = $$('.toc-link');
  const prevBtn = $('[data-prev]');
  const nextBtn = $('[data-next]');
  const nextLabel = $('[data-next-label]');
  const nextTitle = $('[data-next-title]');
  const bar = $('[data-progress-bar]');
  const toast = $('[data-toast]');
  let current = -1;
  let done = new Set(readJSON(K('done'), []));
  let running = [];
  let swapToken = 0;

  function markDone(index) {
    done.add(course.chapters[index].id);
    writeJSON(K('done'), Array.from(done));
  }

  function keyframes(dir) {
    if (course.transition === 'fade') {
      return {
        out: [{ opacity: 1 }, { opacity: 0 }],
        in: [{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }],
        duration: 240,
      };
    }
    const far = (sign) => `translateX(calc(${sign} * (100% + 6vw)))`;
    return {
      out: [{ transform: 'none', opacity: 1 }, { transform: far(-dir), opacity: 0.25 }],
      in: [{ transform: far(dir), opacity: 0.25 }, { transform: 'none', opacity: 1 }],
      duration: 480,
    };
  }

  /* Next slides the current chapter out to the left and the new one in from the right;
     Back does the opposite. Both share one grid cell while they move. */
  function swap(from, to, dir, animate) {
    running.forEach((a) => a.finish());
    running = [];
    chapters.forEach((c) => { if (c !== from && c !== to) c.classList.remove('is-active', 'is-leaving'); });
    to.classList.remove('is-leaving');
    to.classList.add('is-active');
    if (!from || from === to) return;
    from.classList.remove('is-active');
    if (!animate || course.transition === 'none' || !motionOK() || !to.animate) {
      from.classList.remove('is-leaving');
      return;
    }
    const token = ++swapToken;
    const kf = keyframes(dir);
    const timing = { duration: kf.duration, easing: 'cubic-bezier(.22,.8,.24,1)' };
    from.classList.add('is-leaving');
    const outgoing = from.animate(kf.out, timing);
    const incoming = to.animate(kf.in, timing);
    running = [outgoing, incoming];
    const cleanup = () => {
      if (from !== chapters[current]) from.classList.remove('is-leaving');
      if (token === swapToken) running = [];
    };
    outgoing.finished.then(cleanup, cleanup);
  }

  function revealActiveLink() {
    const link = links[current];
    if (!link || !sidebarScroll) return;
    const r = link.getBoundingClientRect();
    const box = sidebarScroll.getBoundingClientRect();
    if (r.top < box.top || r.bottom > box.bottom) {
      sidebarScroll.scrollTop += r.top - box.top - box.height / 3;
    }
  }

  function update() {
    const n = chapters.length;
    const i = current;
    links.forEach((a, k) => {
      a.classList.toggle('is-active', k === i);
      a.classList.toggle('is-done', done.has(course.chapters[k].id));
      if (k === i) a.setAttribute('aria-current', 'step');
      else a.removeAttribute('aria-current');
    });
    $$('.toc-part').forEach((part) => {
      const partLinks = $$('.toc-link', part);
      const count = $('[data-part-count]', part);
      if (count) count.textContent = `${partLinks.filter((a) => a.classList.contains('is-done')).length}/${partLinks.length}`;
      const head = $('.toc-part-head', part);
      if (head && head.getAttribute('aria-expanded') === 'false' && partLinks.includes(links[i])) head.click();
    });
    if (prevBtn) {
      prevBtn.classList.toggle('is-hidden', i === 0);
      prevBtn.disabled = i === 0;
    }
    const last = i === n - 1;
    if (nextLabel) nextLabel.textContent = last ? L.finish : L.next;
    if (nextTitle) nextTitle.textContent = last ? '' : course.chapters[i + 1].title;
    if (bar) {
      bar.style.width = `${((i + 1) / n) * 100}%`;
      bar.parentElement.setAttribute('aria-valuenow', String(i + 1));
    }
    const remaining = course.chapters.slice(i).reduce((sum, c) => sum + c.duration, 0);
    $$('[data-time-left]').forEach((el) => { el.textContent = L.remaining.replace('{t}', fmtMinutes(remaining)); });
    document.title = `${course.chapters[i].title} · ${course.title}`;
    revealActiveLink();
  }

  function emit(name, detail, cancelable = false) {
    return document.dispatchEvent(new CustomEvent(name, { detail, cancelable }));
  }

  function chapterDetail(index, previous) {
    const c = course.chapters[index];
    return { index, previous, id: c.id, title: c.title, element: chapters[index] };
  }

  function go(index, { push = true, target = null, animate = true, focus = false } = {}) {
    index = Math.max(0, Math.min(chapters.length - 1, index));
    const previous = current;
    const changed = index !== previous;
    if (changed) {
      current = index;
      swap(chapters[previous], chapters[index], index > previous ? 1 : -1, animate && previous !== -1);
      update();
      write(K('last'), course.chapters[index].id);
    }
    const hash = '#' + encodeURIComponent(target ? target.id : course.chapters[index].id);
    if (location.hash !== hash) {
      if (push) history.pushState(null, '', hash);
      else history.replaceState(null, '', hash);
    }
    if (target) {
      requestAnimationFrame(() => target.scrollIntoView({ block: 'start', behavior: !changed && motionOK() ? 'smooth' : 'auto' }));
    } else if (changed && previous !== -1) {
      window.scrollTo(0, 0);
      if (focus) {
        const heading = $('.chapter-title', chapters[index]);
        if (heading) heading.focus({ preventScroll: true });
      }
    }
    if (changed) emit('coursekit:chapterchange', chapterDetail(index, previous));
  }

  let toastTimer = 0;
  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('is-visible'), 4000);
  }

  function finish() {
    markDone(current);
    update();
    // a listener can call event.preventDefault() to replace the default toast / redirect
    if (!emit('coursekit:finish', chapterDetail(current, current), true)) return;
    if (course.finishUrl) window.location.href = course.finishUrl;
    else showToast(L.course_complete);
  }

  if (prevBtn) prevBtn.addEventListener('click', () => { if (current > 0) go(current - 1); });
  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      if (current < chapters.length - 1) {
        markDone(current);
        go(current + 1);
      } else {
        finish();
      }
    });
  }

  // in-page links: chapters, headings, footnotes … all routed through go()
  function resolveHash(hash) {
    let id = (hash || '').replace(/^#/, '');
    try { id = decodeURIComponent(id); } catch (e) { /* keep raw */ }
    if (!id) return null;
    const index = course.chapters.findIndex((c) => c.id === id);
    if (index >= 0) return { index, target: null };
    const el = document.getElementById(id);
    const chapter = el && el.closest('.chapter');
    return chapter ? { index: chapters.indexOf(chapter), target: el === chapter ? null : el } : null;
  }

  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest('a[href^="#"]');
    if (!a) return;
    const r = resolveHash(a.getAttribute('href'));
    if (!r) return;
    e.preventDefault();
    const fromToc = a.classList.contains('toc-link');
    go(r.index, { target: r.target, focus: fromToc });
    if (fromToc && root.dataset.nav !== 'full') setDrawer(false);
  });

  const onHistory = () => {
    const r = resolveHash(location.hash);
    if (r) go(r.index, { push: false, target: r.target });
  };
  window.addEventListener('popstate', onHistory);
  window.addEventListener('hashchange', onHistory);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && root.dataset.drawer === 'open') {
      setDrawer(false);
      if (sidebarBtn) sidebarBtn.focus();
      return;
    }
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    if (e.target.closest && e.target.closest('input, textarea, select, [contenteditable], [role="tab"], [role="radio"], [role="checkbox"], pre, dialog')) return;
    if (e.key === 'ArrowRight' && current < chapters.length - 1) nextBtn.click();
    if (e.key === 'ArrowLeft' && current > 0) go(current - 1);
  });

  // ---------------------------------------------------------------- code copy
  function codeText(block) {
    const lines = $$('.line', block);
    if ($('.gp', block)) {
      // terminal / REPL transcript: copy only the commands (and their `\` continuation
      // lines), without prompts or output
      const kept = [];
      let inCommand = false;
      lines.forEach((l) => {
        const prompt = !!$('.gp', l);
        const continuation = inCommand && !$('.go', l) && l.textContent.trim() !== '';
        inCommand = prompt || continuation;
        if (!inCommand) return;
        const clone = l.cloneNode(true);
        $$('.gp, .go', clone).forEach((n) => n.remove());
        kept.push(clone.textContent);
      });
      return kept.join('\n');
    }
    return lines.map((l) => l.textContent).join('\n');
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      const area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
      area.remove();
      return ok;
    }
  }

  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.code-copy');
    if (!btn) return;
    if (!(await copyText(codeText(btn.closest('.code'))))) return;
    const label = $('.code-copy-text', btn);
    btn.classList.add('is-copied');
    if (label) label.textContent = L.copied;
    clearTimeout(btn._ckTimer);
    btn._ckTimer = setTimeout(() => {
      btn.classList.remove('is-copied');
      if (label) label.textContent = L.copy;
    }, 1600);
  });

  // ---------------------------------------------------------------- tabs (synced by label)
  const TAB_KEY = 'coursekit:tabs';
  const tabParts = (tabs) => ({
    buttons: $$(':scope > .tab-list > [role="tab"]', tabs),
    panels: $$(':scope > .tab-panels > .tab-panel', tabs),
  });

  function activateTab(tabs, button) {
    const { buttons, panels } = tabParts(tabs);
    buttons.forEach((b) => {
      const selected = b === button;
      b.setAttribute('aria-selected', String(selected));
      b.tabIndex = selected ? 0 : -1;
    });
    panels.forEach((p) => p.classList.toggle('is-active', p.id === button.getAttribute('aria-controls')));
  }

  function selectLabel(label, origin) {
    const before = origin ? origin.getBoundingClientRect().top : 0;
    $$('[data-tabs]').forEach((tabs) => {
      const match = tabParts(tabs).buttons.find((b) => b.dataset.label === label);
      if (match) activateTab(tabs, match);
    });
    if (origin) {
      const shift = origin.getBoundingClientRect().top - before;   // keep the clicked tab in place
      if (shift) window.scrollBy(0, shift);
    }
    const prefs = readJSON(TAB_KEY, []).filter((x) => x !== label);
    prefs.unshift(label);
    writeJSON(TAB_KEY, prefs.slice(0, 20));
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('.tab-list > [role="tab"]');
    if (b) selectLabel(b.dataset.label, b);
  });
  document.addEventListener('keydown', (e) => {
    const b = e.target.closest && e.target.closest('.tab-list > [role="tab"]');
    if (!b) return;
    const buttons = Array.from(b.parentElement.children);
    let k = buttons.indexOf(b);
    if (e.key === 'ArrowRight') k = (k + 1) % buttons.length;
    else if (e.key === 'ArrowLeft') k = (k - 1 + buttons.length) % buttons.length;
    else if (e.key === 'Home') k = 0;
    else if (e.key === 'End') k = buttons.length - 1;
    else return;
    e.preventDefault();
    buttons[k].focus();
    selectLabel(buttons[k].dataset.label, buttons[k]);
  });

  const preferred = readJSON(TAB_KEY, []);
  $$('[data-tabs]').forEach((tabs) => {
    const { buttons } = tabParts(tabs);
    const label = preferred.find((p) => buttons.some((b) => b.dataset.label === p));
    if (label) activateTab(tabs, buttons.find((b) => b.dataset.label === label));
  });

  // ---------------------------------------------------------------- quizzes
  function initQuiz(quiz) {
    const body = $(':scope > .quiz-body', quiz);
    const list = body && $(':scope > ul.contains-task-list, :scope > ol.contains-task-list', body);
    if (!list) return;
    const items = Array.from(list.children).filter((li) => li.classList.contains('task-list-item'));
    if (!items.length) return;
    const correct = items.map((li) => {
      const box = $('input[type="checkbox"]', li);
      const ok = !!(box && box.checked);
      if (box) box.remove();
      return ok;
    });
    const multi = correct.filter(Boolean).length > 1;
    quiz.classList.toggle('is-multi', multi);
    list.classList.add('quiz-options');
    list.setAttribute('role', multi ? 'group' : 'radiogroup');

    const explanation = document.createElement('div');
    explanation.className = 'quiz-explanation';
    explanation.hidden = true;
    while (list.nextSibling) explanation.appendChild(list.nextSibling);
    const hasExplanation = explanation.textContent.trim() !== '' || !!$('img, .code, svg', explanation);

    const actions = document.createElement('div');
    actions.className = 'quiz-actions';
    const feedback = document.createElement('span');
    feedback.className = 'quiz-feedback';
    feedback.setAttribute('role', 'status');
    const reveal = document.createElement('button');
    reveal.type = 'button';
    reveal.className = 'quiz-reveal';
    reveal.textContent = L.quiz_reveal;
    reveal.hidden = true;
    let checkBtn = null;
    if (multi) {
      const hint = document.createElement('p');
      hint.className = 'quiz-hint';
      hint.textContent = L.quiz_multi;
      $('.quiz-head', quiz).appendChild(hint);
      checkBtn = document.createElement('button');
      checkBtn.type = 'button';
      checkBtn.className = 'button';
      checkBtn.textContent = L.quiz_check;
      actions.appendChild(checkBtn);
    }
    actions.append(feedback, reveal);
    body.appendChild(actions);
    if (hasExplanation) body.appendChild(explanation);

    let solved = false;
    const setFeedback = (text, ok) => {
      feedback.textContent = text;
      feedback.classList.toggle('is-correct', !!text && ok);
      feedback.classList.toggle('is-wrong', !!text && !ok);
    };
    const solve = (revealed) => {
      solved = true;
      items.forEach((li, k) => {
        li.setAttribute('aria-disabled', 'true');
        li.setAttribute('aria-checked', String(correct[k]));
        li.tabIndex = -1;
        li.classList.toggle('is-correct', correct[k]);
        if (correct[k]) li.classList.remove('is-wrong');
      });
      setFeedback(revealed ? '' : L.quiz_correct, true);
      reveal.hidden = true;
      if (checkBtn) checkBtn.hidden = true;
      explanation.hidden = false;
      quiz.classList.add('is-solved');
    };
    const choose = (k) => {
      const li = items[k];
      if (solved || li.getAttribute('aria-disabled') === 'true') return;
      if (multi) {
        li.setAttribute('aria-checked', String(li.getAttribute('aria-checked') !== 'true'));
        items.forEach((x) => x.classList.remove('is-wrong'));
        setFeedback('', true);
        return;
      }
      items.forEach((x, j) => x.setAttribute('aria-checked', String(j === k)));
      if (correct[k]) {
        solve(false);
      } else {
        li.classList.add('is-wrong');
        li.setAttribute('aria-disabled', 'true');
        setFeedback(L.quiz_incorrect, false);
        reveal.hidden = false;
      }
    };
    items.forEach((li, k) => {
      li.classList.add('quiz-option');
      li.setAttribute('role', multi ? 'checkbox' : 'radio');
      li.setAttribute('aria-checked', 'false');
      li.tabIndex = 0;
      li.addEventListener('click', (e) => { if (!e.target.closest('a')) choose(k); });
      li.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(k); }
      });
    });
    if (checkBtn) {
      checkBtn.addEventListener('click', () => {
        const chosen = items.map((li) => li.getAttribute('aria-checked') === 'true');
        if (chosen.every((c, k) => c === correct[k])) { solve(false); return; }
        items.forEach((li, k) => li.classList.toggle('is-wrong', chosen[k] && !correct[k]));
        setFeedback(L.quiz_incorrect, false);
        reveal.hidden = false;
      });
    }
    reveal.addEventListener('click', () => solve(true));
  }
  $$('[data-quiz]').forEach(initQuiz);

  // ---------------------------------------------------------------- checklists (remembered)
  let checks = readJSON(K('checks'), {});
  chapters.forEach((chapter) => {
    $$('.task-list-item-checkbox', chapter).filter((cb) => !cb.closest('.quiz')).forEach((cb, k) => {
      const key = `${chapter.id}:${k}`;
      if (typeof checks[key] === 'boolean') cb.checked = checks[key];
      cb.addEventListener('change', () => {
        checks[key] = cb.checked;
        writeJSON(K('checks'), checks);
      });
    });
  });

  // ---------------------------------------------------------------- image zoom
  let lightbox = null;
  document.addEventListener('click', (e) => {
    const img = e.target.closest('.prose img');
    if (!img || img.closest('a, .quiz-option') || img.dataset.zoom === 'false') return;
    if (!lightbox) {
      lightbox = document.createElement('dialog');
      lightbox.className = 'lightbox';
      lightbox.addEventListener('click', () => lightbox.close());
      document.body.appendChild(lightbox);
    }
    const big = document.createElement('img');
    big.src = img.currentSrc || img.src;
    big.alt = img.alt;
    lightbox.replaceChildren(big);
    lightbox.setAttribute('aria-label', img.alt || L.close);
    lightbox.showModal();
  });

  // ---------------------------------------------------------------- misc
  $$('time[data-date]').forEach((t) => {
    try {
      const date = new Date(`${t.getAttribute('datetime')}T12:00:00`);
      t.textContent = new Intl.DateTimeFormat(course.lang, { dateStyle: 'long' }).format(date);
    } catch (e) { /* keep the build-time text */ }
  });

  const resetBtn = $('[data-reset-progress]');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      if (!window.confirm(L.reset_confirm)) return;
      done = new Set();
      checks = {};
      write(K('done'), null);
      write(K('checks'), null);
      $$('.task-list-item-checkbox').forEach((cb) => { cb.checked = cb.defaultChecked; });
      update();
    });
  }

  let printOpened = [];
  window.addEventListener('beforeprint', () => {
    printOpened = $$('.chapter details:not([open])');
    printOpened.forEach((d) => { d.open = true; });
  });
  window.addEventListener('afterprint', () => {
    printOpened.forEach((d) => { d.open = false; });
    printOpened = [];
  });

  // ---------------------------------------------------------------- public API & start
  window.coursekit = {
    course,
    get current() { return current; },
    go(target) {
      const i = typeof target === 'number' ? target : course.chapters.findIndex((c) => c.id === target);
      if (i >= 0) go(i);
    },
    next() { if (nextBtn) nextBtn.click(); },
    prev() { if (current > 0) go(current - 1); },
    toast: showToast,
    onChapter(fn) {
      document.addEventListener('coursekit:chapterchange', (e) => fn(e.detail));
      if (current >= 0) fn(chapterDetail(current, -1));
    },
  };

  applyNav();
  const start = resolveHash(location.hash)
    || { index: Math.max(0, course.chapters.findIndex((c) => c.id === read(K('last')))), target: null };
  go(start.index, { push: false, animate: false, target: start.target });
})();
