from __future__ import annotations

from html import escape

from newsintel.domain.access import AccessRole, Permission, permissions_for_role

BASE_CSS = r"""
:root{
  color-scheme:light dark;
  --bg:#f4f7fb;--surface:#ffffff;--surface-2:#f8faff;--text:#172033;--muted:#657084;
  --line:#dde4ee;--line-strong:#cbd5e1;--brand:#3453b5;--brand-2:#243b8f;--brand-soft:#eef2ff;
  --good:#167044;--good-bg:#e9f8ef;--warn:#7a5800;--warn-bg:#fff4d8;--bad:#9d2437;--bad-bg:#ffe9ec;
  --info:#3157a6;--info-bg:#edf3ff;--shadow:0 12px 40px rgba(25,40,75,.08);--radius:16px;
  --sans:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
[hidden]{display:none!important}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);line-height:1.5}
a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}button,input,select,textarea{font:inherit}
button,.button{min-height:42px;border:0;border-radius:11px;padding:0 15px;background:var(--brand);color:#fff;font-weight:750;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:7px;text-decoration:none;transition:transform .15s ease,box-shadow .15s ease,background .15s ease}
button:hover,.button:hover{background:var(--brand-2);text-decoration:none;transform:translateY(-1px)}button:disabled{opacity:.55;cursor:not-allowed;transform:none}.button.secondary,button.secondary{background:var(--surface-2);color:var(--brand-2);border:1px solid var(--line)}.button.ghost,button.ghost{background:transparent;color:var(--text);border:1px solid var(--line)}button.danger,.button.danger{background:#b42342}
input,select,textarea{width:100%;border:1px solid var(--line-strong);border-radius:11px;background:var(--surface);color:var(--text);padding:10px 12px;outline:none;transition:border .15s ease,box-shadow .15s ease}input:focus,select:focus,textarea:focus{border-color:#8098e7;box-shadow:0 0 0 4px rgba(52,83,181,.11)}textarea{resize:vertical;min-height:96px}
:focus-visible{outline:3px solid rgba(52,83,181,.34);outline-offset:2px}.skip{position:fixed;top:-60px;left:12px;z-index:100;background:var(--text);color:var(--surface);padding:9px 12px;border-radius:8px}.skip:focus{top:12px}
.app-header{position:sticky;top:0;z-index:30;border-bottom:1px solid color-mix(in srgb,var(--line) 84%,transparent);background:color-mix(in srgb,var(--surface) 90%,transparent);backdrop-filter:blur(14px)}.app-nav{width:min(1280px,calc(100% - 28px));min-height:64px;margin:auto;display:flex;align-items:center;gap:18px;justify-content:space-between}.brand{display:flex;align-items:center;gap:10px;color:var(--text);font-weight:850;letter-spacing:-.02em}.brand-mark{width:31px;height:31px;border-radius:10px;background:linear-gradient(135deg,var(--brand),#6d86e5);box-shadow:inset 0 0 0 1px rgba(255,255,255,.25)}.nav-links{display:flex;align-items:center;gap:5px;flex-wrap:wrap}.nav-links a{padding:8px 10px;border-radius:9px;color:var(--muted);font-weight:700;font-size:14px}.nav-links a:hover,.nav-links a.active{background:var(--brand-soft);color:var(--brand);text-decoration:none}.nav-meta{display:flex;align-items:center;gap:8px}.mobile-nav{display:none}
.shell{width:min(1280px,calc(100% - 28px));margin:0 auto;padding:28px 0 64px}.page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:22px}.page-head h1{margin:4px 0 4px;font-size:clamp(30px,4vw,48px);line-height:1.02;letter-spacing:-.035em}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--brand);font-weight:850}.muted{color:var(--muted)}.small{font-size:13px}.lead{font-size:17px;color:var(--muted);max-width:760px}
.panel,.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}.panel{padding:20px}.tile{display:block;padding:22px;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);color:var(--text);transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}.tile:hover{transform:translateY(-2px);border-color:#bfcaf1;box-shadow:0 16px 38px rgba(25,40,75,.11);text-decoration:none}.tile h2{margin:7px 0 6px;font-size:22px;letter-spacing:-.02em}.tile p{margin:0}.panel.flat{box-shadow:none}.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.section-head h2,.panel h2{margin:0;font-size:19px;letter-spacing:-.015em}.stack{display:grid;gap:14px}.grid{display:grid;gap:14px}.grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.toolbar.grow>*:first-child{flex:1;min-width:220px}.filters{display:flex;gap:8px;flex-wrap:wrap}.filter-chip{min-height:34px;padding:0 11px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--muted);font-size:13px;font-weight:700;cursor:pointer}.filter-chip.active{background:var(--brand-soft);color:var(--brand);border-color:#cbd6ff}
.pill-row{display:flex;gap:6px;flex-wrap:wrap}.pill{display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:999px;background:var(--brand-soft);color:var(--brand);font-size:11px;font-weight:800;letter-spacing:.01em}.pill.good{background:var(--good-bg);color:var(--good)}.pill.warn{background:var(--warn-bg);color:var(--warn)}.pill.bad{background:var(--bad-bg);color:var(--bad)}.pill.neutral{background:var(--surface-2);color:var(--muted);border:1px solid var(--line)}
.metric{padding:15px;border:1px solid var(--line);border-radius:13px;background:var(--surface-2)}.metric .label{font-size:12px;color:var(--muted);font-weight:750}.metric .value{font-size:24px;line-height:1.15;font-weight:850;margin-top:5px;letter-spacing:-.02em}.metric .hint{font-size:12px;color:var(--muted);margin-top:4px}
.notice{border-radius:12px;padding:12px 14px;background:var(--info-bg);color:var(--info);border:1px solid #d7e3ff}.notice.warn{background:var(--warn-bg);color:var(--warn);border-color:#f3dea2}.notice.bad{background:var(--bad-bg);color:var(--bad);border-color:#f3c4cd}.empty{padding:30px;text-align:center;border:1px dashed var(--line-strong);border-radius:14px;color:var(--muted);background:var(--surface-2)}.error-box{padding:16px;border-radius:12px;background:var(--bad-bg);color:var(--bad);border:1px solid #f3c4cd}.skeleton{position:relative;overflow:hidden;background:#e8edf5;border-radius:8px;min-height:14px}.skeleton::after{content:"";position:absolute;inset:0;transform:translateX(-100%);background:linear-gradient(90deg,transparent,rgba(255,255,255,.72),transparent);animation:shimmer 1.25s infinite}@keyframes shimmer{to{transform:translateX(100%)}}
.status-dot{width:9px;height:9px;border-radius:50%;background:#9aa5b4;display:inline-block}.status-dot.live{background:#22a05a;box-shadow:0 0 0 5px rgba(34,160,90,.12)}
.article-list{display:grid;gap:12px}.story-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:18px;padding:18px;background:var(--surface);border:1px solid var(--line);border-radius:15px;box-shadow:0 6px 24px rgba(25,40,75,.045);transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}.story-card:hover{transform:translateY(-1px);border-color:#bfcaf1;box-shadow:0 12px 32px rgba(25,40,75,.08)}.story-card h2,.story-card h3{margin:4px 0 7px;line-height:1.28;letter-spacing:-.015em}.story-card h2{font-size:20px}.story-card .story-side{text-align:right;min-width:118px}.story-card .pattern{font-weight:800;color:var(--text);text-transform:capitalize}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);overflow-x:auto}.tab{border:0;border-radius:9px 9px 0 0;background:transparent;color:var(--muted);padding:11px 12px;min-height:auto}.tab.active{color:var(--brand);background:var(--brand-soft)}.tab-panel{display:none;padding-top:18px}.tab-panel.active{display:block}
.timeline{display:grid;gap:0}.timeline-item{position:relative;padding:0 0 18px 24px}.timeline-item::before{content:"";position:absolute;left:5px;top:7px;width:8px;height:8px;border-radius:50%;background:var(--brand)}.timeline-item::after{content:"";position:absolute;left:8px;top:18px;bottom:0;width:2px;background:var(--line)}.timeline-item:last-child::after{display:none}.timeline-time{font-size:12px;color:var(--muted);margin-top:3px}
.claim-card{border:1px solid var(--line);border-radius:13px;background:var(--surface-2);overflow:hidden}.claim-card summary{list-style:none;cursor:pointer;padding:14px;display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.claim-card summary::-webkit-details-marker{display:none}.claim-body{padding:0 14px 14px;border-top:1px solid var(--line)}.evidence-list{display:grid;gap:8px;margin-top:10px}.evidence-item{padding:10px;border-radius:10px;border:1px solid var(--line);background:var(--surface)}
.bar{height:8px;background:#e7ebf3;border-radius:999px;overflow:hidden}.bar>span{display:block;height:100%;background:var(--brand);border-radius:inherit}.dimension{display:grid;grid-template-columns:minmax(170px,.55fr) 1fr auto;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--line)}.dimension:first-child{border-top:0}.prose{white-space:pre-wrap;line-height:1.72;font-size:15px}.prose-box{max-height:640px;overflow:auto;padding:18px;border:1px solid var(--line);border-radius:13px;background:var(--surface-2)}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:13px}table{width:100%;border-collapse:collapse;min-width:760px}th,td{padding:11px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;font-size:13px}th{background:var(--surface-2);color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em;position:sticky;top:0}tr:last-child td{border-bottom:0}
.toast-region{position:fixed;right:18px;bottom:18px;z-index:100;display:grid;gap:8px;width:min(380px,calc(100% - 36px))}.toast{padding:12px 14px;border:1px solid var(--line);background:var(--surface);border-radius:12px;box-shadow:var(--shadow)}
.sr-only{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(prefers-color-scheme:dark){:root{--bg:#0d1220;--surface:#121a2a;--surface-2:#0f1726;--text:#edf2ff;--muted:#a0abc0;--line:#263248;--line-strong:#394860;--brand:#91a8ff;--brand-2:#b8c6ff;--brand-soft:#1b2748;--good:#9ce0b9;--good-bg:#123c2b;--warn:#ffe1a0;--warn-bg:#493915;--bad:#ffb3c1;--bad-bg:#451b29;--info:#b8ccff;--info-bg:#18294d;--shadow:0 12px 40px rgba(0,0,0,.22)}.skeleton{background:#243047}.skeleton::after{background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}.bar{background:#28344a}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important;animation-duration:.01ms!important;animation-iteration-count:1!important}}
@media(max-width:820px){.app-nav{min-height:58px}.nav-links{display:none}.mobile-nav{position:fixed;bottom:0;left:0;right:0;z-index:40;display:flex;overflow-x:auto;overscroll-behavior-x:contain;border-top:1px solid var(--line);background:color-mix(in srgb,var(--surface) 94%,transparent);backdrop-filter:blur(14px);scrollbar-width:none}.mobile-nav::-webkit-scrollbar{display:none}.mobile-nav a{flex:1 0 76px;padding:10px 6px 12px;text-align:center;font-size:11px;font-weight:750;color:var(--muted);white-space:nowrap}.mobile-nav a.active{color:var(--brand);background:var(--brand-soft)}.shell{padding-bottom:90px}.page-head{align-items:flex-start;flex-direction:column}.grid.two,.grid.three,.grid.four{grid-template-columns:1fr}.story-card{grid-template-columns:1fr}.story-card .story-side{text-align:left}.dimension{grid-template-columns:1fr}.toolbar.grow>*:first-child{min-width:100%}}
@media(max-width:520px){.shell,.app-nav{width:min(100% - 18px,1280px)}.panel{padding:15px}.page-head h1{font-size:32px}.story-card{padding:14px}.nav-meta .label-hide{display:none}}

/* News Intelligence visual system: calm editorial surfaces with a dark navigation rail. */
:root{color-scheme:light;--bg:#f5f7fb;--surface:#fff;--surface-2:#f8faff;--text:#14233c;--muted:#5d6d85;--line:#e1e7f0;--line-strong:#c6d2e2;--brand:#2158d8;--brand-2:#1745b5;--brand-soft:#edf3ff;--info:#2456b7;--info-bg:#edf4ff;--shadow:0 6px 22px rgba(22,37,64,.045);--radius:16px}
html{scroll-padding-top:100px}body{font-size:14px;letter-spacing:.003em;background:var(--bg)}.app-sidebar{position:fixed;top:0;bottom:0;left:0;width:244px;padding:28px 14px 18px;background:#101d34;color:#e9f1ff;z-index:41;display:flex;flex-direction:column;gap:26px;box-shadow:8px 0 35px rgba(16,29,52,.06)}
.sidebar-brand{color:#fff;display:flex;align-items:center;gap:11px;padding:2px 10px 20px;border-bottom:1px solid rgba(255,255,255,.10)}.sidebar-brand:hover{color:#fff;text-decoration:none}.brand-copy{display:flex;flex-direction:column;line-height:1.25}.brand-copy b{font-size:15px;letter-spacing:-.025em}.brand-copy small{font-size:11px;font-weight:500;margin-top:3px;color:#a4b4d1}.brand-mark{width:36px;height:36px;flex:none;border-radius:11px;background:#fff;box-shadow:none;position:relative;display:grid;place-items:center}.brand-mark::before{content:'';height:17px;width:17px;border:2px solid #2158d8;border-radius:50%;transform:rotate(-25deg)}.brand-mark span{position:absolute;width:5px;height:5px;border-radius:50%;background:#2158d8;top:8px;right:7px}
.nav-links{display:block;overflow:auto;flex:1;scrollbar-width:thin}.nav-group{margin-bottom:21px}.nav-group-label{font-size:10px;letter-spacing:.115em;text-transform:uppercase;font-weight:800;color:#8499ba;padding:0 14px;margin:0 0 8px}.nav-links a{display:block;color:#c5d2e6;padding:11px 14px;margin:2px 0;border-radius:10px;font-size:13px;font-weight:650;border:1px solid transparent;transition:background .12s ease,color .12s ease}.nav-links a:hover{background:#1a2b49;color:#fff;text-decoration:none}.nav-links a.active,.nav-links a[aria-current="page"]{background:#234477;color:#fff;border-color:#34558b;box-shadow:inset 3px 0 #7cbbff}.sidebar-foot{border-top:1px solid rgba(255,255,255,.09);padding:16px 10px 0;display:flex;align-items:center;gap:8px;color:#adbed8;font-size:11px;flex-wrap:wrap}.sidebar-foot a{color:#cedaf2;display:block;width:100%;padding-top:8px;font-size:12px}
.app-header{margin-left:244px;left:auto;position:sticky;top:0;z-index:35;background:rgba(255,255,255,.95);backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}.app-nav{width:auto;max-width:1440px;padding:0 30px;min-height:68px;gap:18px}.topbar-context{color:var(--muted);font-size:13px;font-weight:550}.compact-brand,.menu-toggle{display:none}.topbar-search{display:flex;align-items:center;gap:10px;color:#667590;font-size:12px;font-weight:550;border:1px solid var(--line);background:#f6f8fc;border-radius:10px;padding:9px 12px}.topbar-search:hover{text-decoration:none;border-color:#b0c6ec}.topbar-search kbd{font:inherit;padding:0 6px;border:1px solid #d0d9e7;border-radius:4px;background:white}.topbar-home{font-size:12px;font-weight:750}.icon-button{min-width:40px;padding:0 8px;font-size:23px;background:transparent!important;color:var(--text)!important;border:1px solid var(--line);box-shadow:none!important}.shell{margin-left:244px;margin-right:0;width:calc(100% - 244px);max-width:none;padding:30px clamp(22px,3.1vw,52px) 72px}.shell>*{max-width:1520px;margin-left:auto;margin-right:auto}.page-head{align-items:center;margin-bottom:24px;gap:28px}.page-head h1{font-size:clamp(28px,3vw,41px);line-height:1.15;font-weight:800;letter-spacing:-.035em;margin-top:6px}.eyebrow{letter-spacing:.085em;font-size:11px;color:#46699f}.lead{font-size:14px;line-height:1.65;max-width:740px;margin-top:8px}.page-head .toolbar{justify-content:flex-end}
.panel,.card,.tile{border:1px solid var(--line);box-shadow:var(--shadow);border-radius:16px}.panel{padding:23px}.panel.flat{box-shadow:var(--shadow)}.section-head{margin-bottom:17px}.section-head h2,.panel h2{font-size:16px;font-weight:780}.grid{gap:16px}.grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}.tile{padding:21px;position:relative}.tile:hover{border-color:#97b3e8;box-shadow:0 12px 27px rgba(30,54,110,.10)}.tile h2{font-size:17px}.metric{padding:19px 20px;background:#fff;border-radius:14px;min-width:0}.metric .label{font-size:11px;letter-spacing:.015em;font-weight:750;color:#63748c}.metric .value{font-size:30px;font-weight:800;line-height:1.2;letter-spacing:-.045em;color:#1a355c;margin-top:9px;font-variant-numeric:tabular-nums}.metric .hint{font-size:11px;line-height:1.45;color:#718098;margin-top:8px}.story-card{padding:20px 22px;box-shadow:none;border-radius:14px}.story-card:hover{background:#fbfcff}.story-card h2{font-size:18px;line-height:1.36}.pill{letter-spacing:0;font-size:11px;border-radius:7px;font-weight:740;padding:5px 9px}.pill.neutral{background:#f2f5fa;color:#465d79;border-color:#dfe6ef}.pill.good{background:#ecf8f0}.pill.warn{background:#fff7e3}.pill.bad{background:#fff0f2}.filter-chip{border-radius:8px}.filter-chip.active{border-color:#b3c8f4}.button,button{font-size:12px;font-weight:740;border-radius:9px;min-height:39px}.button.secondary,button.secondary{background:#f7f9fd;color:#1b4da9}.button.ghost,button.ghost{color:var(--text)}input,select,textarea{font-size:13px;border-radius:9px}input:focus-visible,select:focus-visible,textarea:focus-visible{outline-offset:1px}.table-wrap{border-radius:12px}.table-wrap th{font-size:10px;letter-spacing:.09em}.table-wrap td{font-size:12px}.tabs{gap:8px}.tab{font-size:12px;white-space:nowrap;border-radius:8px 8px 0 0;padding:11px 15px}.timeline-item::before{width:9px;height:9px}.notice{font-size:13px;line-height:1.65}.prose{line-height:1.76;font-size:14px}.empty{padding:34px}.row-link{border-radius:11px}
.mobile-nav{display:none}.nav-backdrop{display:none}.menu-toggle{display:none}.mobile-menu-head{display:none}.mobile-signout{display:none}
/* High-density layouts retain three/four columns when room allows. */
@media(min-width:821px) and (max-width:1310px){.app-sidebar{width:210px}.app-header{margin-left:210px}.shell{margin-left:210px;width:calc(100% - 210px)}.app-nav{padding:0 20px}.grid.four{grid-template-columns:repeat(2,minmax(0,1fr))}.topbar-context{display:none}}
@media(max-width:820px){.app-sidebar{display:none}.app-header{margin-left:0}.app-nav{padding:0 14px;min-height:61px}.compact-brand{display:flex;gap:9px;font-size:13px;white-space:nowrap}.compact-brand .brand-mark{width:30px;height:30px}.menu-toggle{display:inline-flex;align-items:center}.topbar-context,.topbar-home,.topbar-search span,.topbar-search kbd{display:none}.topbar-search{min-height:38px;font-size:21px;padding:3px 10px}.shell{width:100%;margin:0;padding:22px 18px 60px}.grid.four{grid-template-columns:repeat(2,minmax(0,1fr))}.grid.three{grid-template-columns:repeat(2,minmax(0,1fr))}.grid.two{grid-template-columns:1fr}.page-head{flex-direction:column;align-items:flex-start;gap:14px}.page-head h1{font-size:32px}.nav-backdrop{display:block;position:fixed;inset:0;background:rgba(9,20,40,.5);z-index:49}.nav-backdrop[hidden]{display:none}.mobile-nav{display:flex;flex-direction:column;position:fixed;z-index:50;top:0;bottom:0;left:0;right:auto;width:min(82vw,320px);padding:16px 16px 30px;border:0;background:#101d34;color:#fff;overflow-y:auto;transform:translateX(-105%);transition:transform .18s ease;box-shadow:12px 0 48px rgba(0,0,0,.2)}.mobile-nav.is-open{transform:translateX(0)}.mobile-menu-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;padding:4px 2px 14px;border-bottom:1px solid rgba(255,255,255,.14)}.mobile-menu-head .icon-button{color:#fff!important;border-color:#435571}.mobile-nav a{flex:none;display:block;padding:12px 14px;min-height:42px;border-radius:9px;font-size:14px;color:#c9d6ea;text-align:left}.mobile-nav a.active{background:#254879;color:#fff}.mobile-signout{display:block;margin-top:26px!important;border-top:1px solid #30425e;border-radius:0!important}.story-card{grid-template-columns:1fr}.story-card .story-side{text-align:left;min-width:0}.dimension{grid-template-columns:1fr}.toolbar.grow>*:first-child{min-width:100%}.shell .panel{padding:18px}}
@media(max-width:520px){.shell{padding:18px 12px 50px}.grid.three{grid-template-columns:1fr;gap:10px}.grid.four{grid-template-columns:1fr 1fr;gap:9px}.metric{padding:13px}.metric .value{font-size:24px}.page-head h1{font-size:29px}.story-card{padding:16px}.panel{padding:16px}.section-head{align-items:flex-start}.page-head .toolbar{width:100%}.page-head .toolbar>*{max-width:100%}}
@media(max-width:360px){.grid.three,.grid.four{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.mobile-nav{transition:none}}


.theme-toggle{display:inline-flex!important;font-size:18px;min-height:38px;min-width:38px;color:#506381!important;background:#f6f8fc!important}
.site-explainer{margin:6px 0 0 244px;padding:0 clamp(22px,3.1vw,52px) 45px;color:var(--muted);font-size:12px}.site-explainer details{max-width:1510px;margin:auto;border-top:1px solid var(--line);padding-top:16px}.site-explainer summary{cursor:pointer;font-weight:740;color:var(--brand)}.site-explainer p{max-width:900px;line-height:1.7}
html[data-theme="dark"]{color-scheme:dark;--bg:#0e1524;--surface:#182437;--surface-2:#202d42;--text:#e8effb;--muted:#a7b7cf;--line:#34445c;--line-strong:#4b5e79;--brand:#95b7ff;--brand-2:#c0d3ff;--brand-soft:#233656;--info:#b8d1ff;--info-bg:#1c3150;--good:#a0eac0;--good-bg:#1a3c30;--warn:#ffe1a3;--warn-bg:#483919;--bad:#ffafbd;--bad-bg:#472333;--shadow:0 7px 26px rgba(0,0,0,.13)}
html[data-theme="dark"] .app-header{background:rgba(24,36,55,.94)}html[data-theme="dark"] .metric,html[data-theme="dark"] .story-card,html[data-theme="dark"] .panel,html[data-theme="dark"] .tile{background:var(--surface)}html[data-theme="dark"] .metric .value{color:#dce9ff}html[data-theme="dark"] .story-card:hover{background:#20314c}html[data-theme="dark"] .pill.neutral{background:#23334b;color:#cad7e9;border-color:#40516d}html[data-theme="dark"] .pill.good{background:#1b4030}html[data-theme="dark"] .pill.warn{background:#483919}html[data-theme="dark"] .pill.bad{background:#472333}html[data-theme="dark"] .button.secondary,html[data-theme="dark"] button.secondary,html[data-theme="dark"] .topbar-search,html[data-theme="dark"] .theme-toggle,html[data-theme="dark"] input,html[data-theme="dark"] select,html[data-theme="dark"] textarea{background:#26364e!important;color:#e7effc!important;border-color:#425575}html[data-theme="dark"] .topbar-search kbd{background:#13223a;color:#cedbef;border-color:#425575}html[data-theme="dark"] .source-ref{background:#213b67;color:#d7e8ff;border-color:#37568a}html[data-theme="dark"] .reference-card,html[data-theme="dark"] .briefing-item{background:#202f45;border-color:#344c6c}html[data-theme="dark"] .empty{background:#1a293c}html[data-theme="dark"] .tab.active{background:#233656}html[data-theme="dark"] .nav-links a.active{background:#234477}
@media(max-width:820px){.site-explainer{margin-left:0;padding:0 18px 35px}}@media(max-width:520px){.topbar-home{display:none}.site-explainer{padding:0 12px 30px}}
@media(max-width:820px){.story-card{gap:12px}.story-card .story-side{display:flex;justify-content:flex-start;align-items:center;gap:10px}.story-card .story-side .toolbar{margin-top:0!important;justify-content:flex-start!important;flex-wrap:wrap}}

"""


