"""Cadet Inventory Cards: durable intake and atomic, staff-approved reconciliation."""
from collections import Counter
from contextlib import closing
from datetime import datetime
import hashlib
import json
import secrets
import uuid
from pathlib import Path
from .catalog_inventory import item_key

CIC_SCHEMA='''
CREATE TABLE IF NOT EXISTS cic_cards (
 card_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, request_id TEXT NOT NULL,
 receipt_hash TEXT NOT NULL, cadet_name TEXT NOT NULL, cadet_email TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('Pending','Held','Approved','Rejected')),
 submitted_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 cadet_id INTEGER REFERENCES cadets(cadet_id), approved_by TEXT NOT NULL DEFAULT '',
 approved_at TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', assessment_json TEXT NOT NULL DEFAULT '{}',
 intake_issues_json TEXT NOT NULL DEFAULT '[]',
 UNIQUE(session_id,request_id)
);
CREATE TABLE IF NOT EXISTS cic_lines (
 line_id INTEGER PRIMARY KEY, card_id TEXT NOT NULL REFERENCES cic_cards(card_id),
 item_no TEXT NOT NULL DEFAULT '', entered_name TEXT NOT NULL DEFAULT '',
 entered_size TEXT NOT NULL DEFAULT '', quantity INTEGER NOT NULL CHECK(quantity>0),
 problem TEXT NOT NULL DEFAULT '', barcode_id TEXT NOT NULL DEFAULT '',
 existing_quantity INTEGER NOT NULL DEFAULT 0, added_quantity INTEGER NOT NULL DEFAULT 0,
 transaction_ids TEXT NOT NULL DEFAULT '[]', group_key TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cic_events (
 event_id INTEGER PRIMARY KEY, card_id TEXT NOT NULL REFERENCES cic_cards(card_id),
 event_time TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL
);
'''

def now():return datetime.now().astimezone().isoformat(timespec='seconds')
def fail(message):
    from .services import InventoryError
    raise InventoryError(message)
def norm(value):return ' '.join(str(value or '').casefold().split())
def receipt_hash(token):return hashlib.sha256(token.encode()).hexdigest()
def name_key(name):
    parts=[norm(p) for p in name.split(',')]
    return (parts[0],parts[-1]) if len(parts)>1 else (norm(name),'')


