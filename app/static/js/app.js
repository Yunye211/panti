/* 在线编辑器与判题交互 */
(function () {
  var editor = null;

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function currentCode() {
    if (editor) return editor.getValue();
    var ta = document.querySelector('.code-area');
    return ta ? ta.value : '';
  }

  function initEditor() {
    var ta = document.querySelector('.code-area');
    if (!ta) return;
    if (typeof CodeMirror === 'undefined') return; // CDN 不可用时退回普通 textarea
    editor = CodeMirror.fromTextArea(ta, {
      mode: 'python',
      lineNumbers: true,
      indentUnit: 4,
      tabSize: 4,
      indentWithTabs: false,
      lineWrapping: false,
      matchBrackets: true,
      extraKeys: { Tab: function (cm) { cm.replaceSelection('    '); } }
    });
    editor.setOption('viewportMargin', Infinity);
    var wrap = editor.getWrapperElement();
    wrap.style.height = '380px';
    wrap.style.borderRadius = '0 0 10px 10px';
    editor.refresh();
  }

  function esc(s) {
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderCases(cases) {
    var box = document.getElementById('result-cases');
    if (!box) return;
    if (!cases || !cases.length) { box.innerHTML = ''; return; }
    var html = cases.map(function (c) {
      return '<div class="case-item ' + (c.ok ? 'ok' : 'bad') + '">' +
        '<div class="case-item-head">' +
          '<strong>测试点 ' + c.index + '</strong>' +
          '<span class="badge badge-' + (c.ok ? 'success' : 'danger') + '">' + (c.ok ? '通过' : '未通过') + '</span>' +
          '<span class="muted small">' + c.time_ms + ' ms</span>' +
        '</div>' +
        '<div class="case-item-body">' +
          '<div><label>输入</label><pre>' + esc(c.input) + '</pre></div>' +
          '<div><label>期望输出</label><pre>' + esc(c.expected) + '</pre></div>' +
          '<div><label>实际输出</label><pre>' + esc(c.actual) + '</pre></div>' +
        '</div>' +
        (c.error ? '<div class="case-error"><pre>' + esc(c.error) + '</pre></div>' : '') +
        '</div>';
    }).join('');
    box.innerHTML = html;
  }

  function submitCode() {
    var btn = document.getElementById('btn-submit');
    if (!btn) return;
    var panel = document.getElementById('result-panel');
    var statusEl = document.getElementById('result-status');
    var summaryEl = document.getElementById('result-summary');
    var msgEl = document.getElementById('result-message');
    var spinner = document.getElementById('result-spinner');

    var code = currentCode();
    if (!code.trim()) {
      alert('请先编写代码再提交。');
      return;
    }

    if (panel) panel.classList.remove('hidden');
    if (spinner) spinner.classList.remove('hidden');
    if (statusEl) { statusEl.textContent = '判题中…'; statusEl.className = 'badge badge-muted'; }
    if (summaryEl) summaryEl.textContent = '';
    if (msgEl) msgEl.textContent = '';
    btn.disabled = true;

    fetch('/api/judge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
      body: JSON.stringify({
        code: code,
        problem_id: parseInt(btn.dataset.problem, 10),
        homework_id: btn.dataset.homework ? parseInt(btn.dataset.homework, 10) : null,
        source: btn.dataset.source || 'free',
        save: btn.dataset.save !== '0'
      })
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        btn.disabled = false;
        if (spinner) spinner.classList.add('hidden');
        if (data.error) {
          if (statusEl) { statusEl.textContent = '提交失败'; statusEl.className = 'badge badge-danger'; }
          if (msgEl) msgEl.textContent = data.error;
          return;
        }
        var cls = { AC: 'success', WA: 'warning', RE: 'danger', CE: 'danger', TLE: 'timeout' }[data.status] || 'muted';
        var label = { AC: '通过', WA: '答案错误', RE: '运行时错误', CE: '语法错误', TLE: '运行超时' }[data.status] || data.status;
        if (statusEl) { statusEl.textContent = label; statusEl.className = 'badge badge-' + cls; }
        if (summaryEl) {
          summaryEl.textContent = '通过测试点 ' + data.passed + '/' + data.total + '，耗时 ' + data.max_time_ms + ' ms';
        }
        if (msgEl) msgEl.textContent = data.message || '';
        renderCases(data.cases);
        var next = document.getElementById('next-link');
        if (data.status === 'AC' && next) {
          next.classList.add('btn-glow');
          next.scrollIntoView({ block: 'nearest' });
        }
      }).catch(function (err) {
        btn.disabled = false;
        if (spinner) spinner.classList.add('hidden');
        if (statusEl) { statusEl.textContent = '网络错误'; statusEl.className = 'badge badge-danger'; }
        if (msgEl) msgEl.textContent = String(err);
      });
  }

  function runCustom() {
    var out = document.getElementById('run-output');
    var btn = document.getElementById('btn-run');
    var input = document.getElementById('custom-input');
    if (!out || !btn) return;
    out.textContent = '运行中…';
    btn.disabled = true;
    fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
      body: JSON.stringify({ code: currentCode(), stdin: input ? input.value : '' })
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        btn.disabled = false;
        if (data.error) { out.textContent = data.error; return; }
        var text = '';
        if (data.status === 'TLE') text += '[运行超时]\n';
        if (data.stdout) text += data.stdout + '\n';
        if (data.stderr) text += '[stderr]\n' + data.stderr;
        out.textContent = text || '(无输出)';
      }).catch(function (err) {
        btn.disabled = false;
        out.textContent = '运行失败：' + err;
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initEditor();

    var btn = document.getElementById('btn-submit');
    if (btn) btn.addEventListener('click', submitCode);

    var runBtn = document.getElementById('btn-run');
    if (runBtn) runBtn.addEventListener('click', runCustom);

    var toggle = document.getElementById('btn-toggle-run');
    if (toggle) {
      toggle.addEventListener('click', function () {
        document.getElementById('run-box').classList.toggle('hidden');
      });
    }

    // 教师端：测试用例行增删
    var addBtn = document.getElementById('add-case');
    if (addBtn) {
      var list = document.getElementById('case-list');
      var template = document.getElementById('case-template');
      addBtn.addEventListener('click', function () {
        var row = template.querySelector('.case-row');
        if (!row) return;
        var node = row.cloneNode(true);
        list.appendChild(node);
        var ta = node.querySelector('textarea');
        if (ta) ta.focus();
        reindexCases();
      });
    }

    document.querySelectorAll('.flash-wrap .alert').forEach(function (el) {
      setTimeout(function () { el.style.opacity = '0'; }, 4000);
    });
  });

  function reindexCases() {
    var rows = document.querySelectorAll('#case-list .case-row');
    rows.forEach(function (row, i) {
      var idx = row.querySelector('.case-index');
      if (idx) idx.textContent = String(i + 1);
      var cb = row.querySelector('input[name="tc_sample"]');
      if (cb) cb.value = String(i);
    });
  }

  window.removeCase = function (btn) {
    var row = btn.closest('.case-row');
    if (!row) return;
    row.remove();
    reindexCases();
  };
})();
