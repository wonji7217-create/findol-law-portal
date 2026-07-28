const $ = (s) => document.querySelector(s);
let token = sessionStorage.getItem('findol_admin_token') || '';
let topics = [];

const api = async (path, options={}) => {
  const headers = {'Content-Type':'application/json','X-Admin-Token':token,...(options.headers||{})};
  const res = await fetch(path,{...options,headers});
  if (res.status === 401) { sessionStorage.removeItem('findol_admin_token'); token=''; $('#loginDialog').showModal(); throw new Error('관리자 토큰이 올바르지 않습니다.'); }
  const data = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error(data.detail || '요청에 실패했습니다.');
  return data;
};
const lines = (v) => (v||'').split('\n').map(x=>x.trim()).filter(Boolean);
const joinLines = (v) => (v||[]).join('\n');
const toast = (msg) => { const el=$('#toast'); el.textContent=msg; el.classList.add('show'); setTimeout(()=>el.classList.remove('show'),1800); };

function ruleRow(rule={}) {
  const node = $('#ruleTemplate').content.firstElementChild.cloneNode(true);
  node.querySelector('.rule-kind').value = rule.kind || 'admin_rule';
  node.querySelector('.rule-title').value = rule.title || '';
  node.querySelector('.rule-url').value = rule.official_url || '';
  node.querySelector('.remove-rule').onclick = () => node.remove();
  return node;
}
function setRules(id, items=[]) { const el=$(id); el.innerHTML=''; items.forEach(x=>el.append(ruleRow(x))); }
function getRules(id) { return [...$(id).querySelectorAll('.rule-row')].map(row=>({kind:row.querySelector('.rule-kind').value,title:row.querySelector('.rule-title').value.trim(),official_url:row.querySelector('.rule-url').value.trim()||null})).filter(x=>x.title); }

function resetForm() {
  $('#topicForm').reset(); $('#topicId').value=''; $('#priorityInput').value=50; $('#activeInput').checked=true;
  setRules('#primaryRules'); setRules('#upperLaws'); setRules('#relatedRules');
  $('#editorTitle').textContent='새 지식 주제'; $('#editorSubtitle').textContent='검색과 법령 연결에 필요한 내용을 입력하세요.'; $('#deleteBtn').hidden=true;
  document.querySelectorAll('.topic-card').forEach(x=>x.classList.remove('active'));
}
function fillForm(item) {
  $('#topicId').value=item.id; $('#topicKey').value=item.topic_key; $('#labelInput').value=item.label;
  $('#descriptionInput').value=item.description||''; $('#intentInput').value=item.intent_summary||'';
  $('#triggersInput').value=joinLines(item.triggers); $('#searchTermsInput').value=joinLines(item.search_terms);
  $('#checklistInput').value=joinLines(item.checklist); $('#tasksInput').value=joinLines(item.related_tasks);
  $('#notesInput').value=item.notes||''; $('#priorityInput').value=item.priority||50; $('#activeInput').checked=!!item.is_active;
  setRules('#primaryRules',item.primary_rules); setRules('#upperLaws',item.upper_laws); setRules('#relatedRules',item.related_rules);
  $('#editorTitle').textContent=item.label; $('#editorSubtitle').textContent=`${item.topic_key} · 검색어 ${item.triggers.length}개`; $('#deleteBtn').hidden=false;
  document.querySelectorAll('.topic-card').forEach(x=>x.classList.toggle('active',Number(x.dataset.id)===item.id));
  window.scrollTo({top:0,behavior:'smooth'});
}
function renderList() {
  const el=$('#topicList'); const keyword=$('#filterInput').value.trim().toLowerCase();
  const filtered=topics.filter(x=>!keyword || [x.label,x.topic_key,x.description,...x.triggers].join(' ').toLowerCase().includes(keyword));
  el.innerHTML='';
  filtered.forEach(item=>{ const b=document.createElement('button'); b.type='button'; b.className='topic-card'; b.dataset.id=item.id; b.innerHTML=`<div class="topic-meta"><strong>${item.label}</strong><span class="badge ${item.is_active?'on':''}">${item.is_active?'사용 중':'숨김'}</span></div><span>${item.topic_key}</span><span>${item.triggers.slice(0,4).join(' · ') || '등록된 검색어 없음'}</span>`; b.onclick=()=>fillForm(item); el.append(b); });
  if(!filtered.length) el.innerHTML='<p style="padding:20px;color:#73807b">일치하는 주제가 없습니다.</p>';
}
async function loadAll() {
  const [summary,list]=await Promise.all([api('/api/admin/summary'),api('/api/admin/knowledge')]);
  $('#topicCount').textContent=summary.topic_count; $('#activeCount').textContent=summary.active_count; $('#archiveCount').textContent=summary.archive_count;
  const syncStatus=$('#syncStatus');
  if (syncStatus) {
    syncStatus.textContent=summary.lawmaking_api_configured
      ? 'API 인증값이 설정되어 있습니다. 버튼을 누르면 최신 관련 예고를 확인합니다.'
      : 'Render 환경변수 LAWMAKING_API_OC가 아직 설정되지 않았습니다.';
    syncStatus.classList.toggle('warning',!summary.lawmaking_api_configured);
    $('#syncLawmakingBtn').disabled=!summary.lawmaking_api_configured;
  }
  topics=list.items; renderList();
}
function payload() { return {topic_key:$('#topicKey').value.trim(),label:$('#labelInput').value.trim(),description:$('#descriptionInput').value.trim(),intent_summary:$('#intentInput').value.trim(),triggers:lines($('#triggersInput').value),search_terms:lines($('#searchTermsInput').value),primary_rules:getRules('#primaryRules'),upper_laws:getRules('#upperLaws'),related_rules:getRules('#relatedRules'),checklist:lines($('#checklistInput').value),related_tasks:lines($('#tasksInput').value),notes:$('#notesInput').value.trim(),is_active:$('#activeInput').checked,priority:Number($('#priorityInput').value||50)}; }