class CicServiceMixin:
    def cic_catalog(self):
        from .cic_questions import question_for
        return [{'item_no':r['item_no'],'name':r['item_name'],'size':r['size'],
                 'category':r['category'],'sex':r['sex'],'official':bool(r['is_wings']),
                 'group':question_for(r),'uom':r['uom']}
                for r in self.list_wings_catalog()]

    def _cic_catalog(self,c):
        return {item_key(r['item_no']):dict(r) for r in c.execute('''SELECT * FROM wings_catalog w
          WHERE NOT EXISTS(SELECT 1 FROM hidden_index_items h WHERE h.item_no=w.item_no)
          AND item_no NOT LIKE 'LOCAL-RANK-SB-%' ''')}

    def _cic_revalidate(self,c,card_id):
        card=c.execute('SELECT * FROM cic_cards WHERE card_id=?',(card_id,)).fetchone()
        if card is None:fail('Card not found.')
        if card['status'] in ('Approved','Rejected'):return
        catalog=self._cic_catalog(c);problems=json.loads(card['intake_issues_json'])
        for line in c.execute('SELECT * FROM cic_lines WHERE card_id=?',(card_id,)).fetchall():
            cat=catalog.get(item_key(line['item_no']))
            problem=''
            if cat is None:problem='Item ID is missing, hidden, or not in the ACE index. Correct or create an item in ACE and map this line.'
            elif norm(cat['item_name'])!=norm(line['entered_name']) or norm(cat['size'])!=norm(line['entered_size']):
                problem='Item name or size does not exactly match the index. Staff must confirm the correct item.'
            c.execute('UPDATE cic_lines SET problem=? WHERE line_id=?',(problem,line['line_id']))
            if problem:problems.append(problem)
        c.execute('UPDATE cic_cards SET status=?,updated_at=? WHERE card_id=?',('Held' if problems else 'Pending',now(),card_id))

    def submit_cic(self, payload, *, session_id, intake_issues=None):
        if not isinstance(payload,dict):fail('Card must be a JSON object.')
        name,email=self._validate_cadet_identity(str(payload.get('name',''))[:200],str(payload.get('email',''))[:254])
        request=str(payload.get('request_id',''))
        try:uuid.UUID(request)
        except (ValueError,AttributeError):fail('A valid request ID is required.')
        lines=payload.get('lines')
        if not isinstance(lines,list) or len(lines)>100 or (not lines and payload.get('no_items') is not True):fail('Include item lines or explicitly confirm you possess no uniform items.')
        cleaned=[]
        for line in lines:
            if not isinstance(line,dict):fail('Invalid item line.')
            qty=line.get('quantity')
            if type(qty) is not int or not 1<=qty<=100:fail('Each item quantity must be a whole number from 1 to 100.')
            cleaned.append((str(line.get('item_no',''))[:100],str(line.get('name',''))[:200],str(line.get('size',''))[:100],qty,str(line.get('group',''))[:100]))
        if sum(x[3] for x in cleaned)>500:fail('A card cannot declare more than 500 items.')
        assessment=payload.get('assessment',{})
        if not isinstance(assessment,dict):fail('Invalid quantity questionnaire.')
        if assessment:
            from .cic_questions import QUESTIONS
            expected={q[0] for q in QUESTIONS}
            if set(assessment)!=expected or any(type(v) is not int or not 0<=v<=100 for v in assessment.values()):fail('Answer every quantity question with a whole number from 0 to 100.')
            actual=Counter()
            for line in cleaned:actual[line[4]]+=line[3]
            if any(actual[k]!=v for k,v in assessment.items()) or any(k not in expected for k in actual):fail('Size quantities must exactly equal your earlier item counts. Go back and correct the card.')
        token=str(payload.get('receipt_token',''))
        if len(token)<32 or len(token)>100:fail('A private receipt token is required.')
        stamp=now();card_id=str(uuid.uuid4())
        with closing(self.database.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT card_id,receipt_hash FROM cic_cards WHERE session_id=? AND request_id=?',(session_id,request)).fetchone()
            if old:
                if not secrets.compare_digest(old['receipt_hash'],receipt_hash(token)):fail('Request ID already used.')
                return self._cic_card(c,old['card_id'])
            pending=c.execute("SELECT COUNT(*) FROM cic_cards WHERE status IN ('Pending','Held')").fetchone()[0]
            if pending>=1000:fail('Intake queue is full. Ask staff to review submitted cards.')
            c.execute('''INSERT INTO cic_cards(card_id,session_id,request_id,receipt_hash,cadet_name,cadet_email,status,submitted_at,updated_at,notes,assessment_json,intake_issues_json)
             VALUES(?,?,?,?,?,?,'Pending',?,?,?,?,?)''',(card_id,session_id,request,receipt_hash(token),name,email,stamp,stamp,str(payload.get('notes',''))[:1000],json.dumps(assessment),json.dumps(intake_issues or [])))
            c.executemany('INSERT INTO cic_lines(card_id,item_no,entered_name,entered_size,quantity,group_key) VALUES(?,?,?,?,?,?)',[(card_id,*x) for x in cleaned])
            self._cic_revalidate(c,card_id)
            self._cic_event(c,card_id,'Submitted','Phone intake','No stock, cadet profiles, or checkouts changed.')
            c.commit();result=self._cic_card(c,card_id)
        self.database.note_write();return result

    def _cic_event(self,c,card,action,actor,details):
        c.execute('INSERT INTO cic_events(card_id,event_time,action,actor,details) VALUES(?,?,?,?,?)',(card,now(),action,actor,details))

    def _cic_card(self,c,card_id):
        row=c.execute('SELECT * FROM cic_cards WHERE card_id=?',(card_id,)).fetchone()
        if row is None:fail('Card not found.')
        result=dict(row);result.pop('receipt_hash',None)
        result['lines']=[dict(r) for r in c.execute('SELECT * FROM cic_lines WHERE card_id=? ORDER BY line_id',(card_id,))]
        return result

    def get_cic(self,card_id):
        with closing(self.database.connect()) as c:return self._cic_card(c,card_id)

    def list_cic(self,search=''):
        with closing(self.database.connect()) as c:
            return [dict(r) for r in c.execute('''SELECT card_id,cadet_name,cadet_email,status,submitted_at,cadet_id,version
             FROM cic_cards WHERE cadet_name LIKE ? OR cadet_email LIKE ? ORDER BY submitted_at DESC''',('%'+search+'%','%'+search+'%'))]

    def cic_candidates(self,card_id):
        card=self.get_cic(card_id);key=name_key(card['cadet_name'])
        return [dict(r,match_reason='Exact email' if norm(r['email'])==norm(card['cadet_email']) else 'Same first and last name')
                for r in self.list_cadets() if norm(r['email'])==norm(card['cadet_email']) or name_key(r['full_name'])==key]

    def map_cic_line(self,card_id,line_id,item_no,*,approved_by):
        actor=self._normalize_admin_identity(approved_by)['label']
        with closing(self.database.connect()) as c:
            c.execute('BEGIN IMMEDIATE');card=self._cic_card(c,card_id)
            if card['status'] not in ('Held','Pending'):fail('Only pending or held cards can be corrected.')
            if not any(r['line_id']==line_id for r in card['lines']):fail('Line does not belong to this card.')
            cat=self._cic_catalog(c).get(item_key(item_no))
            if cat is None:fail('Choose an existing visible ACE catalog item.')
            c.execute('UPDATE cic_lines SET item_no=?,entered_name=?,entered_size=? WHERE card_id=? AND line_id=?',
                      (cat['item_no'],cat['item_name'],cat['size'],card_id,line_id))
            c.execute('UPDATE cic_cards SET version=version+1 WHERE card_id=?',(card_id,))
            self._cic_revalidate(c,card_id)
            self._cic_event(c,card_id,'Line mapped',actor,f"Line {line_id} confirmed as {cat['item_no']}: {cat['item_name']} / {cat['size']}")
            c.commit()
        self.database.note_write()

    def revalidate_cic(self,card_id):
        with closing(self.database.connect()) as c:
            c.execute('BEGIN IMMEDIATE');self._cic_revalidate(c,card_id);c.commit()
        return self.get_cic(card_id)

    def _cic_identity(self,c,card,cadet_id,create_new):
        email=c.execute('SELECT * FROM cadets WHERE lower(email)=lower(?)',(card['cadet_email'],)).fetchone()
        if create_new:
            if email:fail('This email already belongs to a saved cadet. Select that profile instead of creating a duplicate.')
            return None
        if cadet_id is None:fail('Confirm an existing profile or explicitly choose Create new profile.')
        row=c.execute('SELECT * FROM cadets WHERE cadet_id=?',(int(cadet_id),)).fetchone()
        if row is None:fail('Selected cadet no longer exists.')
        if email and email['cadet_id']!=row['cadet_id']:fail('The submitted email belongs to a different profile. Resolve the identity in ACE first.')
        return dict(row)

    def _cic_plan(self,c,card,cadet):
        catalog=self._cic_catalog(c);quantities=Counter()
        for line in card['lines']:
            if line['problem']:fail('Card is held. Resolve every item before approval.')
            quantities[item_key(line['item_no'])]+=line['quantity']
        plan=[]
        for key,qty in quantities.items():
            if key not in catalog:fail('Catalog changed. Revalidate this card.')
            cat=catalog[key]
            inventory=[dict(r) for r in c.execute('SELECT * FROM items') if item_key(r['wings_item_no'])==key]
            active=[r for r in inventory if r['status'] not in ('Lost','Retired')]
            if inventory and not active:fail(f"{cat['item_name']} is lost or retired. Correct its inventory status first.")
            if active:
                target=active[0]
                if target['total_quantity']-target['available_quantity']!=self._open_checkout_count(c,target['barcode_id']):
                    fail(f"Stock balance for {target['barcode_id']} needs correction in ACE before CIC reconciliation.")
            existing=owned=0
            if cadet:
                for r in c.execute('''SELECT t.*,i.wings_item_no FROM transactions t JOIN items i ON i.barcode_id=t.barcode_id
                   WHERE t.cadet_id=? OR (t.cadet_id IS NULL AND lower(t.cadet_email)=lower(?))''',(cadet['cadet_id'],cadet['email'])):
                    if item_key(r['wings_item_no'])!=key:continue
                    if r['return_time'] is None:existing+=1
                    elif r['disposition'] in ('Acquired / Permanent Issue','Purchased'):owned+=1
            plan.append({'item_no':cat['item_no'],'item_name':cat['item_name'],'size':cat['size'],'quantity':qty,
                         'existing':existing,'owned':owned,'add':max(0,qty-existing-owned),
                         'excess':max(0,existing+owned-qty),'barcode':active[0]['barcode_id'] if active else '',
                         'official':bool(cat['is_wings'])})
        return plan

    def preview_cic(self,card_id,*,cadet_id=None,create_new=False):
        self.revalidate_cic(card_id)
        with closing(self.database.connect()) as c:
            card=self._cic_card(c,card_id)
            if card['status']!='Pending':fail('Only a valid pending card can be approved.')
            cadet=self._cic_identity(c,card,cadet_id,create_new)
            plan=self._cic_plan(c,card,cadet)
            # Optimistic review guard: re-preview if holdings, mapping or identity changes.
            data=[card['version'],cadet,plan]
            review=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
            return {'card':card,'cadet':cadet,'plan':plan,'review_token':review}

    def approve_cic(self,card_id,*,cadet_id=None,create_new=False,approved_by=None,review_token):
        approval=self._normalize_admin_identity(approved_by)
        with closing(self.database.connect()) as c:
            c.execute('BEGIN IMMEDIATE');self._cic_revalidate(c,card_id);card=self._cic_card(c,card_id)
            if card['status']=='Approved':return card
            if card['status']!='Pending':fail('Card is held or rejected; it cannot be approved.')
            cadet=self._cic_identity(c,card,cadet_id,create_new);plan=self._cic_plan(c,card,cadet)
            review=hashlib.sha256(json.dumps([card['version'],cadet,plan],sort_keys=True).encode()).hexdigest()
            if not secrets.compare_digest(review,str(review_token)):fail('Card, profile or holdings changed. Preview again before approving.')
            if cadet is None:cadet=self._upsert_cadet(c,card['cadet_name'],card['cadet_email'])
            stamp=now();catalog=self._cic_catalog(c)
            used={r[0].upper() for r in c.execute('SELECT barcode_id FROM items UNION SELECT alias_barcode_id FROM barcode_aliases')}
            for line in plan:
                cat=catalog[item_key(line['item_no'])];bc=line['barcode'];last=c.execute('SELECT COALESCE(MAX(change_id),0) FROM inventory_changes').fetchone()[0]
                if not bc:
                    n=1
                    while f'A{n:07d}' in used:n+=1
                    bc=f'A{n:07d}';used.add(bc)
                    c.execute('''INSERT INTO items(barcode_id,wings_item_no,item_name,category,variant,item_type,status,total_quantity,available_quantity,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,'Available',0,0,?,?)''',(bc,cat['item_no'],cat['item_name'],cat['category'].upper(),cat['size'] or 'ONE SIZE',cat['subcategory'] or 'UNIFORM',stamp,stamp))
                if line['add']:
                    c.execute('UPDATE items SET total_quantity=total_quantity+?,updated_at=? WHERE barcode_id=?',(line['add'],stamp,bc))
                tx=[]
                for _ in range(line['add']):
                    cursor=c.execute('''INSERT INTO transactions(barcode_id,cadet_id,cadet_name,cadet_email,checkout_time,
                      approved_by_admin_id,approved_by_name,approved_by_role,approved_at,condition_notes)
                      VALUES(?,?,?,?,?,?,?,?,?,?)''',(bc,cadet['cadet_id'],cadet['full_name'],cadet['email'],stamp,approval['admin_id'],approval['approved_by_name'],approval['approved_by_role'],stamp,
                        f'CIC {card_id}: pre-existing possession confirmed by bag drag; not a new shelf issue. Original issue date unknown.'))
                    tx.append(cursor.lastrowid)
                if line['add']:self._sync_item_state(c,bc)
                c.execute("UPDATE inventory_changes SET source=?,action=CASE WHEN quantity_change>0 THEN 'Recovered CIC Possession' ELSE 'CIC Reconciliation' END,details=? WHERE change_id>? AND barcode_id=?",(approval['label'],f'CIC {card_id}: reconciled pre-existing cadet possession, {line["add"]} unit(s). Not a shipment receipt. Shelf availability preserved.',last,bc))
                # Aggregate duplicate card lines once, while preserving the submitted original quantities.
                ids=[r['line_id'] for r in card['lines'] if item_key(r['item_no'])==item_key(line['item_no'])]
                for i,lid in enumerate(ids):
                    c.execute('UPDATE cic_lines SET barcode_id=?,existing_quantity=?,added_quantity=?,transaction_ids=? WHERE line_id=?',
                      (bc,line['existing']+line['owned'] if i==0 else 0,line['add'] if i==0 else 0,json.dumps(tx) if i==0 else '[]',lid))
            c.execute("UPDATE cic_cards SET status='Approved',cadet_id=?,approved_by=?,approved_at=?,updated_at=?,version=version+1 WHERE card_id=?",(cadet['cadet_id'],approval['label'],stamp,stamp,card_id))
            self._cic_event(c,card_id,'Approved',approval['label'],json.dumps({'cadet_id':cadet['cadet_id'],'plan':plan}))
            c.commit();result=self._cic_card(c,card_id)
        self.database.note_write();return result

    def reject_cic(self,card_id,*,approved_by,reason):
        actor=self._normalize_admin_identity(approved_by)['label']
        if not reason.strip():fail('Give a rejection reason.')
        with closing(self.database.connect()) as c:
            c.execute('BEGIN IMMEDIATE');card=self._cic_card(c,card_id)
            if card['status'] not in ('Pending','Held'):fail('Only pending or held cards can be rejected.')
            c.execute("UPDATE cic_cards SET status='Rejected',version=version+1,updated_at=? WHERE card_id=?",(now(),card_id))
            self._cic_event(c,card_id,'Rejected',actor,reason[:1000]);c.commit()
        self.database.note_write()

    def cic_receipt(self,card_id,token):
        with closing(self.database.connect()) as c:
            row=c.execute('SELECT receipt_hash FROM cic_cards WHERE card_id=?',(card_id,)).fetchone()
            if row is None or not secrets.compare_digest(row[0],receipt_hash(token)):fail('Private receipt not found.')
            card=self._cic_card(c,card_id)
            return {k:card[k] for k in ('card_id','status','submitted_at','approved_at','lines','assessment_json')}

    def export_cic_wings(self,card_id,*,open_after=False):
        from .wings_catalog import WINGS_COLUMNS
        from .barcode_utils import open_file
        with closing(self.database.connect()) as c:
            card=self._cic_card(c,card_id)
            if card['status']!='Approved':fail('Only approved cards can be exported to WINGS.')
            catalog=self._cic_catalog(c);quantities=Counter()
            for line in card['lines']:
                item=c.execute('SELECT wings_item_no FROM items WHERE barcode_id=?',(line['barcode_id'],)).fetchone()
                cat=catalog.get(item_key(item[0] if item else ''))
                if cat is None or not cat['is_wings'] or not str(cat['item_no']).isdigit():
                    fail('WINGS export is held: one or more items still use local, hidden, missing or unverified IDs. Correct the mapping in ACE first.')
                quantities[item_key(cat['item_no'])]+=line['quantity']
            cadet=c.execute('SELECT * FROM cadets WHERE cadet_id=?',(card['cadet_id'],)).fetchone()
            rows=[]
            for key,qty in quantities.items():
                cat=catalog[key]
                rows.append(dict(zip(WINGS_COLUMNS,[self._format_wings_item_no(cat['item_no']),qty,0,qty,cat['item_name'],cat['size'],cat['category'],cat['subcategory'],cat['sex'],cat['stock_number'],cat['uom'],cat['writeoffs'],'Approved CIC '+card_id])))
            cover=[{'Cadet ID':cadet['cadet_id'],'Cadet':cadet['full_name'],'Email':cadet['email'],'Card ID':card_id,'Approved By':card['approved_by'],'Approved At':card['approved_at'],
                    'Purpose':'Existing possession reconciliation for cadre review, not proof of a new WINGS issue.'}]
        path=self.settings.database_path.parent/'exports'/f'ACE_CIC_WINGS_{card_id}.xlsx'
        path.parent.mkdir(parents=True,exist_ok=True)
        self._write_simple_xlsx_workbook(path,workbook_title='Approved Cadet Inventory Card',sheets=[{'sheet_name':'Cadet','columns':list(cover[0]),'rows':cover},{'sheet_name':'WINGs Inventory','columns':list(WINGS_COLUMNS),'rows':rows}])
        if open_after:open_file(path)
        return path

    def export_cic_copy(self,card_id):
        from html import escape
        card=self.get_cic(card_id)
        from .cic_questions import QUESTIONS
        assessment=json.loads(card['assessment_json'])
        counts='<h2>Declared quantities</h2>'+''.join('<h3>'+escape(family)+'</h3><p>'+escape(', '.join(f"{q[2]}: {assessment.get(q[0],0)}" for q in QUESTIONS if q[1]==family and assessment.get(q[0],0)) or 'None')+'</p>' for family in dict.fromkeys(q[1] for q in QUESTIONS)) if assessment else ''
        rows=''.join('<tr>'+''.join('<td>'+escape(str(line[k]))+'</td>' for k in ('item_no','entered_name','entered_size','quantity','problem'))+'</tr>' for line in card['lines'])
        path=self.settings.database_path.parent/'exports'/f'ACE_CIC_{card_id}.html';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('<!doctype html><meta charset="utf-8"><title>Cadet Inventory Card</title><style>body{font:16px Arial;margin:30px}th,td{padding:12px;border-bottom:1px solid #ddd;text-align:left}th{background:#0c2340;color:white}</style><h1>Cadet Inventory Card</h1><p>'+escape(card['cadet_name']+' | '+card['cadet_email']+' | '+card['status'])+'</p><p>Card '+escape(card_id)+'</p>'+counts+'<table><tr><th>Item ID</th><th>Item</th><th>Size</th><th>Quantity</th><th>Hold reason</th></tr>'+rows+'</table><p>Declared possession for ACE staff review. Pending and Held cards have not been approved. This is not an official WINGS issue transaction.</p>',encoding='utf-8')
        return path
