/* dashboard 공통 알림 시스템 — alert/confirm 대체
 * 사용:
 *   notify.toast(msg, type='info')  → 우상단 토스트, 3초 후 자동 사라짐
 *   notify.modal(msg, type='error', title='')  → 모달, 사용자가 닫음
 *   notify.confirm(msg, title='')  → Promise<bool> (window.confirm 대체)
 * type: 'info' | 'success' | 'error' | 'warning'
 */
(function () {
  if (window.notify) return; // 중복 로드 가드

  var STYLE = '\
  .nf-toast-wrap{position:fixed;top:max(20px, env(safe-area-inset-top, 20px));right:max(20px, env(safe-area-inset-right, 20px));z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none;max-width:calc(100vw - 40px)}\
  .nf-toast{pointer-events:auto;min-width:240px;max-width:420px;padding:12px 16px;border-radius:8px;background:var(--surface,#fff);color:var(--text,#141413);border:1px solid var(--border,#e8e6dc);box-shadow:0 4px 16px rgba(0,0,0,.12);font-size:14px;line-height:1.45;display:flex;gap:10px;align-items:flex-start;animation:nfSlide .25s ease-out}\
  .nf-toast.nf-success{border-left:4px solid #788c5d}\
  .nf-toast.nf-error{border-left:4px solid #b34a44}\
  .nf-toast.nf-warning{border-left:4px solid #d97757}\
  .nf-toast.nf-info{border-left:4px solid #6a9bcc}\
  .nf-toast .nf-icon{flex:0 0 auto;font-weight:700;font-size:14px;line-height:1.45}\
  .nf-toast.nf-success .nf-icon{color:#788c5d}\
  .nf-toast.nf-error .nf-icon{color:#b34a44}\
  .nf-toast.nf-warning .nf-icon{color:#d97757}\
  .nf-toast.nf-info .nf-icon{color:#6a9bcc}\
  .nf-toast .nf-msg{flex:1;word-break:break-word;white-space:pre-wrap}\
  .nf-toast .nf-close{flex:0 0 auto;cursor:pointer;color:var(--text-muted,#b0aea5);background:none;border:0;font-size:16px;line-height:1;padding:0 0 0 4px}\
  .nf-toast.nf-leaving{animation:nfFade .2s ease-in forwards}\
  @keyframes nfSlide{from{transform:translateX(20px);opacity:0}to{transform:translateX(0);opacity:1}}\
  @keyframes nfFade{to{opacity:0;transform:translateX(20px)}}\
  .nf-modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998;display:flex;align-items:center;justify-content:center;padding:20px;animation:nfBackdrop .2s ease-out}\
  .nf-modal{background:var(--surface,#fff);color:var(--text,#141413);border:1px solid var(--border,#e8e6dc);border-radius:10px;max-width:480px;width:100%;box-shadow:0 12px 40px rgba(0,0,0,.25);overflow:hidden;animation:nfPop .2s ease-out}\
  .nf-modal.nf-error{border-top:4px solid #b34a44}\
  .nf-modal.nf-warning{border-top:4px solid #d97757}\
  .nf-modal.nf-info{border-top:4px solid #6a9bcc}\
  .nf-modal.nf-success{border-top:4px solid #788c5d}\
  .nf-modal .nf-head{padding:16px 20px 0;font-weight:600;font-size:15px;display:flex;gap:8px;align-items:center}\
  .nf-modal.nf-error .nf-head{color:#b34a44}\
  .nf-modal.nf-warning .nf-head{color:#d97757}\
  .nf-modal .nf-body{padding:12px 20px 4px;font-size:14px;line-height:1.55;white-space:pre-wrap;word-break:break-word;max-height:60vh;overflow:auto;user-select:text}\
  .nf-modal .nf-actions{padding:12px 20px 16px;display:flex;gap:8px;justify-content:flex-end}\
  .nf-btn{appearance:none;background:var(--surface,#fff);color:var(--text,#141413);border:1px solid var(--border,#e8e6dc);border-radius:6px;padding:8px 16px;font-size:14px;cursor:pointer;font-family:inherit}\
  .nf-btn:hover{background:var(--bg,#faf9f5)}\
  .nf-btn-primary{background:var(--accent,#d97757);color:#fff;border-color:var(--accent,#d97757)}\
  .nf-btn-primary:hover{background:var(--accent-hover,#c4623f);color:#fff}\
  @keyframes nfBackdrop{from{opacity:0}to{opacity:1}}\
  @keyframes nfPop{from{transform:scale(.95);opacity:0}to{transform:scale(1);opacity:1}}\
  @media (max-width:480px){.nf-toast-wrap{top:max(12px, env(safe-area-inset-top, 12px));right:max(12px, env(safe-area-inset-right, 12px));left:max(12px, env(safe-area-inset-left, 12px));max-width:none}.nf-toast{min-width:0;max-width:none}}\
  ';

  function injectStyle() {
    if (document.getElementById('nf-style')) return;
    var s = document.createElement('style');
    s.id = 'nf-style';
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  function ensureToastWrap() {
    var w = document.getElementById('nf-toast-wrap');
    if (w) return w;
    w = document.createElement('div');
    w.id = 'nf-toast-wrap';
    w.className = 'nf-toast-wrap';
    document.body.appendChild(w);
    return w;
  }

  var ICON = { info: 'i', success: '✓', error: '!', warning: '!' };

  function toast(msg, type) {
    injectStyle();
    type = type || 'info';
    var wrap = ensureToastWrap();
    var t = document.createElement('div');
    t.className = 'nf-toast nf-' + type;
    var icon = document.createElement('div');
    icon.className = 'nf-icon';
    icon.textContent = ICON[type] || ICON.info;
    var body = document.createElement('div');
    body.className = 'nf-msg';
    body.textContent = String(msg);
    var close = document.createElement('button');
    close.className = 'nf-close';
    close.type = 'button';
    close.setAttribute('aria-label', '닫기');
    close.textContent = '×';
    var dismiss = function () {
      if (t._gone) return;
      t._gone = true;
      t.classList.add('nf-leaving');
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 200);
    };
    close.addEventListener('click', dismiss);
    t.appendChild(icon);
    t.appendChild(body);
    t.appendChild(close);
    wrap.appendChild(t);
    var duration = type === 'error' ? 5000 : 3000;
    setTimeout(dismiss, duration);
    return { dismiss: dismiss };
  }

  function openModal(opts) {
    injectStyle();
    var type = opts.type || 'info';
    var backdrop = document.createElement('div');
    backdrop.className = 'nf-modal-backdrop';
    var modal = document.createElement('div');
    modal.className = 'nf-modal nf-' + type;

    if (opts.title) {
      var h = document.createElement('div');
      h.className = 'nf-head';
      h.textContent = opts.title;
      modal.appendChild(h);
    }
    var b = document.createElement('div');
    b.className = 'nf-body';
    b.textContent = String(opts.message || '');
    modal.appendChild(b);

    var actions = document.createElement('div');
    actions.className = 'nf-actions';
    (opts.buttons || []).forEach(function (btn) {
      var el = document.createElement('button');
      el.className = 'nf-btn' + (btn.primary ? ' nf-btn-primary' : '');
      el.type = 'button';
      el.textContent = btn.label;
      el.addEventListener('click', function () {
        if (modal._closed) return;
        modal._closed = true;
        if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
        if (typeof btn.onClick === 'function') btn.onClick();
      });
      actions.appendChild(el);
    });
    modal.appendChild(actions);
    backdrop.appendChild(modal);

    backdrop.addEventListener('click', function (e) {
      if (e.target !== backdrop) return;
      if (!opts.dismissOnBackdrop) return;
      if (modal._closed) return;
      modal._closed = true;
      if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
      if (typeof opts.onBackdrop === 'function') opts.onBackdrop();
    });

    var onKey = function (e) {
      if (e.key !== 'Escape') return;
      if (modal._closed) return;
      modal._closed = true;
      if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
      document.removeEventListener('keydown', onKey);
      if (typeof opts.onEscape === 'function') opts.onEscape();
    };
    document.addEventListener('keydown', onKey);

    document.body.appendChild(backdrop);
    var primary = modal.querySelector('.nf-btn-primary') || modal.querySelector('.nf-btn');
    if (primary) primary.focus();
  }

  function modal(msg, type, title) {
    type = type || 'error';
    var defaultTitle = title;
    if (defaultTitle === undefined) {
      defaultTitle = type === 'error' ? '오류' : (type === 'warning' ? '주의' : '');
    }
    openModal({
      type: type,
      title: defaultTitle,
      message: msg,
      buttons: [{ label: '확인', primary: true }],
      dismissOnBackdrop: false
    });
  }

  function confirm(msg, title) {
    return new Promise(function (resolve) {
      openModal({
        type: 'neutral',
        title: title || '확인',
        message: msg,
        buttons: [
          { label: '취소', onClick: function () { resolve(false); } },
          { label: '확인', primary: true, onClick: function () { resolve(true); } }
        ],
        dismissOnBackdrop: true,
        onBackdrop: function () { resolve(false); },
        onEscape: function () { resolve(false); }
      });
    });
  }

  window.notify = { toast: toast, modal: modal, confirm: confirm };
})();
