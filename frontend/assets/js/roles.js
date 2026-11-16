// Role editor and access-aware navigation. The API enforces every permission too.
let roleCatalog = {catalog: [], roles: [], builtins: [], dependencies: {}}, staffRows = [];
let currentPermissions = new Set();
const viewPermissions = {dashboard:'dashboard.view',assistant:'assistant.use',schedule:'schedule.view',substitutions:'substitutions.view',teachers:'directory.view',reports:'reports.view',settings:'settings.manage',audit:'audit.view',roles:'manager',staff:'manager'};
function can(permission) { return currentRole === 'MANAGER' || currentPermissions.has(permission); }
function canView(name) { return name === 'my-work' || can(viewPermissions[name] || 'manager'); }
function roleValue(item) { return item.role === 'CUSTOM' ? 'custom:'+item.custom_role_id : item.role; }
function rolePayload(value) { return value.startsWith('custom:') ? {role:'CUSTOM',custom_role_id:Number(value.slice(7))} : {role:value,custom_role_id:null}; }
function roleOptions(selected='TEACHER') {
  return [...roleCatalog.builtins.map(r=>({value:r.key,name:r.name})),...roleCatalog.roles.map(r=>({value:'custom:'+r.id,name:r.name}))]
    .map(r=>`<option value="${esc(r.value)}" ${r.value===selected?'selected':''}>${esc(r.name)}</option>`).join('');
}
function applyPermissionControls() {
  document.querySelectorAll('[data-permission]').forEach(el=>el.hidden=!can(el.dataset.permission));
  document.querySelectorAll('[data-open]').forEach(el=>el.hidden=!canView(el.dataset.open));
  document.querySelectorAll('[data-open-import]').forEach(el=>el.hidden=!can('schedule.view'));
  document.querySelectorAll('[data-action]').forEach(el=>{
    const p=['assign','review','confirm','complete','cancel'].includes(el.dataset.action)?'substitutions.manage':el.dataset.action==='toggle-teacher'?'directory.edit':null;
    if(p)el.hidden=!can(p);
  });
  document.querySelectorAll('.cell-edit').forEach(el=>{el.disabled=!can('schedule.edit');el.setAttribute('aria-label',(can('schedule.edit')?'تعديل':'عرض')+' الحصة '+el.dataset.period+' للمعلم '+(el.closest('tr')?.dataset.teacherName||''))});
}
function renderStaffRows() {
  const query=document.querySelector('#staff-search').value.trim().toLocaleLowerCase();
  const rows=staffRows.filter(x=>[x.teacher_name,x.username,x.email,x.role_name].some(v=>String(v).toLocaleLowerCase().includes(query)));
  document.querySelector('#staff-list').innerHTML=rows.length?`<div class="table-wrap"><table><thead><tr><th>الموظف</th><th>الدور والصلاحيات</th><th>الحالة</th><th>الإجراءات</th></tr></thead><tbody>${rows.map(x=>`<tr><td><div class="person-cell"><span class="person-avatar" aria-hidden="true">${esc(x.teacher_name.slice(0,1))}</span><div><strong>${esc(x.teacher_name)}</strong><small><bdi>${esc(x.username)}</bdi> · <bdi>${esc(x.email)}</bdi></small></div></div></td><td><select aria-label="دور ${esc(x.teacher_name)}" id="staff-role-${x.id}">${roleOptions(roleValue(x))}</select></td><td><span class="status-pill ${x.is_active?'ready':'suggested'}">${x.is_active?'نشط':x.invite_expires_at?'دعوة مرسلة':'موقوف'}</span></td><td><div class="row-actions"><button class="button secondary" data-action="update-staff-role" data-staff-id="${x.id}">حفظ الدور</button>${x.is_active?`<button class="text-button danger-text" data-action="deactivate-staff" data-staff-id="${x.id}">إيقاف</button>`:`<button class="text-button" data-action="resend-staff-invite" data-staff-id="${x.id}">إرسال دعوة</button>`}</div></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty"><strong>${query?'لا توجد نتائج مطابقة':'فريق مدرستك يبدأ من هنا'}</strong><p>${query?'جرّب اسمًا أو بريدًا آخر.':'اختر المعلم ودوره وأرسل إليه دعوة للانضمام.'}</p></div>`;
  document.querySelector('#staff-total').textContent=staffRows.length;
  document.querySelector('#staff-active').textContent=staffRows.filter(x=>x.is_active).length;
  document.querySelector('#staff-pending').textContent=staffRows.filter(x=>!x.is_active&&x.invite_expires_at).length;
}
async function loadRoles() {
  const newButton=document.querySelector('#view-roles [data-new-role]');newButton.disabled=true;const target=document.querySelector('#roles-list');target.innerHTML=loadingMarkup('جارٍ تحميل الأدوار');
  try {roleCatalog=await req('/roles');renderRoles();newButton.disabled=false;} catch(e){setLoadError('#roles-list',e,loadRoles)}
}
function renderRoles() {
  document.querySelector('#roles-count').textContent=roleCatalog.roles.length;
  const cards=roleCatalog.roles.map(role=>`<article class="role-card"><div class="role-card-top"><span class="role-symbol" aria-hidden="true">◈</span><span class="status-pill">${role.member_count} موظف</span></div><h2>${esc(role.name)}</h2><p>${esc(role.description||'دور مخصص للمدرسة')}</p><div class="permission-chips">${role.permissions.slice(0,3).map(key=>`<span>${esc(roleCatalog.catalog.find(p=>p.key===key)?.label||key)}</span>`).join('')}${role.permissions.length>3?`<span>+${role.permissions.length-3}</span>`:''}${!role.permissions.length?'<span>الجدول والتكليفات الشخصية فقط</span>':''}</div><div class="role-card-footer"><button class="button secondary" data-edit-role="${role.id}">تعديل الصلاحيات</button><button class="text-button danger-text" data-delete-role="${role.id}" ${role.member_count?'disabled title="غيّر أدوار الموظفين المرتبطين أولًا"':''}>حذف</button></div></article>`);
  document.querySelector('#roles-list').innerHTML=cards.length?cards.join(''):'<div class="empty role-empty"><strong>صمّم الدور المناسب لفريقك</strong><p>مثل «مسؤول التقارير» أو «مشرف الجدول». حدّد الصلاحيات ثم وزّع الدور من حسابات الموظفين.</p><button class="button primary" data-new-role>إنشاء أول دور</button></div>';
  document.querySelector('#builtin-roles').innerHTML=[{name:'مدير المدرسة',description:'صلاحيات كاملة وإدارة الأدوار وحسابات الفريق.'},{name:'منسق',description:'الغياب والاحتياط والتقارير؛ دون تعديل الجدول أو الحسابات.'},{name:'معلم',description:'جدوله وتكليفاته الشخصية فقط.'}].map(r=>`<div class="builtin-role"><strong>${r.name}<span>جاهز</span></strong><p>${r.description}</p></div>`).join('');
}
function selectedRolePermissions() {return [...document.querySelectorAll('#permission-grid input:checked')].map(x=>x.value)}
function expandedPermissions(keys) {const result=new Set(keys);let changed=true;while(changed){changed=false;for(const key of result)for(const dep of roleCatalog.dependencies[key]||[])if(!result.has(dep)){result.add(dep);changed=true}}return result}
function updatePermissionSummary() {
  const chosen=selectedRolePermissions();
  document.querySelector('#permission-count').textContent=`${chosen.length} من ${roleCatalog.catalog.length} صلاحية`;
  document.querySelector('#role-summary').textContent=chosen.length?`هذا الدور يستطيع ${roleCatalog.catalog.filter(p=>chosen.includes(p.key)).map(p=>p.label).join('، ')}.`:'يستطيع الموظف عرض جدوله وتكليفاته الشخصية فقط.';
}
function openRoleEditor(id=null) {
  const role=roleCatalog.roles.find(x=>x.id===id);
  document.querySelector('#role-form').reset();document.querySelector('#role-id').value=role?.id||'';
  document.querySelector('#role-name').value=role?.name||'';document.querySelector('#role-description').value=role?.description||'';
  document.querySelector('#role-dialog-title').textContent=role?'تعديل الدور':'إنشاء دور مخصص';
  document.querySelector('#role-form-error').hidden=true;
  const groups=[...new Set(roleCatalog.catalog.map(p=>p.group))];
  document.querySelector('#permission-grid').innerHTML=groups.map(group=>`<fieldset><legend>${esc(group)}</legend>${roleCatalog.catalog.filter(p=>p.group===group).map(p=>`<label class="permission-option"><input type="checkbox" value="${p.key}" ${(role?.permissions||[]).includes(p.key)?'checked':''}><span><strong>${esc(p.label)}</strong><small>${esc(p.description)}</small></span></label>`).join('')}</fieldset>`).join('');
  updatePermissionSummary();document.querySelector('#role-dialog').showModal();document.querySelector('#role-name').focus();
}
document.querySelector('#permission-grid').addEventListener('change',event=>{
  const checks=[...document.querySelectorAll('#permission-grid input')],changed=event.target;
  if(changed.checked){const expanded=expandedPermissions(selectedRolePermissions());checks.forEach(c=>c.checked=expanded.has(c.value))}
  else checks.forEach(c=>{if(expandedPermissions([c.value]).has(changed.value))c.checked=false});
  updatePermissionSummary();
});
document.querySelector('#role-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=document.querySelector('#save-role'),error=document.querySelector('#role-form-error');button.disabled=true;error.hidden=true;
  const id=document.querySelector('#role-id').value;
  try {await req('/roles'+(id?'/'+id:''),{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.querySelector('#role-name').value,description:document.querySelector('#role-description').value,permissions:selectedRolePermissions()})});document.querySelector('#role-dialog').close();await loadRoles();notify('تم حفظ الدور وصلاحياته. تسري التغييرات على الطلبات التالية للموظفين المرتبطين به.');}
  catch(e){error.textContent=e.message;error.hidden=false;}finally{button.disabled=false}
});
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-new-role],[data-edit-role],[data-delete-role],[data-close-role]');if(!button)return;
  if(button.hasAttribute('data-close-role'))return document.querySelector('#role-dialog').close();
  if(button.hasAttribute('data-new-role'))return openRoleEditor();
  if(button.dataset.editRole)return openRoleEditor(Number(button.dataset.editRole));
  const role=roleCatalog.roles.find(x=>x.id===Number(button.dataset.deleteRole));
  if(!role||!confirm(`حذف الدور «${role.name}»؟`))return;
  button.disabled=true;
  try{await req('/roles/'+role.id,{method:'DELETE'});await loadRoles();notify('تم حذف الدور');}catch(e){notify(e.message,true);button.disabled=false}
});
document.querySelector('#staff-search').addEventListener('input',renderStaffRows);
new MutationObserver(applyPermissionControls).observe(document.querySelector('#app-shell'),{childList:true,subtree:true});