READER_CSS = r"""
.reader-layout{font-size:15px}html:not([data-theme="dark"]) .reader-layout{--bg:#f6f7f9;--brand:#214c9a;--brand-2:#163b7d}
html[data-theme="dark"] .reader-layout #applyBrief,html[data-theme="dark"] .reader-layout #updateBrief,html[data-theme="dark"] .reader-layout #retryBrief,html[data-theme="dark"] .reader-layout #retryNews{color:#101d34}
.reader-header{position:sticky;top:0;z-index:40;background:var(--surface);border-bottom:1px solid var(--line)}
.reader-nav{max-width:1040px;margin:auto;min-height:74px;padding:12px 28px;display:flex;align-items:center;justify-content:space-between;gap:24px}
.reader-brand{color:var(--text);font-weight:800;letter-spacing:-.025em;display:flex;gap:10px;align-items:center;white-space:nowrap}.reader-brand:hover{text-decoration:none}.reader-brand .brand-mark{width:31px;height:31px;background:var(--brand-soft)}
.reader-links{display:flex;align-items:center;gap:6px;margin-left:auto}.reader-links>a,.reader-menu>summary{padding:10px 12px;color:var(--muted);font-size:13px;font-weight:650;border-radius:8px}.reader-links>a[aria-current]{color:var(--brand);background:var(--brand-soft)}
.reader-menu{position:relative}.reader-menu>summary{cursor:pointer;list-style:none}.reader-menu>summary::-webkit-details-marker{display:none}.reader-menu[open]>summary{background:var(--surface-2)}.reader-menu-list{position:absolute;right:0;top:45px;min-width:220px;background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:8px;display:grid;gap:3px}.reader-menu-list a{padding:10px;border-radius:7px;color:var(--text);font-size:13px}.reader-menu-list a:hover{background:var(--brand-soft);text-decoration:none}
.reader-layout .shell{width:100%;max-width:920px;margin:0 auto;padding:40px 28px 48px}.reader-layout .site-explainer{width:auto;max-width:864px;margin:0 auto 32px;padding:16px 0;font-size:12px;line-height:1.7;color:var(--muted);border-top:1px solid var(--line)}
.reader-layout button,.reader-layout .button{font-size:13px;min-height:44px}.reader-layout .panel{box-shadow:none}.reader-layout .section-head h2{font-size:20px}.reader-layout .notice{font-size:13px}
@media(max-width:620px){.reader-nav{min-height:64px;padding:10px 16px;gap:10px;flex-wrap:wrap}.reader-brand{font-size:14px}.reader-links{gap:0}.reader-links>a,.reader-menu>summary{padding:10px 8px;font-size:12px}.reader-brand .brand-mark{display:none}.reader-layout .shell{padding:28px 16px 36px}.reader-layout .site-explainer{margin:0 16px 24px}.reader-nav #themeToggle{min-width:36px;min-height:36px}}
@media(max-width:390px){.reader-brand{width:100%}.reader-links{margin:0;flex:1}.reader-nav{gap:4px}}
@media(max-width:620px){.reader-nav{display:grid;grid-template-columns:1fr auto;gap:6px 14px}.reader-brand{grid-column:1;grid-row:1;width:auto}.reader-links{grid-column:1/-1;grid-row:2;margin:0;justify-content:flex-start;gap:8px}.reader-nav #themeToggle{grid-column:2;grid-row:1}}
"""


