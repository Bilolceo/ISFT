/* ISFT Core — AI tutor (pilot) paneli dars pleyeri ichida (app/tutor.py).
 * Faqat ISFT Core launch orqali (URL'da endpoint + auth — launch tokeni) ishlaydi; token bo'lmasa — hech narsa qilmaydi.
 * Javoblar faqat kurs materialidan, manba havolalari darsning tegishli bo'limiga olib boradi. Matn faqat textContent orqali (HTML yo'q).
 * «Yordam» — bilimni tekshirish bloklari yonida: maslahat (javobni aytmaydi). */
(function (W, D) {
  'use strict';
  if (W.ISFTTutor) return;
  var qs = new URLSearchParams(W.location.search), AUTH = qs.get('auth');
  if (!AUTH) return;
  var BASE = /\/xapi\/pkg\//.test(W.location.pathname) ? '/xapi/tutor/' : (function () {
    var e = qs.get('endpoint') || ''; return /^https?:\/\/[^\s]+\/xapi\/$/.test(e) ? e + 'tutor/' : null;
  })();
  if (!BASE) return;
  var NS = W.ISFTTutor = { ready: false, open: openPanel };
  var ST = null, busy = false, panel, log, ta, quota, fab;

  function el(tag, a, kids) {
    var n = D.createElement(tag);
    if (a) Object.keys(a).forEach(function (k) {
      var v = a[k]; if (v == null || v === false) return;
      if (k === 'text') n.textContent = v; else if (k === 'cls') n.className = v; else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), v); else n.setAttribute(k, v === true ? '' : v);
    });
    (kids || []).forEach(function (c) { if (c) n.appendChild(typeof c === 'string' ? D.createTextNode(c) : c); });
    return n;
  }
  function api(path, body) {
    return fetch(BASE + path, { method: body ? 'POST' : 'GET', headers: Object.assign({ Authorization: AUTH }, body ? { 'Content-Type': 'application/json' } : {}),
      body: body ? JSON.stringify(body) : undefined, credentials: 'omit', cache: 'no-store' })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { d._status = r.status; return d; }); });
  }
  function curLesson() {
    try { if (W.ISFTKurs && W.KURS && W.ISFTKurs.debug) { var i = W.ISFTKurs.debug.current(); var l = W.KURS.lessons[i]; return l ? l.id : ''; } } catch (e) { /* jim */ }
    return '';
  }
  function go(c) {
    if (W.ISFTKurs && W.KURS) {
      W.location.hash = 'lesson=' + encodeURIComponent(c.lesson) + (c.block ? '&block=' + encodeURIComponent(c.block) : '');
    } else {
      var b = D.querySelector('.nav-i[data-block="' + CSS.escape(c.block) + '"]');
      if (b) b.click();
      var s = D.querySelector('section[data-block="' + CSS.escape(c.block) + '"]');
      if (s) s.scrollIntoView({ block: 'start' });
    }
    if (W.innerWidth < 720) closePanel();
  }
  function here(c) {
    if (!ST || c.src !== ST.course_ref) return false;
    return W.KURS ? !!c.lesson : (!ST.lesson || c.lesson === ST.lesson);
  }
  function msg(cls, text) { var m = el('div', { cls: 'itu-m ' + cls }, [el('p', { text: text })]); log.appendChild(m); log.scrollTop = log.scrollHeight; return m; }

  function render(d) {
    var m = msg('itu-bot itu-' + (d.mode || 'xato'), d.answer || d.message || "Javob olinmadi");
    if (d.mode === 'maslahat') m.insertBefore(el('span', { cls: 'itu-tag', text: 'Maslahat — javob aytilmaydi' }), m.firstChild);
    if (d.cites && d.cites.length) {
      var box = el('div', { cls: 'itu-cites' }, [el('span', { cls: 'itu-sm', text: 'Manba: ' })]);
      d.cites.forEach(function (c) {
        box.appendChild(here(c) ? el('button', { type: 'button', cls: 'itu-cite', title: c.title || c.label, text: c.label, onclick: function () { go(c); } })
          : el('span', { cls: 'itu-cite off', title: 'Boshqa dars', text: c.label }));
      });
      m.appendChild(box);
    }
    if (d.log_id) {
      var acts = el('div', { cls: 'itu-acts' });
      if (d.mode === 'topilmadi' || d.mode === 'maslahat' || d.mode === 'javob') acts.appendChild(el('button', { type: 'button', cls: 'itu-lnk', text: "O'qituvchiga yuborish", onclick: function (e) {
        var b = e.currentTarget; b.disabled = true;
        api('teacher', { log_id: d.log_id }).then(function (r) { b.textContent = r.ok ? "Yuborildi ✓" : (r.message || 'Xato'); });
      } }));
      acts.appendChild(el('button', { type: 'button', cls: 'itu-lnk', text: 'Shikoyat', 'data-flag': '1', onclick: function (e) {
        var b = e.currentTarget, note = W.prompt ? W.prompt("Javobda nima noto'g'ri? (ixtiyoriy)") : '';
        if (note === null) return;
        b.disabled = true;
        api('flag', { log_id: d.log_id, note: note || '' }).then(function (r) { b.textContent = r.ok ? "Qabul qilindi ✓" : (r.message || 'Xato'); });
      } }));
      m.appendChild(acts);
    }
    if (d.remaining != null) setQuota(d.remaining);
  }
  function setQuota(n) { if (quota) quota.textContent = 'Bugun qolgan savollar: ' + n; }

  function send(question, item) {
    if (busy) return;
    if (!ST || !ST.enabled) { msg('itu-bot itu-off', (ST && ST.message) || "AI yordamchi hozir o'chirilgan."); return; }
    busy = true;
    if (question) msg('itu-me', question); else msg('itu-me', 'Yordam: shu savol bo\'yicha maslahat');
    var wait = msg('itu-bot itu-wait', 'Kurs materialidan qidirilmoqda…');
    api('ask', { question: question || '', lesson: curLesson(), item: item || '' }).then(function (d) {
      wait.remove(); render(d._status === 200 ? d : { mode: 'xato', answer: d.message || 'Xato' });
    }).catch(function () { wait.remove(); msg('itu-bot itu-xato', "Tarmoq xatosi — qayta urinib ko'ring."); })
      .then(function () { busy = false; });
  }

  function build() {
    fab = el('button', { type: 'button', cls: 'itu-fab', 'aria-haspopup': 'dialog', 'aria-label': 'AI yordamchi: savol berish', onclick: openPanel },
      [el('span', { cls: 'itu-dot', 'aria-hidden': 'true', text: '?' }), el('span', { text: 'Savol berish' })]);
    log = el('div', { cls: 'itu-log', 'aria-live': 'polite' });
    ta = el('textarea', { rows: '2', maxlength: '600', placeholder: "Dars bo'yicha savolingiz…", 'aria-label': 'Savol' });
    ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });
    function submit() { var v = ta.value.trim(); if (v.length < 3) return; ta.value = ''; send(v); }
    quota = el('p', { cls: 'itu-sm itu-q' });
    panel = el('div', { cls: 'itu-panel', role: 'dialog', 'aria-modal': 'false', 'aria-label': 'AI yordamchi', hidden: true }, [
      el('div', { cls: 'itu-h' }, [el('div', null, [el('b', { text: 'AI yordamchi' }), el('span', { cls: 'itu-pill', text: 'sinov' })]),
        el('button', { type: 'button', cls: 'itu-x', 'aria-label': 'Yopish', text: '×', onclick: closePanel })]),
      el('p', { cls: 'itu-note', text: "Javoblar faqat shu kurs materialidan olinadi va xato bo'lishi mumkin. Test savollariga javob aytilmaydi — faqat maslahat." }),
      log,
      el('form', { cls: 'itu-f', onsubmit: function (e) { e.preventDefault(); submit(); } }, [ta, el('button', { type: 'submit', cls: 'itu-send', text: 'Yuborish' })]),
      quota]);
    D.body.appendChild(fab); D.body.appendChild(panel);
    D.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) closePanel(); });
  }
  function openPanel() {
    panel.hidden = false; fab.hidden = true; D.documentElement.classList.add('itu-on');
    if (!log.childNodes.length) {
      msg('itu-bot', ST && ST.enabled ? "Salom! Dars mavzusi bo'yicha savol bering — kurs materialidan javob topib, manbasini ko'rsataman." : ((ST && ST.message) || "AI yordamchi hozir o'chirilgan."));
      (ST && ST.teacher_questions || []).filter(function (q) { return q.reply; }).slice(0, 3).forEach(function (q) {
        msg('itu-bot itu-teacher', "O'qituvchi javobi («" + String(q.question || '').slice(0, 80) + "»): " + q.reply);
      });
    }
    ta.focus();
  }
  function closePanel() { panel.hidden = true; fab.hidden = false; D.documentElement.classList.remove('itu-on'); fab.focus(); }

  function helpButtons() {
    if (!W.KURS) return;
    D.querySelectorAll('.blk[id^="b-"] .kc').forEach(function (kc) {
      if (kc.querySelector('.itu-help')) return;
      var id = kc.closest('.blk').id.slice(2);
      kc.appendChild(el('button', { type: 'button', cls: 'itu-help', 'data-item': id, onclick: function () { openPanel(); send('', id); } },
        [el('span', { 'aria-hidden': 'true', text: '?' }), ' Yordam (maslahat)']));
    });
  }

  api('status').then(function (d) {
    if (d._status !== 200) return;
    ST = d; build(); setQuota(d.remaining);
    helpButtons();
    new MutationObserver(function () { helpButtons(); }).observe(D.body, { childList: true, subtree: true });
    NS.ready = true;
  }).catch(function () { /* tutor ixtiyoriy — pleyer ishlashda davom etadi */ });
})(window, document);
