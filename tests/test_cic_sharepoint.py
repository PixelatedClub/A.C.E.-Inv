import gc
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from inventory_app.cic_sharepoint import FIELDS, SCHEMA, InboxReader, parse_answers, read_envelope
from inventory_app.cic_questions import QUESTIONS
from inventory_app.config import AppSettings
from inventory_app.services import InventoryService, InventoryError

ADMIN = {'role':'CADRE','display_name':'CADRE','admin_id':None}


class MicrosoftCicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = InventoryService(AppSettings(db_path=str(self.root/'inventory.db'), backup_interval_ops=10000))
        self.profile = {'schema':SCHEMA,'form_id':'form-example','field_map':{k:k for k,_ in FIELDS}}
        self.answers = {k:('0' if k.endswith('.count') else '') for k,_ in FIELDS}
        self.answers.update({k:'yes' for k,_ in FIELDS if k.endswith('.has_items')})
        self.answers.update({k:'yes' for k,_ in FIELDS if k.endswith('.has_item')})
        self.answers.update(first_name='Jane', last_name='Example', email='jane@example.invalid')
        self.cat = next(c for c in self.service.cic_catalog() if c['group'] in {q[0] for q in QUESTIONS})
        key = self.cat['group']
        self.answers[key+'.count']='2'
        self.answers[key+'.sizes']=f'{self.cat["item_no"]} | {self.cat["size"]} | 2'
    def tearDown(self):
        self.service=None;gc.collect();self.temp.cleanup()
    def envelope(self, answers=None, response='1'):
        return {'schema':SCHEMA,'form_id':'form-example','response_id':response,'submitted_at':'2026-10-26T15:00:00Z','answers':answers or self.answers}
    def operational(self):
        with self.service.database.connect() as c:
            return {t:[tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in ('items','cadets','transactions','inventory_changes')}
    def test_inbox_read_only_replay_and_approval(self):
        folder=self.root/'inbox';folder.mkdir();path=folder/'cic-1.json'
        path.write_text(json.dumps(self.envelope()),encoding='utf-8');before=path.read_bytes();ops=self.operational()
        reader=InboxReader(self.service,folder,self.profile,'local-test-secret')
        cards,errors=reader.poll();self.assertEqual(errors,[]);self.assertEqual(len(cards),1)
        self.assertEqual(cards[0]['status'], 'Pending')
        current = self.operational()
        self.assertEqual(len(current['cadets']), 1)
        self.assertEqual(current['cadets'][0][0], cards[0]['cadet_id'])
        self.assertEqual({k: v for k, v in ops.items() if k != 'cadets'},
                         {k: v for k, v in current.items() if k != 'cadets'})
        self.assertEqual(before,path.read_bytes())
        self.assertEqual(reader.poll(),([],[]))
        reader=InboxReader(self.service,folder,self.profile,'local-test-secret')
        self.assertEqual(reader.poll(),([],[]))
        self.assertEqual(current, self.operational())
        preview=self.service.preview_cic(cards[0]['card_id'],cadet_id=cards[0]['cadet_id'])
        self.service.approve_cic(cards[0]['card_id'],cadet_id=cards[0]['cadet_id'],approved_by=ADMIN,review_token=preview['review_token'])
        self.assertEqual(before,path.read_bytes())
        with self.service.database.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],2)
    def test_bad_counts_held_and_staff_correction_preserves_original(self):
        answers=dict(self.answers);answers[self.cat['group']+'.count']='3'
        original=self.envelope(answers)
        card,_=self.service.import_microsoft_cic(original,self.profile,secret='secret')
        self.assertEqual(card['status'],'Held');self.assertTrue(json.loads(card['intake_issues_json']))
        self.service.revalidate_cic(card['card_id'])
        with self.assertRaises(InventoryError):self.service.preview_cic(card['card_id'],create_new=True)
        before=self.operational()
        fixed=self.service.correct_microsoft_cic(card['card_id'],self.answers,approved_by=ADMIN,expected_version=card['version'])
        self.assertEqual(fixed['status'],'Pending');self.assertEqual(fixed['cadet_name'],'Example, Jane');self.assertEqual(before,self.operational())
        with self.service.database.connect() as c:
            row=c.execute('SELECT * FROM cic_remote').fetchone();self.assertEqual(json.loads(row['original_json']),original)
            self.assertEqual(json.loads(row['corrected_json']),self.answers)
        with self.assertRaises(ValueError):self.service.correct_microsoft_cic(card['card_id'],self.answers,approved_by=ADMIN,expected_version=card['version'])
    def test_misspelling_is_never_fuzzy_matched(self):
        answers=dict(self.answers);answers[self.cat['group']+'.sizes']='Mispelled | wrong | 2'
        card,_=self.service.import_microsoft_cic(self.envelope(answers),self.profile,secret='secret')
        self.assertEqual(card['status'],'Held');self.assertEqual(card['lines'][0]['item_no'],'')
    def test_partial_corrections_keep_lines_and_remain_held(self):
        answers=dict(self.answers);answers[self.cat['group']+'.count']='3'
        card,_=self.service.import_microsoft_cic(self.envelope(answers),self.profile,secret='secret')
        self.assertTrue(card['lines'])
        before=self.operational()
        answers['middle_initial']='J'
        fixed=self.service.correct_microsoft_cic(card['card_id'],answers,approved_by=ADMIN,expected_version=card['version'])
        self.assertEqual(fixed['status'],'Held');self.assertTrue(fixed['lines'])
        self.assertEqual(before,self.operational())
        with self.assertRaises(InventoryError):self.service.preview_cic(card['card_id'],create_new=True)
    def test_family_no_skips_missing_counts_but_conflicting_answers_hold(self):
        answers=dict(self.answers)
        family=self.cat['group'].split('.')[0]
        answers[family+'.has_items']='no'
        for key in list(answers):
            if key.startswith(family+'.') and not key.endswith('.has_items'):answers[key]=''
        parsed,issues=parse_answers(answers,self.service.cic_catalog());self.assertEqual(issues,[])
        self.assertFalse(parsed['lines'])
        answers[self.cat['group']+'.count']='1'
        self.assertTrue(parse_answers(answers,self.service.cic_catalog())[1])
    def test_more_than_ten_uses_exact_size_allocation_and_zero_skips_sizes(self):
        answers=dict(self.answers);key=self.cat['group']
        answers[key+'.count']='More than 10';answers[key+'.sizes']=f'{self.cat["item_no"]} | {self.cat["size"]} | 12'
        parsed,issues=parse_answers(answers,self.service.cic_catalog());self.assertEqual(issues,[]);self.assertEqual(parsed['assessment'][key],12)
        answers[key+'.count']='0 - None';answers[key+'.sizes']=''
        self.assertFalse(parse_answers(answers,self.service.cic_catalog())[1])
    def test_empty_none_and_missing_identity(self):
        answers={k:('0' if k.endswith('.count') else '') for k,_ in FIELDS}
        answers.update({k:'no' for k,_ in FIELDS if k.endswith('.has_items')})
        parsed,issues=parse_answers(answers,self.service.cic_catalog());self.assertTrue(issues)
        card,_=self.service.import_microsoft_cic(self.envelope(answers),self.profile,secret='secret')
        self.assertEqual(card['status'],'Held')
        answers.update(first_name='Jane',last_name='Example',email='jane@example.invalid')
        parsed,issues=parse_answers(answers,self.service.cic_catalog());self.assertEqual(issues,[]);self.assertTrue(parsed['no_items'])
    def test_blues_belt_defaults_to_two_components(self):
        catalog = [
            {'item_no': 'LOCAL-BLUES-BELT-SIZEUNSPECIFIED', 'name': 'Blues Belt', 'size': 'SIZE UNSPECIFIED', 'group': 'blues.belt'},
            {'item_no': '1', 'name': 'BUCKLE, BELT', 'size': 'N/A-BUCKLE', 'group': 'blues.belt'},
        ]
        answers = dict(self.answers)
        answers.update({key+'.count': '0' for key, _, _ in QUESTIONS})
        answers.update({key+'.sizes': '' for key, _, _ in QUESTIONS})
        answers.update({'blues.belt.count': '1', 'blues.belt.sizes': 'N/A'})
        parsed, issues = parse_answers(answers, catalog)
        self.assertEqual(issues, [])
        self.assertEqual(parsed['assessment']['blues.belt'], 2)
        self.assertEqual(parsed['name'], 'Example, Jane')
        self.assertEqual([(r['item_no'], r['quantity']) for r in parsed['lines']],
                         [('LOCAL-BLUES-BELT-SIZEUNSPECIFIED', 1), ('1', 1)])
        answers['blues.belt.sizes'] = '1 | N/A-BUCKLE | 1'
        parsed, issues = parse_answers(answers, catalog)
        self.assertEqual(issues, [])
        self.assertEqual([r['item_no'] for r in parsed['lines']], ['1'])

    def test_form_edit_keeps_staff_mapping_in_unchanged_group(self):
        group = self.cat['group']
        answers = dict(self.answers)
        answers[group+'.sizes'] = 'Staff will identify this item'
        card,_ = self.service.import_microsoft_cic(self.envelope(answers),self.profile,secret='secret')
        line_id = card['lines'][0]['line_id']
        self.service.map_cic_line(card['card_id'],line_id,self.cat['item_no'],approved_by=ADMIN)
        mapped = self.service.get_cic(card['card_id'])
        self.assertEqual(mapped['status'],'Pending')
        answers['middle_initial'] = 'Q'
        edited = self.service.correct_microsoft_cic(card['card_id'],answers,approved_by=ADMIN,
            expected_version=mapped['version'],profile=self.profile)
        self.assertEqual(edited['status'],'Pending')
        self.assertEqual(edited['lines'],mapped['lines'])
        answers[group+'.count'] = '3'
        answers[group+'.sizes'] = f"{self.cat['item_no']} | {self.cat['size']} | 3"
        changed = self.service.correct_microsoft_cic(card['card_id'],answers,approved_by=ADMIN,
            expected_version=edited['version'],profile=self.profile)
        self.assertEqual(changed['lines'][0]['quantity'],3)

    def test_changed_received_response_cannot_overwrite_card(self):
        card,_=self.service.import_microsoft_cic(self.envelope(),self.profile,secret='secret')
        changed=self.envelope();changed['answers']=dict(self.answers,email='changed@example.invalid')
        with self.assertRaises(ValueError):self.service.import_microsoft_cic(changed,self.profile,secret='secret')
        self.assertEqual(self.service.get_cic(card['card_id'])['cadet_email'],'jane@example.invalid')
    def test_crash_after_submit_recovers_idempotently(self):
        original=self.service._cic_event
        def fail(c,card,action,actor,details):
            if action=='Microsoft intake received':raise RuntimeError('power loss')
            return original(c,card,action,actor,details)
        with patch.object(self.service,'_cic_event',side_effect=fail):
            with self.assertRaises(RuntimeError):self.service.import_microsoft_cic(self.envelope(),self.profile,secret='secret')
        card,added=self.service.import_microsoft_cic(self.envelope(),self.profile,secret='secret')
        self.assertTrue(added);self.assertEqual(len(self.service.list_cic()),1);self.assertEqual(card['status'],'Pending')
    def test_wrong_form_partial_json_and_limit_leave_inventory_unchanged(self):
        before=self.operational();folder=self.root/'inbox';folder.mkdir();path=folder/'cic-1.json';path.write_text('{')
        reader=InboxReader(self.service,folder,self.profile,'secret');cards,errors=reader.poll();self.assertFalse(cards);self.assertTrue(errors)
        value=self.envelope();value['form_id']='wrong';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):read_envelope(path,self.profile)
        path.write_text('x'*(256*1024+1))
        with self.assertRaises(ValueError):read_envelope(path,self.profile)
        self.assertEqual(before,self.operational())


if __name__=='__main__':unittest.main()