def _permissions_for_role_name(role: str | None) -> frozenset[Permission]:
    try:
        resolved_role = AccessRole(role or AccessRole.VIEWER.value)
    except ValueError:
        resolved_role = AccessRole.VIEWER
    return permissions_for_role(resolved_role)


def nav_for_role(*, active: str, role: str | None = None) -> str:
    """One permission-derived navigation model for desktop and mobile."""
    permissions = _permissions_for_role_name(role)
    groups: list[tuple[str, list[tuple[str, str, str]]]] = []
    explore: list[tuple[str, str, str]] = [("workspace", "/app", "Home")]
    if Permission.CONTENT_VIEW in permissions:
        explore += [("briefs", "/briefs", "Daily & weekly brief"), ("news", "/news", "News"), ("events", "/events", "Events"), ("search", "/search", "Search")]
    groups.append(("Follow the story", explore))
    if Permission.CLAIMS_VIEW in permissions:
        groups.append(("Investigate", [
            ("investigations", "/investigations", "Investigations"),
            ("research", "/historical-research", "History & archives"),
            ("entities", "/entities", "People & organisations"),
        ]))
        groups.append(("Review quality", [
            ("accuracy", "/accuracy", "Verification review"),
            ("search-quality", "/search-quality", "Search quality"),
        ]))
    operations: list[tuple[str, str, str]] = []
    if Permission.SOURCES_MANAGE in permissions:
        operations.append(("sources", "/news-sources", "Sources"))
    if Permission.USERS_MANAGE in permissions:
        operations.append(("admin", "/admin/access-console", "Access"))
    if operations:
        groups.append(("Administration", operations))

    def link(key: str, href: str, label: str) -> str:
        klass = 'active' if key == active else ''
        current = ' aria-current="page"' if key == active else ''
        return f'<a class="{klass}" href="{href}"{current}>{label}</a>'

    menu = ''.join(
        f'<div class="nav-group"><div class="nav-group-label">{label}</div>'
        + ''.join(link(*item) for item in items)
        + '</div>'
        for label, items in groups
    )
    # Keep every authorized destination in the compact menu; no truncation.
    mobile = ''.join(link(*item) for _, items in groups for item in items)
    return f"""
<a class="skip" href="#main-content">Skip to content</a>
<aside class="app-sidebar" aria-label="Application navigation">
  <a class="sidebar-brand" href="/app"><span class="brand-mark" aria-hidden="true"><span></span></span><span class="brand-copy"><b>News Intelligence</b><small>Evidence-led reporting</small></span></a>
  <nav class="nav-links" aria-label="Sections">{menu}</nav>
  <div class="sidebar-foot"><span class="status-dot" aria-hidden="true"></span><span>Source-based research</span><a href="/auth/logout">Sign out</a></div>
</aside>
<header class="app-header"><nav class="app-nav" aria-label="Top navigation">
  <button id="openMobileMenu" class="icon-button menu-toggle" type="button" aria-expanded="false" aria-controls="mobileMenu" aria-label="Open navigation">☰</button>
  <a class="brand compact-brand" href="/app"><span class="brand-mark" aria-hidden="true"><span></span></span><span>News Intelligence</span></a>
  <div class="topbar-context">Reporting, history and evidence in one place</div>
  <div class="nav-meta"><button type="button" id="themeToggle" class="icon-button theme-toggle" aria-label="Switch appearance" title="Change appearance">◐</button><a class="topbar-search" href="/search" aria-label="Search reports and events">⌕ <span>Search reports and events</span><kbd>/</kbd></a><a class="topbar-home" href="/app">Home</a></div>
</nav></header>
<div id="navBackdrop" class="nav-backdrop" hidden></div>
<nav id="mobileMenu" class="mobile-nav" aria-label="Mobile navigation" aria-hidden="true" inert>
  <div class="mobile-menu-head"><strong>Explore News Intelligence</strong><button id="closeMobileMenu" class="icon-button" type="button" aria-label="Close navigation">×</button></div>
  {mobile}
  <a href="/auth/logout" class="mobile-signout">Sign out</a>
</nav>
"""

