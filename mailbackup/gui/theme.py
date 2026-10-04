"""Visual design: colour tokens (light and dark) and the stylesheet.

Everything is local — no web fonts or CDNs — so the UI never makes a network request.
"""

BRAND = '#2563eb'
QUASAR_COLORS = {
    'primary': BRAND,
    'secondary': '#0ea5e9',
    'accent': '#14b8a6',
    'positive': '#12805c',
    'negative': '#c0362c',
    'warning': '#b54708',
    'info': '#475467',
}
THEME_LABELS = {'auto': 'هماهنگ با ویندوز', 'light': 'روشن', 'dark': 'تیره'}
THEME_VALUES = {'auto': None, 'light': False, 'dark': True}

FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="16" fill="#2563eb"/>'
    '<path d="M14 22a4 4 0 0 1 4-4h28a4 4 0 0 1 4 4v20a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4z" fill="none" '
    'stroke="#fff" stroke-width="4" stroke-linejoin="round"/>'
    '<path d="m16 22 16 12 16-12" fill="none" stroke="#fff" stroke-width="4" stroke-linejoin="round"/></svg>'
)

APP_CSS = r'''
:root {
  --font: "Segoe UI", Tahoma, "Noto Sans Arabic", sans-serif;
  --mono: "Cascadia Mono", Consolas, "Courier New", monospace;
  --bg: #f3f5f9;
  --surface: #ffffff;
  --surface-2: #f7f8fb;
  --border: #e4e8f0;
  --border-strong: #d0d6e2;
  --ink: #101828;
  --ink-2: #344054;
  --muted: #667085;
  --brand: #2563eb;
  --brand-ink: #1d4ed8;
  --brand-soft: #eef4ff;
  --ok: #12805c;
  --ok-soft: #e7f6ef;
  --warn: #b54708;
  --warn-soft: #fef4e6;
  --err: #c0362c;
  --err-soft: #fdecea;
  --shadow: 0 1px 2px rgba(16, 24, 40, .04), 0 1px 3px rgba(16, 24, 40, .06);
  --shadow-lg: 0 16px 40px rgba(16, 24, 40, .10);
  --radius: 14px;
}
body.body--dark {
  --bg: #0b0f17;
  --surface: #121826;
  --surface-2: #0f1520;
  --border: #232c3d;
  --border-strong: #323d52;
  --ink: #e6e9ef;
  --ink-2: #c4cad6;
  --muted: #8b95a7;
  --brand: #4f8cff;
  --brand-ink: #8db4ff;
  --brand-soft: rgba(79, 140, 255, .14);
  --ok: #3ecf8e;
  --ok-soft: rgba(62, 207, 142, .12);
  --warn: #f5a524;
  --warn-soft: rgba(245, 165, 36, .12);
  --err: #ff6b5e;
  --err-soft: rgba(255, 107, 94, .12);
  --shadow: 0 1px 2px rgba(0, 0, 0, .35);
  --shadow-lg: 0 16px 40px rgba(0, 0, 0, .45);
  --q-primary: #4f8cff;
  --q-positive: #3ecf8e;
  --q-negative: #ff6b5e;
}

html, body { direction: rtl; }
body { font-family: var(--font); color: var(--ink); background: var(--bg); font-size: 14px; -webkit-font-smoothing: antialiased; }
.nicegui-content { padding: 0 !important; gap: 0 !important; }
.ltr { direction: ltr; unicode-bidi: isolate; }
.ltr-input .q-field__native, .ltr-input input { direction: ltr; text-align: left; }
.num { font-variant-numeric: tabular-nums; }
.muted { color: var(--muted); }
.ink-2 { color: var(--ink-2); }
.text-ok { color: var(--ok); }
.text-warn { color: var(--warn); }
.text-err { color: var(--err); }
.text-brand { color: var(--brand); }

/* ---------- shell ---------- */
.app-shell { display: flex; min-height: 100vh; width: 100%; }
.sidebar {
  width: 248px; flex: none; position: sticky; top: 0; height: 100vh;
  display: flex; flex-direction: column; gap: 6px; padding: 20px 14px 16px;
  background: var(--surface); border-inline-end: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 12px; padding: 4px 8px 18px; }
.brand-mark {
  width: 40px; height: 40px; border-radius: 12px; flex: none; display: grid; place-items: center; color: #fff;
  background: linear-gradient(135deg, #2563eb, #0ea5e9); box-shadow: 0 8px 20px rgba(37, 99, 235, .28);
}
.brand-name { font-weight: 700; font-size: 15px; color: var(--ink); line-height: 1.2; }
.brand-tagline { font-size: 11.5px; color: var(--muted); }
.nav-label { font-size: 11px; font-weight: 600; color: var(--muted); padding: 6px 12px 2px; }
.nav-item.q-btn {
  width: 100%; min-height: 42px; padding: 0 12px; border-radius: 10px; color: var(--ink-2);
  font-weight: 500; font-size: 14px; letter-spacing: 0;
}
.nav-item.q-btn .q-btn__content { justify-content: flex-start; gap: 12px; flex-wrap: nowrap; }
.nav-item.q-btn .q-icon { font-size: 20px; color: var(--muted); margin: 0; }
.nav-item.q-btn:hover { background: var(--surface-2); }
.nav-item.q-btn.active { background: var(--brand-soft); color: var(--brand-ink); font-weight: 600; }
.nav-item.q-btn.active .q-icon { color: var(--brand); }
.nav-item .q-focus-helper { display: none; }
.sidebar-foot { margin-top: auto; display: flex; flex-direction: column; gap: 10px; }
.runtime {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px;
  background: var(--surface-2); border: 1px solid var(--border); font-size: 12.5px; color: var(--ink-2);
}
.runtime .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); flex: none; box-shadow: 0 0 0 3px var(--ok-soft); }
.runtime .dot.off { background: var(--border-strong); box-shadow: none; }
.foot-note { font-size: 11px; color: var(--muted); padding: 0 12px; line-height: 1.7; }

.app-main { flex: 1; min-width: 0; padding: 28px 32px 40px; }
.view { width: 100%; max-width: 1040px; margin: 0 auto; gap: 20px; }
.page-head { width: 100%; display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.page-title { font-size: 22px; font-weight: 700; color: var(--ink); line-height: 1.3; }
.page-sub { font-size: 13px; color: var(--muted); margin-top: 2px; }

/* ---------- surfaces ---------- */
.panel { width: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); }
.panel-pad { padding: 20px 22px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; }
.panel-title { font-size: 15px; font-weight: 700; color: var(--ink); }
.panel-sub { font-size: 12.5px; color: var(--muted); margin-top: 2px; line-height: 1.7; }
.q-card { background: var(--surface); color: var(--ink); }
.q-dialog__inner > .q-card { border-radius: 18px !important; box-shadow: var(--shadow-lg); }
.q-separator { background: var(--border); }

/* ---------- buttons ---------- */
.q-btn { text-transform: none; letter-spacing: 0; font-weight: 600; }
.btn { border-radius: 10px; min-height: 40px; padding: 0 16px; }
.btn-lg { min-height: 46px; padding: 0 22px; font-size: 15px; }
.btn.q-btn--unelevated.bg-primary { box-shadow: 0 6px 16px rgba(37, 99, 235, .25); }
.btn-ghost.q-btn { color: var(--ink-2); border: 1px solid var(--border-strong); background: var(--surface); }
.btn-ghost.q-btn:hover { background: var(--surface-2); }
.icon-btn.q-btn { color: var(--muted); }
.icon-btn.q-btn:hover { color: var(--ink); }
.icon-btn.danger.q-btn:hover { color: var(--err); }

/* ---------- hero ---------- */
.hero { position: relative; overflow: hidden; padding: 22px 24px; }
.hero::before {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(600px 180px at 100% 0%, var(--brand-soft), transparent 70%);
}
.hero > * { position: relative; }
.status-orb { width: 52px; height: 52px; border-radius: 16px; flex: none; display: grid; place-items: center; }
.tone-ok { background: var(--ok-soft); color: var(--ok); }
.tone-warn { background: var(--warn-soft); color: var(--warn); }
.tone-err { background: var(--err-soft); color: var(--err); }
.tone-brand { background: var(--brand-soft); color: var(--brand); }
.tone-idle { background: var(--surface-2); color: var(--muted); border: 1px solid var(--border); }
.hero-title { font-size: 20px; font-weight: 700; color: var(--ink); line-height: 1.35; }
.hero-sub { font-size: 13.5px; color: var(--ink-2); }
.dest {
  display: flex; align-items: center; gap: 10px; width: 100%; margin-top: 18px; padding-top: 14px;
  border-top: 1px dashed var(--border-strong); font-size: 12.5px; color: var(--muted);
}
.dest > .path-chip { flex: 0 1 auto; min-width: 0; }
.path-chip {
  font-family: var(--mono); font-size: 12px; color: var(--ink-2); background: var(--surface-2);
  border: 1px solid var(--border); border-radius: 8px; padding: 3px 8px; max-width: 100%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.link-btn.q-btn { color: var(--brand); font-weight: 600; min-height: 28px; padding: 0 8px; border-radius: 8px; }
.progress-wrap { width: 100%; margin-top: 18px; display: flex; flex-direction: column; gap: 8px; }
.progress-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12.5px; color: var(--ink-2); }
.progress-meta .sep { color: var(--border-strong); }
.progress-pct { margin-inline-start: auto; font-weight: 700; color: var(--brand); }
.progress-bar.q-linear-progress { border-radius: 99px; color: var(--brand); }
.progress-bar .q-linear-progress__track { background: var(--border); opacity: 1; }
.spin { animation: spin 1.2s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ---------- setup steps ---------- */
.steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; width: 100%; margin-top: 16px; }
.step { border: 1px solid var(--border); border-radius: 12px; padding: 14px; background: var(--surface-2); display: flex; flex-direction: column; gap: 6px; min-height: 132px; }
.step.done { background: var(--ok-soft); border-color: transparent; }
.step-num {
  width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-size: 12px; font-weight: 700;
  background: var(--surface); border: 1px solid var(--border-strong); color: var(--ink-2);
}
.step.done .step-num { background: var(--ok); border-color: var(--ok); color: #fff; }
.step-title { font-weight: 700; font-size: 13.5px; color: var(--ink); }
.step-text { font-size: 12px; color: var(--muted); line-height: 1.6; flex: 1; }
.step .q-btn { align-self: flex-start; }
.meter { height: 6px; width: 120px; border-radius: 99px; background: var(--border); overflow: hidden; }
.meter > div { height: 100%; background: var(--ok); border-radius: 99px; }

/* ---------- stats ---------- */
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; width: 100%; }
.stat { padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; }
.stat-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.stat-label { font-size: 12.5px; color: var(--muted); }
.stat-icon { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--ink); line-height: 1.2; }
.stat-hint { font-size: 12px; color: var(--muted); }

/* ---------- accounts ---------- */
.account { display: flex; align-items: center; gap: 14px; padding: 16px 20px; width: 100%; }
.account + .account { border-top: 1px solid var(--border); }
.account.disabled .account-main, .account.disabled .avatar { opacity: .55; }
.avatar {
  width: 42px; height: 42px; border-radius: 12px; flex: none; display: grid; place-items: center;
  font-weight: 700; font-size: 17px; color: #fff; text-transform: uppercase;
}
.account-main { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: flex-start; gap: 3px; }
.account-main > * { max-width: 100%; }
.account-email { font-weight: 600; font-size: 14.5px; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-server { font-size: 12px; color: var(--muted); }
.account-status { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--ink-2); min-width: 0; }
.account-status .dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
.dot-ok { background: var(--ok); } .dot-err { background: var(--err); } .dot-idle { background: var(--border-strong); }
.account-error { color: var(--err); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-meta { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; font-size: 12px; color: var(--muted); flex: none; min-width: 96px; padding-inline-end: 14px; margin-inline-end: 2px; border-inline-end: 1px solid var(--border); }
.account-meta b { font-size: 13.5px; color: var(--ink); font-weight: 600; }
.account-actions { display: flex; align-items: center; gap: 2px; flex: none; }
.chip { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 600; padding: 2px 9px; border-radius: 99px; white-space: nowrap; }
.chip-ok { background: var(--ok-soft); color: var(--ok); }
.chip-idle { background: var(--surface-2); color: var(--muted); border: 1px solid var(--border); }
.chip-err { background: var(--err-soft); color: var(--err); }
.chip-warn { background: var(--warn-soft); color: var(--warn); }
.empty { padding: 44px 20px; display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center; width: 100%; }
.empty-icon.tone-err { background: var(--err-soft); color: var(--err); }
.empty-icon { width: 64px; height: 64px; border-radius: 20px; display: grid; place-items: center; background: var(--brand-soft); color: var(--brand); margin-bottom: 6px; }

/* ---------- forms ---------- */
.field .q-field__control { border-radius: 10px !important; }
.field.q-field--outlined .q-field__control { background: var(--surface); }
.field.q-field--outlined .q-field__control:before { border-color: var(--border-strong); }
.form-row { display: flex; align-items: flex-start; gap: 10px; width: 100%; flex-wrap: wrap; }
.setting-row { display: flex; align-items: flex-start; gap: 14px; width: 100%; padding: 18px 0; }
.setting-row + .setting-row { border-top: 1px solid var(--border); }
.setting-icon { width: 38px; height: 38px; border-radius: 11px; flex: none; display: grid; place-items: center; }
.banner { display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 10px 12px; border-radius: 10px; font-size: 13px; line-height: 1.7; }
.banner-ok { background: var(--ok-soft); color: var(--ok); }
.banner-err { background: var(--err-soft); color: var(--err); }
.banner-info { background: var(--surface-2); color: var(--ink-2); border: 1px solid var(--border); }
.facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; width: 100%; }
.fact { display: flex; gap: 10px; align-items: flex-start; font-size: 12.5px; color: var(--ink-2); line-height: 1.7; }
.fact .q-icon { color: var(--ok); margin-top: 3px; }
.q-toggle__label, .q-btn-group .q-btn { font-weight: 600; }
.seg.q-btn-group { border: 1px solid var(--border-strong); border-radius: 10px; overflow: hidden; box-shadow: none; }
.seg.q-btn-group .q-btn { color: var(--ink-2); padding: 0 14px; min-height: 36px; }

/* ---------- logs ---------- */
.log-list { width: 100%; max-height: calc(100vh - 230px); overflow: auto; direction: ltr; }
.log-row { display: grid; grid-template-columns: 150px 74px 1fr; gap: 12px; align-items: start; padding: 9px 18px; border-top: 1px solid var(--border); font-size: 12.5px; }
.log-row:first-child { border-top: 0; }
.log-time { font-family: var(--mono); color: var(--muted); font-size: 12px; padding-top: 1px; }
.log-level { justify-self: start; font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 99px; background: var(--surface-2); color: var(--muted); border: 1px solid var(--border); }
.log-msg { margin: 0; font-family: var(--mono); font-size: 12px; color: var(--ink-2); white-space: pre-wrap; word-break: break-word; }
.log-row.lvl-warning .log-level { background: var(--warn-soft); color: var(--warn); border-color: transparent; }
.log-row.lvl-error .log-level, .log-row.lvl-critical .log-level { background: var(--err-soft); color: var(--err); border-color: transparent; }
.log-row.lvl-error .log-msg, .log-row.lvl-critical .log-msg { color: var(--err); }

/* ---------- misc ---------- */
.q-notification { border-radius: 12px !important; font-family: var(--font); }
.q-tooltip { font-family: var(--font); font-size: 12px; border-radius: 8px; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 99px; border: 3px solid transparent; background-clip: content-box; }

@media (max-width: 1100px) {
  .steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .app-shell { flex-direction: column; }
  .sidebar { position: static; width: 100%; height: auto; flex-direction: row; flex-wrap: wrap; align-items: center; padding: 10px 14px; gap: 4px; border-inline-end: 0; border-bottom: 1px solid var(--border); }
  .brand { padding: 0 4px 6px; width: 100%; }
  .nav-label, .sidebar-foot .foot-note { display: none; }
  .nav-item.q-btn { width: auto; }
  .sidebar-foot { margin-top: 0; width: 100%; }
  .app-main { padding: 18px 16px 32px; }
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .facts { grid-template-columns: 1fr; }
  .account { flex-wrap: wrap; }
  .account-main { flex-basis: calc(100% - 60px); }
  .account-meta { border: 0; padding: 0; margin: 0; margin-inline-start: 56px; }
  .account-actions { margin-inline-start: auto; }
}
@media (max-width: 560px) {
  .steps, .stats { grid-template-columns: 1fr; }
  .log-row { grid-template-columns: 1fr; gap: 4px; }
}
'''
