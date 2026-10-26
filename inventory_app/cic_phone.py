"""Quantity-first bag-drag phone questionnaire served by Python."""
PHONE_HTML=r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Det005 - A.C.E. Cadet Inventory Card</title><style>
body{margin:0;background:#eef2f6;color:#102638;font:16px Arial}header{background:#0c2340;color:white;padding:22px}main{max-width:800px;margin:auto;padding:16px}section{background:white;border-radius:8px;padding:20px;margin:14px 0}h1{font-size:24px;margin:0}h2{font-size:21px}label{display:block;margin:14px 0}input,select,textarea,button{font:inherit;box-sizing:border-box;padding:12px;width:100%;border:1px solid #9aaab5;border-radius:5px}button{background:#0c2340;color:white;margin-top:10px;cursor:pointer;min-height:46px}button:disabled{opacity:.5}.secondary{background:#eaf1f7;color:#0c2340}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.hint{font-size:14px;color:#4b5d6b}.notice{padding:14px;background:#fff2d6;border-left:5px solid #e87722;white-space:pre-line}.hidden{display:none}.count{display:grid;grid-template-columns:1fr 95px;gap:15px;align-items:center}.item{padding:14px 0;border-bottom:1px solid #ddd}.step{font-size:14px;color:#506579;font-weight:bold}#message:empty{display:none}@media(max-width:500px){.row{grid-template-columns:1fr}}@media print{button,header,#message{display:none}}
</style><header><h1>Det005 Cadet Inventory Card</h1><p>A.C.E. bag drag: what do you currently possess?</p></header><main><div id="message" class="notice" role="status">Connecting...</div>
<section id="join" class="hidden"><h2>Join the Det005 session</h2><label>Six-digit code shown by ACE staff<input id="joinCode" inputmode="numeric" maxlength="6" pattern="[0-9]{6}" autocomplete="off"></label><button id="joinButton">Connect</button></section>
<section id="wizard" class="hidden"><div id="progress" class="step"></div><div id="screen"></div><div class="row"><button id="back" class="secondary">Back</button><button id="next">Next</button></div></section>
<section id="receipt" class="hidden"><h2>Your Cadet Inventory Card</h2><p id="receiptStatus"></p><div id="receiptCounts"></div><div id="receiptLines"></div><button id="refresh" class="secondary">Check review status</button><button id="downloadCard">Download my card</button><button id="downloadWings" class="hidden">Download approved WINGS workbook</button><p class="hint">Close this page on a shared phone. The workbook is for cadre review, not proof of a new official WINGS issue. Local or unverified IDs block that export.</p></section></main><script>
'use strict';
const el=id=>document.getElementById(id);
let token=location.hash.slice(1)||sessionStorage.getItem('aceCicSession')||'';
if(token)sessionStorage.setItem('aceCicSession',token);history.replaceState(null,'',location.pathname);
let catalog=[],questions=[],families=[],counts={},allocations={},step=0,busy=false,saved=null;
let person={last:'',first:'',mi:'',email:'',notes:''};
try{saved=JSON.parse(sessionStorage.getItem('aceCicReceipt')||'null')}catch(e){}
const randomHex=()=>Array.from(crypto.getRandomValues(new Uint8Array(32)),x=>x.toString(16).padStart(2,'0')).join('');
const requestId=crypto.randomUUID?crypto.randomUUID():'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{let r=crypto.getRandomValues(new Uint8Array(1))[0]%16;return(c==='x'?r:r&3|8).toString(16)}),receiptToken=randomHex();
function message(s){el('message').textContent=s}
function element(tag,value,parent,cls){let n=document.createElement(tag);if(value!==undefined)n.textContent=value;if(cls)n.className=cls;if(parent)parent.append(n);return n}
function field(parent,label,id,value,type='text'){let w=element('label',label,parent),n=element('input',undefined,w);n.id=id;n.type=type;n.value=value;return n}
async function api(path,opts={},secret=token){let r=await fetch(path,{...opts,headers:{Authorization:'Bearer '+secret,'Content-Type':'application/json'}}),d=await r.json();if(!r.ok)throw Error(d.error||'ACE is unavailable');return d}
function active(){return questions.filter(q=>counts[q.id]>0)}
function assigned(q){return (allocations[q.id]||[]).reduce((n,x)=>n+x.quantity,0)}
function lines(){return active().flatMap(q=>(allocations[q.id]||[]).map(x=>({...x,group:q.id})))}
function remember(){
 if(step===0){for(let k of ['last','first','mi','email'])person[k]=el(k).value.trim();if(!person.last||!person.first||!person.email)throw Error('Enter last name, first name and email. Middle initial is optional.');if(!/^[^@\s]+@[^@\s]+$/.test(person.email))throw Error('Enter a valid email address.')}
 else if(step<=families.length){for(let q of questions.filter(q=>q.family===families[step-1])){let n=Number(el('count-'+q.id).value);if(!Number.isInteger(n)||n<0||n>100)throw Error('Use whole counts from 0 through 100.');if(n!==counts[q.id])allocations[q.id]=[];counts[q.id]=n}if(Object.values(counts).reduce((a,b)=>a+b,0)>500)throw Error('Maximum 500 items per card. Ask staff for help.')}
}
function show(){
 let screen=el('screen');screen.replaceChildren();message('');el('back').disabled=step===0||busy;el('next').disabled=busy;el('next').textContent='Next';
 let sizeStep=families.length+1,reviewStep=sizeStep+1;
 el('progress').textContent='Step '+(step+1)+' of '+(reviewStep+1)+' | '+(step===0?'Cadet identity':step<=families.length?'Item quantities':step===sizeStep?'Sizes and exact items':'Review and submit');
 if(step===0){
  element('h2','Your information',screen);element('p','First, tell us who you are. You will count items before entering any sizes.',screen);
  field(screen,'Last name','last',person.last).autocomplete='family-name';field(screen,'Middle initial (optional)','mi',person.mi).maxLength=3;field(screen,'First name','first',person.first).autocomplete='given-name';field(screen,'Email','email',person.email,'email').autocomplete='email';
  element('p','No SSNs or private medical information. Staff must approve your card. Submitting does not change inventory or issue anything in WINGS.',screen,'hint');
 }else if(step<=families.length){
  let family=families[step-1];element('h2','How many '+family+' items do you have?',screen);element('p','Count only items currently in your possession. Leave 0 for items you do not have. We will ask sizes afterwards.',screen);
  let none=element('button','I have no '+family+' items',screen,'secondary');none.onclick=()=>{for(let q of questions.filter(q=>q.family===family)){counts[q.id]=0;allocations[q.id]=[]}step++;show()};
  for(let q of questions.filter(q=>q.family===family)){let n=field(screen,q.label,'count-'+q.id,counts[q.id]||0,'number');n.min=0;n.max=100;n.step=1;n.parentElement.className='count'}
  element('p','Count boots and shoes in pairs. Count garments individually. Confirm the issue unit shown at the size-selection step for items sold as pairs.',screen,'hint');
 }else if(step===sizeStep){
  element('h2','Now, what sizes are those items?',screen);element('p','Select the exact uniform type and size. For different sizes, add each size separately until every count is assigned.',screen);
  if(!active().length)element('p','You reported no uniform items. Continue to review and confirm that declaration.',screen);
  for(let q of active()){
   let box=element('div',undefined,screen,'item');element('h3',q.label+' | '+assigned(q)+' of '+counts[q.id]+' assigned',box);
   for(let [i,x] of (allocations[q.id]||[]).entries()){element('p',x.name+' / '+x.size+' x '+x.quantity+(x.item_no?'':' (HELD: unmatched item)'),box);let b=element('button','Remove this size',box,'secondary');b.onclick=()=>{allocations[q.id].splice(i,1);show()}}
   let remaining=counts[q.id]-assigned(q);if(remaining<=0)continue;
   element('p',remaining+' still need sizes / item details.',box,'hint');let options=catalog.filter(x=>x.group===q.id);
   let w=element('label','Exact uniform type and size',box),select=element('select',undefined,w);select.id='size-'+q.id;
   element('option','Select exact size and type',select).value='';
   options.sort((a,b)=>(a.name+' '+a.size).localeCompare(b.name+' '+b.size)).forEach(x=>{let o=element('option',x.name+' | '+x.size+' | '+(x.sex||'Unisex / unspecified')+' | '+x.item_no+(x.official?'':' (LOCAL)')+' | '+(x.uom||'EA'),select);o.value=x.item_no});
   let qty=field(box,'How many of this size?','sizeQty-'+q.id,remaining,'number');qty.min=1;qty.max=remaining;
   let b=element('button','Add this size',box);b.id='add-'+q.id;b.onclick=()=>{try{let x=options.find(x=>x.item_no===select.value),n=Number(qty.value);if(!x)throw Error('Select an exact item and size.');if(!Number.isInteger(n)||n<1||n>remaining)throw Error('Size count must be between 1 and '+remaining);(allocations[q.id]??=[]).push({item_no:x.item_no,name:x.name,size:x.size,quantity:n});show()}catch(e){message(e.message)}};
   let missing=element('details',undefined,box);element('summary','My item / size is missing or spelled incorrectly',missing);element('p','This card will be Held until ACE staff creates or corrects the index and maps this line.',missing,'hint');
   let desc=field(missing,'Description','unknown-'+q.id,q.label),size=field(missing,'Size or marking','unknownSize-'+q.id,'');
   let unknown=element('button','Record unresolved size (card will be held)',missing,'secondary');unknown.onclick=()=>{try{let n=Number(qty.value);if(!desc.value.trim()||!size.value.trim())throw Error('Enter a description and size / marking. Use One Size where applicable.');if(!Number.isInteger(n)||n<1||n>remaining)throw Error('Check the size count.');(allocations[q.id]??=[]).push({item_no:'',name:desc.value.trim(),size:size.value.trim(),quantity:n});show()}catch(e){message(e.message)}};
  }
 }else{
  element('h2','Review your inventory card',screen);element('p',person.last+', '+(person.mi?person.mi+', ':'')+person.first+' | '+person.email,screen);
  for(let family of families){let group=questions.filter(q=>q.family===family&&counts[q.id]>0);element('h3',family,screen);if(!group.length)element('p','None',screen);for(let q of group){element('p',q.label+': '+counts[q.id],screen);for(let x of allocations[q.id]||[])element('p',x.size+' | '+x.name+' x '+x.quantity+(x.item_no?'':' | HOLD: not matched'),screen,'hint')}}
  let w=element('label','Notes (optional)',screen),note=element('textarea',undefined,w);note.id='notes';note.maxLength=1000;note.value=person.notes;note.oninput=()=>person.notes=note.value;
  let label=element('label',undefined,screen),check=element('input',undefined,label);check.type='checkbox';check.id='confirm';check.style.width='auto';label.append(document.createTextNode(' I verified all counts, sizes and None answers. These are the uniform items currently in my possession.'));
  el('next').textContent='Submit for staff approval';
 }
}
el('back').onclick=()=>{try{if(step>0&&step<=families.length)remember();step=Math.max(0,step-1);show()}catch(e){message(e.message)}};
el('next').onclick=async()=>{try{
 remember();let sizeStep=families.length+1,reviewStep=sizeStep+1;
 if(step===sizeStep&&active().some(q=>assigned(q)!==counts[q.id]))throw Error('Assign sizes to every counted item before continuing.');
 if(step<reviewStep){step++;show();return}
 if(!el('confirm').checked)throw Error('Confirm that your card and None answers are correct.');if(busy)return;busy=true;el('next').disabled=true;
 let name=person.last+', '+(person.mi?person.mi+', ':'')+person.first;
 let d=await api('/api/cards',{method:'POST',body:JSON.stringify({name,email:person.email,notes:person.notes,request_id:requestId,receipt_token:receiptToken,assessment:counts,lines:lines(),no_items:lines().length===0})});
 saved={id:d.card_id,token:receiptToken};sessionStorage.setItem('aceCicReceipt',JSON.stringify(saved));await receipt();
 }catch(e){message(e.message)}finally{busy=false;el('next').disabled=false}};
async function receipt(){try{
 let d=await api('/api/cards/'+saved.id,{},saved.token);el('wizard').classList.add('hidden');el('join').classList.add('hidden');el('receipt').classList.remove('hidden');el('receiptStatus').textContent='Card '+d.card_id+' | '+d.status;el('receiptLines').replaceChildren();el('receiptCounts').replaceChildren();
 let assessment=JSON.parse(d.assessment_json||'{}');for(let family of families){let group=questions.filter(q=>q.family===family);element('p',family+': '+group.reduce((n,q)=>n+(assessment[q.id]||0),0)+' item(s)',el('receiptCounts'))}
 for(let x of d.lines)element('p',x.entered_name+' / '+x.entered_size+' x '+x.quantity+(x.problem?' | HOLD: '+x.problem:''),el('receiptLines'));
 el('downloadWings').classList.toggle('hidden',d.status!=='Approved');
 message(d.status==='Held'?'Held: ACE staff must fix the unresolved item or size before approval.':d.status==='Approved'?'Approved. Your copy is available below.':d.status==='Rejected'?'Card was not approved. Contact ACE staff.':'Submitted. Waiting for staff approval; inventory has not changed.');
 }catch(e){message(e.message+' Keep this page open and ask staff for help.')}}
async function download(kind,name){try{let r=await fetch('/api/cards/'+saved.id+'/'+kind,{headers:{Authorization:'Bearer '+saved.token}});if(!r.ok)throw Error((await r.json()).error);let url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000)}catch(e){message(e.message)}}
el('refresh').onclick=receipt;el('downloadCard').onclick=()=>download('copy','ACE_CIC_'+saved.id+'.html');el('downloadWings').onclick=()=>download('wings','ACE_CIC_WINGS_'+saved.id+'.xlsx');
el('joinButton').onclick=async()=>{try{token=(await api('/api/join',{method:'POST',body:JSON.stringify({code:el('joinCode').value.trim()})})).token;sessionStorage.setItem('aceCicSession',token);await start()}catch(e){message(e.message)}};
async function start(){
 if(saved){await receipt();return}
 if(!token){el('join').classList.remove('hidden');el('wizard').classList.add('hidden');message('Enter the session code supplied by ACE staff.');return}
 try{[catalog,questions]=await Promise.all([api('/api/catalog'),api('/api/questions')]);families=[...new Set(questions.map(q=>q.family))];for(let q of questions)counts[q.id]??=0;el('join').classList.add('hidden');el('wizard').classList.remove('hidden');show()}
 catch(e){message(e.message);token='';sessionStorage.removeItem('aceCicSession');el('join').classList.remove('hidden');el('wizard').classList.add('hidden')}
}
start();
</script></html>'''