def render_app_page(
    *,
    title: str,
    body: str,
    active: str = "",
    role: str | None = None,
    scripts: str = "",
    extra_css: str = "",
    lang: str = "en",
    reader_mode: bool = False,
) -> str:
    navigation = nav_for_role(active=active, role=role)
    if reader_mode:
        def reader_link(key: str, href: str, label: str) -> str:
            current = ' aria-current="page"' if active == key else ''
            return f'<a href="{href}"{current}>{label}</a>'

        permissions = _permissions_for_role_name(role)
        extras = '<a href="/app">Research workspace</a><a href="/search">Search the archive</a>'
        if Permission.SOURCES_MANAGE in permissions:
            extras += '<a href="/news-sources">Manage publishers</a>'
        navigation = f"""<a class="skip" href="#main-content">Skip to content</a>
<header class="reader-header"><nav class="reader-nav" aria-label="Reader navigation">
<a class="reader-brand" href="/briefs"><span class="brand-mark" aria-hidden="true"><span></span></span>News Intelligence</a>
<div class="reader-links">{reader_link('briefs', '/briefs', 'Your brief')}{reader_link('news', '/news', 'Latest news')}
<details class="reader-menu"><summary>More <span aria-hidden="true">⌄</span></summary><div class="reader-menu-list">{extras}<a href="/auth/logout">Sign out</a></div></details></div>
<button id="themeToggle" class="icon-button" type="button" aria-label="Switch appearance" title="Change appearance">◐</button>
</nav></header>"""
    footer = ('<p>Headlines and excerpts come from the named publishers. Open the original report '
              'for full context. Coverage depends on the sources captured by this platform.</p>'
              if reader_mode else '<details><summary>How to read evidence and status labels</summary>'
              '<p><b>Supported</b> means the stored evidence assessment supports a specific claim; '
              'it is not a universal truth certificate. <b>Unresolved</b> means there is not enough '
              'evidence for a conclusion. <b>Historical links</b> provide context, not proof of '
              'current claims. <b>Text capture quality</b> measures how well an article was '
              'extracted, not whether its reporting is correct. Multiple publishers may share '
              'one source of reporting.</p></details>')
    return f"""<!doctype html>
<html lang="{escape(lang)}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light" />
<title>{escape(title)} · News Intelligence</title>
<style>{BASE_CSS}{READER_CSS if reader_mode else ''}{extra_css}</style>
</head>
<body class="{'reader-layout' if reader_mode else 'workspace-layout'}">
{navigation}
<main id="main-content" class="shell">{body}</main>
<footer class="site-explainer">{footer}</footer>
<div id="toastRegion" class="toast-region" aria-live="polite" aria-atomic="true"></div>
<script>
(function(){{
 const themeButton=document.getElementById('themeToggle');
 const osDark=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;
 let chosenTheme='light';try{{chosenTheme=localStorage.getItem('ni-theme')||(osDark?'dark':'light')}}catch(_e){{chosenTheme=osDark?'dark':'light'}}
 const applyTheme=()=>{{document.documentElement.dataset.theme=chosenTheme;if(themeButton){{themeButton.setAttribute('aria-label',chosenTheme==='dark'?'Switch to light mode':'Switch to dark mode');themeButton.setAttribute('aria-pressed',String(chosenTheme==='dark'))}}}};
 applyTheme();if(themeButton)themeButton.addEventListener('click',()=>{{chosenTheme=chosenTheme==='dark'?'light':'dark';try{{localStorage.setItem('ni-theme',chosenTheme)}}catch(_e){{}}applyTheme()}});
 const menu=document.getElementById('mobileMenu'), opener=document.getElementById('openMobileMenu'), closer=document.getElementById('closeMobileMenu'), backdrop=document.getElementById('navBackdrop');
 if(!menu||!opener||!closer||!backdrop)return;
 const open=()=>{{menu.classList.add('is-open');menu.setAttribute('aria-hidden','false');menu.inert=false;opener.setAttribute('aria-expanded','true');backdrop.hidden=false;closer.focus();}};
 const close=()=>{{menu.classList.remove('is-open');menu.setAttribute('aria-hidden','true');menu.inert=true;opener.setAttribute('aria-expanded','false');backdrop.hidden=true;opener.focus();}};
 opener.addEventListener('click',open);closer.addEventListener('click',close);backdrop.addEventListener('click',close);
 document.addEventListener('keydown',e=>{{if(e.key==='Escape'&&menu.classList.contains('is-open'))close()}});
 menu.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{{menu.classList.remove('is-open');menu.inert=true;menu.setAttribute('aria-hidden','true');backdrop.hidden=true}}));
}})();
</script>
{scripts}
</body>
</html>"""