$('#syncLawmakingBtn').onclick=async()=>{
  const btn=$('#syncLawmakingBtn');
  const status=$('#syncStatus');
  const payload={
    include_administrative:$('#syncAdministrative').checked,
    include_legislative:$('#syncLegislative').checked,
    max_items:Number($('#syncLimit').value||60),
  };
  if(!payload.include_administrative&&!payload.include_legislative){alert('행정예고 또는 입법예고 중 하나를 선택하세요.');return;}
  btn.disabled=true; btn.textContent='가져오는 중...'; status.classList.remove('warning');
  status.textContent='목록과 상세정보를 확인하고 있어요. 자료 수에 따라 잠시 걸릴 수 있습니다.';
  try{
    const result=await api('/api/admin/lawmaking/sync',{method:'POST',body:JSON.stringify(payload)});
    status.textContent=`확인 ${result.fetched}건 · 신규/변경 ${result.created_or_changed}건 · 기존과 동일 ${result.unchanged}건`;
    toast('국민참여입법센터 동기화를 마쳤습니다.');
    await loadAll();
  }catch(err){status.textContent=err.message;status.classList.add('warning');}
  finally{btn.disabled=false;btn.textContent='새 정보 가져오기';}
};

$('#loginForm').addEventListener('submit',async e=>{e.preventDefault(); token=$('#tokenInput').value.trim(); try{await api('/api/admin/summary'); sessionStorage.setItem('findol_admin_token',token); $('#loginError').textContent=''; $('#loginDialog').close(); await loadAll();}catch(err){$('#loginError').textContent=err.message;}});
$('#topicForm').addEventListener('submit',async e=>{e.preventDefault(); const id=$('#topicId').value; try{await api(id?`/api/admin/knowledge/${id}`:'/api/admin/knowledge',{method:id?'PUT':'POST',body:JSON.stringify(payload())}); toast('저장했습니다. 검색에 즉시 반영됩니다.'); await loadAll(); if(id){const item=topics.find(x=>x.id===Number(id)); if(item) fillForm(item);} else resetForm();}catch(err){alert(err.message);}});
$('#deleteBtn').onclick=async()=>{const id=$('#topicId').value;if(!id||!confirm('이 지식 주제를 삭제할까요?'))return;try{await api(`/api/admin/knowledge/${id}`,{method:'DELETE'});toast('삭제했습니다.');resetForm();await loadAll();}catch(err){alert(err.message);}};
$('#newBtn').onclick=resetForm; $('#resetBtn').onclick=resetForm; $('#filterInput').oninput=renderList;
$('#logoutBtn').onclick=()=>{sessionStorage.removeItem('findol_admin_token');token='';$('#tokenInput').value='';$('#loginDialog').showModal();};
document.querySelectorAll('[data-add-rule]').forEach(btn=>btn.onclick=()=>{const map={primary:'#primaryRules',upper:'#upperLaws',related:'#relatedRules'};$(map[btn.dataset.addRule]).append(ruleRow());});

if(!token) $('#loginDialog').showModal(); else loadAll().catch(err=>{console.error(err);$('#loginDialog').showModal();});
