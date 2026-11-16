// Shared presentation and navigation, kept separate from application workflows.
const uiPaths = {
 home:'M3 10 12 3l9 7v10H3Z M9 20v-7h6v7',
 calendar:'M5 5h14v16H5Z M8 3v4m8-4v4M5 10h14M8 14h2m4 0h2m-8 3h2',
 swap:'M4 7h15l-4-4m4 4-4 4M20 17H5l4-4m-4 4 4 4',
 users:'M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3m17-7a4 4 0 0 1 3 4v3M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0m4-4a4 4 0 0 1 0 8',
 team:'M3 21v-3a4 4 0 0 1 4-4h5a4 4 0 0 1 4 4v3M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0m4 1h6m-3-3v6',
 chart:'M4 3v18h17M8 17v-5m5 5V7m5 10V4',
 book:'M12 5C8 2 4 3 2 4v15c4-2 7-1 10 1 3-2 6-3 10-1V4c-2-1-6-2-10 1Zm0 0v15',
 shield:'M12 2 3 6v6c0 5 6 9 9 10 3-1 9-5 9-10V6ZM8 12l3 3 5-6',
 settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8m-2-5h4l1 3 3 1 3-1 2 4-2 2v3l1 2-3 3-3-1-2 2h-4l-1-3-3-1-2 1-2-4 2-2v-3L2 7l3-3 3 1Z',
 history:'M3 11a9 9 0 1 1 2 7M3 4v7h7m2-5v6l4 2',
 chat:'M4 5h16v11H9l-5 4Zm4 4h8m-8 4h5',
 school:'M2 9 12 3l10 6M4 8v13h16V8M9 21v-7h6v7M10 9h4',
 menu:'M4 6h16M4 12h16M4 18h16',
 user:'M20 21v-3a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v3M16 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
 logout:'M10 3H4v18h6m-2-9h13m-4-4 4 4-4 4',
 plus:'M12 5v14M5 12h14',arrow:'M20 12H4m5-5-5 5 5 5',
 upload:'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',chevron:'m6 9 6 6 6-6',
 file:'M14 2H4v20h16V8Zm0 0v6h6M8 12h8m-8 4h8',
 image:'M3 3h18v18H3Zm0 13 5-5 5 6 3-3 5 5M16 7h.01',
 print:'M6 8V2h12v6M6 17H3V8h18v9h-3M6 13h12v9H6Zm11-2h.01',
 check:'m5 12 4 4L19 6',clock:'M12 8v5l3 2m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
 absent:'M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0m5 1 4 4m0-4-4 4'
};
function uiIcon(name){return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${uiPaths[name]||uiPaths.book}"/></svg>`}
document.querySelectorAll('[data-icon]').forEach(el=>el.innerHTML=uiIcon(el.dataset.icon));
const mobileBreakpoint=matchMedia('(max-width:1024px)');
const sideMenu=document.querySelector('#main-sidebar'),menuToggle=document.querySelector('#menu-toggle'),menuBackdrop=document.querySelector('#sidebar-backdrop');
function closeNavigation(restore=false){document.querySelector('#main-content').inert=false;document.querySelector('.topbar').inert=false;sideMenu.classList.remove('open');menuBackdrop.hidden=true;menuToggle.setAttribute('aria-expanded','false');sideMenu.inert=mobileBreakpoint.matches;sideMenu.removeAttribute('role');sideMenu.removeAttribute('aria-modal');document.body.classList.remove('menu-open');if(restore)menuToggle.focus()}
menuToggle.addEventListener('click',()=>{document.querySelector('#main-content').inert=true;document.querySelector('.topbar').inert=true;sideMenu.inert=false;sideMenu.classList.add('open');sideMenu.setAttribute('role','dialog');sideMenu.setAttribute('aria-modal','true');sideMenu.setAttribute('aria-label','التنقل الرئيسي');menuBackdrop.hidden=false;menuToggle.setAttribute('aria-expanded','true');document.body.classList.add('menu-open');document.querySelector('#menu-close').focus()});
document.querySelector('#menu-close').addEventListener('click',()=>closeNavigation(true));menuBackdrop.addEventListener('click',()=>closeNavigation(true));
mobileBreakpoint.addEventListener('change',()=>closeNavigation());closeNavigation();
sideMenu.addEventListener('keydown',e=>{if(!sideMenu.classList.contains('open'))return;if(e.key==='Escape'){e.preventDefault();closeNavigation(true)}if(e.key==='Tab'){const controls=[...sideMenu.querySelectorAll('button:not([hidden])')].filter(x=>x.getClientRects().length);const first=controls[0],last=controls.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}});
function updatePageChrome(name){const heading=document.querySelector('#view-'+name+' h1');document.querySelector('#current-page-title').textContent=heading?.textContent||'بديل';const wasOpen=sideMenu.classList.contains('open');closeNavigation();if(wasOpen)document.querySelector('#main-content').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'})}
function updateSchoolIdentity(){for(const id of ['header-school-name','sidebar-school-name'])document.getElementById(id).textContent=schoolSettings.school_name||'مساحة المدرسة'}
function syncScheduleDays(){const day=document.querySelector('#schedule-day').value;document.querySelectorAll('[data-schedule-day]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.scheduleDay===day)))}
document.querySelectorAll('[data-schedule-day]').forEach(b=>b.addEventListener('click',()=>{document.querySelector('#schedule-day').value=b.dataset.scheduleDay;document.querySelector('#schedule-day').dispatchEvent(new Event('change'));syncScheduleDays()}));
document.querySelector('#schedule-day').addEventListener('change',syncScheduleDays);
document.querySelector('#close-cell-dialog').addEventListener('click',()=>document.querySelector('#cell-dialog').close());

function personalScheduleMarkup(entries) {
  if(!entries.length)return '<div class="empty">لا يوجد جدول مسجل لك بعد</div>';
  return Object.keys(days).filter(day=>entries.some(x=>x.day_of_week===day)).map((day,index)=>{
    const lessons=entries.filter(x=>x.day_of_week===day).sort((a,b)=>a.period_number-b.period_number);
    const teaching=lessons.filter(x=>x.status==='TEACHING').length;
    return `<details class="personal-day" ${index===0?'open':''}><summary><span>${uiIcon('calendar')}<strong>${days[day]}</strong></span><small>${teaching} حصص تدريس</small>${uiIcon('chevron')}</summary><div class="personal-lessons">${lessons.map(x=>{
      const reserve=(x.notes||'').match(/RESERVE_PRIORITY:(\d+)/)?.[1];
      const label=reserve?`احتياط ح${reserve}`:statusLabel[x.status]||x.status;
      return `<article class="personal-lesson ${x.status==='FREE'?'available':''}"><div><span>الحصة ${x.period_number}</span><span class="status-pill ${x.status==='FREE'?'free':x.status==='DUTY'?'duty':'busy'}">${esc(label)}</span></div><strong>${esc(x.school_class?.name||(x.status==='FREE'?'متاح للاحتياط':'—'))}</strong><small>${esc(x.subject?.name||(reserve?'وفق أولوية جدول المدرسة':x.status==='FREE'?'بدون حصة تدريس':'بدون مادة مسجلة'))}</small></article>`;
    }).join('')}</div></details>`;
  }).join('');
}
function personalAssignmentsMarkup(assignments) {
  if(!assignments.length)return '<div class="empty">لا توجد تكليفات احتياط مسندة لك</div>';
  return `<div class="personal-assignments">${assignments.map(x=>`<article class="personal-assignment"><div class="personal-assignment-heading"><div><span class="eyebrow">${esc(x.date)}</span><h3>الحصة ${x.period_number} · الشعبة ${esc(x.school_class?.name||'—')}</h3></div><span class="status-pill ${esc(x.status.toLowerCase())}">${esc(statusLabel[x.status]||x.status)}</span></div><dl><div><dt>المعلم الغائب</dt><dd>${esc(x.absent_teacher?.name||'—')}</dd></div><div><dt>موقع الانتظار</dt><dd>${esc(x.waiting_location||'لم يُحدد')}</dd></div></dl>${x.notes?`<p class="personal-note">${esc(x.notes)}</p>`:''}</article>`).join('')}</div>`;
}