COMMON_JS = r"""
function niEsc(v){return String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;')}
function niDate(v){if(!v)return '—';const d=new Date(v);return Number.isNaN(d.getTime())?'—':d.toLocaleString()}
function niRelative(v){if(!v)return '—';const d=new Date(v);const s=Math.round((d-Date.now())/1000);const a=Math.abs(s);const r=new Intl.RelativeTimeFormat(undefined,{numeric:'auto'});if(a<60)return r.format(s,'second');if(a<3600)return r.format(Math.round(s/60),'minute');if(a<86400)return r.format(Math.round(s/3600),'hour');if(a<2592000)return r.format(Math.round(s/86400),'day');return niDate(v)}
function niTitle(v){const key=String(v??'').toLowerCase();const labels={not_checkable:'Not enough evidence',insufficient_evidence:'Not enough evidence',possible_conflict_or_revision:'Possible reporting conflict',mostly_new_reporting:'New reporting',material_update:'Material change',continuity_with_prior_reporting:'Consistent with earlier reports',retraction:'Retraction',factual_correction:'Factual correction',ready_with_warnings:'Needs review',internal_only:'Internal history only',abstained:'No conclusion',no_checkable_claims:'No checkable claims'};return labels[key]||String(v??'').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
function niSafeUrl(value){try{const u=new URL(String(value),location.origin);return ['http:','https:'].includes(u.protocol)?u.href:'#'}catch{return '#'}}
function niCsrf(){return document.cookie.split('; ').find(x=>x.startsWith('newsintel_csrf='))?.split('=')[1]||''}
async function niApi(path,options={}){const headers=Object.assign({},options.headers||{});if(options.method&&options.method!=='GET')headers['X-CSRF-Token']=niCsrf();if(options.body&&!headers['Content-Type'])headers['Content-Type']='application/json';const r=await fetch(path,Object.assign({credentials:'same-origin'},options,{headers}));if(!r.ok){let d=await r.text();try{d=JSON.parse(d).detail||d}catch{}const e=new Error(String(d).slice(0,600));e.status=r.status;throw e}if(r.status===204)return null;return r.json()}
async function niOptional(path){try{return await niApi(path)}catch(e){if(e.status===401||e.status===403||e.status===404)return null;throw e}}
function niPill(text,kind='neutral'){return `<span class="pill ${kind}">${niEsc(text)}</span>`}
function niToast(message,kind=''){const region=document.getElementById('toastRegion');if(!region)return;const t=document.createElement('div');t.className=`toast ${kind}`;t.textContent=message;region.appendChild(t);setTimeout(()=>t.remove(),4500)}
function niDebounce(fn,ms=180){let h;return(...args)=>{clearTimeout(h);h=setTimeout(()=>fn(...args),ms)}}
function niInitTabs(root=document){for(const list of root.querySelectorAll('[role="tablist"]')){const tabs=Array.from(list.querySelectorAll('[role="tab"][data-tab]'));if(!tabs.length)continue;const activate=(tab,focus=false)=>{for(const t of tabs){const on=t===tab;t.classList.toggle('active',on);t.setAttribute('aria-selected',String(on));t.tabIndex=on?0:-1;const panel=root.getElementById?root.getElementById(`tab-${t.dataset.tab}`):document.getElementById(`tab-${t.dataset.tab}`);if(panel){panel.classList.toggle('active',on);panel.hidden=!on}}if(focus)tab.focus()};tabs.forEach((tab,index)=>{if(!tab.id)tab.id=`tab-control-${tab.dataset.tab}`;const panel=document.getElementById(`tab-${tab.dataset.tab}`);if(panel){tab.setAttribute('aria-controls',panel.id);panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id)}tab.addEventListener('click',()=>activate(tab));tab.addEventListener('keydown',event=>{let target=null;if(event.key==='ArrowRight')target=tabs[(index+1)%tabs.length];else if(event.key==='ArrowLeft')target=tabs[(index-1+tabs.length)%tabs.length];else if(event.key==='Home')target=tabs[0];else if(event.key==='End')target=tabs[tabs.length-1];if(target){event.preventDefault();activate(target,true)}})});activate(tabs.find(t=>t.classList.contains('active'))||tabs[0])}}
"""
