"""Optional Microsoft Forms intake over a read-only OneDrive-synced inbox.

The application never uploads, moves, edits or deletes files in that inbox.
Only the existing, explicit CIC review transaction can change inventory.
"""
from collections import Counter
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import uuid

from .cic import norm, now
from .cic_questions import QUESTIONS
from .cic_matching import match_human, row_quantity
from .catalog_inventory import item_key

SCHEMA = 'ace.cic.forms.v1'
MAX_BYTES = 256 * 1024
FIELDS = [('last_name', 'Last name'), ('middle_initial', 'Middle initial optional'),
          ('first_name', 'First name'), ('email', 'Auburn email')]
FAMILIES = list(dict.fromkeys((key.split('.')[0], family) for key, family, _ in QUESTIONS))
FIELDS += [(key + '.has_items', f'Do you currently possess any {family} items?') for key, family in FAMILIES]
FIELDS += [(key + '.has_item', f'{family} {label} possessed') for key, family, label in QUESTIONS]
FIELDS += [(key + '.count', f'{family} {label} quantity') for key, family, label in QUESTIONS]
FIELDS += [(key + '.sizes', f'{family} {label} sizes and types') for key, family, label in QUESTIONS]

REMOTE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS cic_remote (
 source_key TEXT PRIMARY KEY, card_id TEXT NOT NULL UNIQUE REFERENCES cic_cards(card_id),
 payload_hash TEXT NOT NULL, original_json TEXT NOT NULL, corrected_json TEXT NOT NULL DEFAULT '',
 imported_at TEXT NOT NULL, source_file TEXT NOT NULL
);
'''


def load_profile(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('schema') != SCHEMA:
        raise ValueError('Choose an ACE Microsoft CIC profile, schema ' + SCHEMA + '.')
    if not data.get('form_id') or not isinstance(data.get('field_map'), dict):
        raise ValueError('The CIC profile needs a form ID and a question field map.')
    if set(data['field_map']) != {key for key, _ in FIELDS}:
        raise ValueError('The form map must include every identity, quantity and size question.')
    values = list(data['field_map'].values())
    if any(not isinstance(v, str) or not v for v in values) or len(set(values)) != len(values):
        raise ValueError('Form question IDs must be distinct nonempty strings.')
    return data


def read_envelope(path, profile):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not re.fullmatch(r'cic-[0-9]+\.json', path.name):
        raise ValueError('Expected an ordinary cic-NUMBER.json submission file.')
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Card exceeds the 256 KB intake limit.')
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError('Card exceeds the 256 KB intake limit.')
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or data.get('form_id') != profile['form_id']:
        raise ValueError('Submission belongs to a different form or schema.')
    response = str(data.get('response_id', ''))
    if not re.fullmatch(r'[1-9][0-9]{0,11}', response) or path.name != f'cic-{response}.json':
        raise ValueError('File name and Forms response ID must match.')
    if not isinstance(data.get('answers'), dict):
        raise ValueError('Submission must contain Microsoft Forms answers.')
    return data


def decode_answers(envelope, profile):
    return {key: str(envelope['answers'].get(qid, '') or '').strip()
            for key, qid in profile['field_map'].items()}


def parse_answers(answers, catalog):
    """Context-scoped aliases and ordinary size entries; uncertainty stays held."""
    issues = []
    last = answers.get('last_name', '').strip()
    first = answers.get('first_name', '').strip()
    middle = answers.get('middle_initial', '').strip().rstrip('.')
    email = answers.get('email', '').strip()
    if not first or not last:
        issues.append('First and last name are required.')
    if len(middle) > 1:
        issues.append('Middle initial must be one letter or blank.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        issues.append('Enter a valid email address.')
    name = ', '.join(x for x in (last, middle, first) if x)
    counts = {}; lines = []
    family_answers = {}
    for key, family in FAMILIES:
        answer = norm(answers.get(key + '.has_items', ''))
        if answer not in ('yes', 'no'):
            issues.append(f'{family}: answer Yes or No to possessing this uniform family.')
        family_answers[key] = answer
    for key, family, label in QUESTIONS:
        value = answers.get(key + '.count', '').strip()
        text = answers.get(key + '.sizes', '').strip()
        if family_answers[key.split('.')[0]] == 'no':
            if value not in ('', '0', '0 - None') or norm(text) not in ('', '0', 'none', 'n/a'):
                issues.append(f'{family} {label}: No family possession conflicts with saved item answers. Confirm the correct answers.')
            counts[key] = 0
            continue
        has_item = norm(answers.get(key + '.has_item', ''))
        if has_item == 'no':
            if value not in ('', '0', '0 - None') or norm(text) not in ('', '0', 'none', 'n/a'):
                issues.append(f'{family} {label}: No item possession conflicts with saved quantities or sizes.')
            counts[key] = 0
            continue
        if has_item != 'yes':
            issues.append(f'{family} {label}: answer Yes or No to possessing this item.')
        if value == '0 - None':
            value = '0'
        if not value.isdigit():
            from .cic_matching import canonical
            normalized_count = canonical(value)
            if len(normalized_count) == 1 and normalized_count[0].isdigit():
                value = normalized_count[0]
        large_count = value == 'More than 10'
        if large_count:
            count = 11
        elif not re.fullmatch(r'[0-9]{1,3}', value) or int(value) > 100:
            issues.append(f'{family} {label}: enter a quantity from 0 to 100, including 0 for none.')
            count = 0
        else:
            count = int(value)
        counts[key] = count
        allocated = 0
        if norm(text) in ('none', '0', 'n/a'):
            text = ''
        rows = [row.strip() for row in re.split(r'[\n;]+', text) if row.strip()]
        for row in rows:
            parts = [p.strip() for p in row.split('|')]
            cat = None
            if len(parts) == 3:
                if not re.fullmatch(r'[1-9][0-9]{0,2}', parts[-1]) or int(parts[-1]) > 100:
                    issues.append(f'{family} {label}: invalid quantity in {row[:160]}.'); continue
                description, size, qty = parts[0], parts[1], int(parts[2])
                matches = [c for c in catalog if c.get('group') == key and norm(c['size']) == norm(size)
                           and (norm(description) == norm(c['name']) or item_key(description) == item_key(c['item_no']))]
                if len(matches) != 1:
                    matches = match_human(description + ' ' + size, key, catalog)
            elif len(parts) == 1:
                description, qty = row_quantity(row)
                size = description
                if qty is None and key in ('ocp.flag', 'ocp.afrotc'):
                    patch_count = re.fullmatch(r'(\d+)\s+((?:spice|brown|coyote|tan)\b.*)', description, re.I)
                    if patch_count:
                        description, qty = patch_count[2], int(patch_count[1])
                if qty is None:
                    if len(rows) == 1 and not large_count:
                        qty = count
                    elif len(rows) == count:
                        qty = 1
                    else:
                        issues.append(f'{family} {label}: say how many of each size, for example Medium x2.'); continue
                if not 1 <= qty <= 100:
                    issues.append(f'{family} {label}: quantity per size must be 1 to 100.'); continue
                matches = match_human(description, key, catalog)
                if len(matches) != 1:
                    if matches:
                        choices = '; '.join(f"{c['name']} / {c['size']}" + (f" ({c['sex']})" if c.get('sex') else '') for c in matches[:5])
                        issues.append(f'{family} {label}: "{row[:120]}" matches multiple items. Specify type, summer/all weather, mens/womens or width as applicable. Options: {choices}.')
                    else:
                        issues.append(f'{family} {label}: could not match "{row[:120]}". Confirm its label size and type in ACE; no item ID is required.')
            else:
                issues.append(f'{family} {label}: enter a size such as Medium regular x2, one size per line.'); continue
            allocated += qty
            cat = matches[0] if len(matches) == 1 else None
            lines.append({'item_no': cat['item_no'] if cat else '', 'name': cat['name'] if cat else description,
                          'size': cat['size'] if cat else size, 'quantity': qty, 'group': key})
        if large_count and 11 <= allocated <= 100:
            counts[key] = allocated
        elif allocated != count or (large_count and allocated < 11):
            issues.append(f'{family} {label}: quantity {count}, but size lines total {allocated}.')
    if sum(counts.values()) > 500 or sum(l['quantity'] for l in lines) > 500:
        issues.append('A card cannot contain more than 500 items.')
    if len(lines) > 100:
        issues.append('A card cannot contain more than 100 size lines.')
    return {'name': name, 'email': email, 'lines': lines, 'assessment': counts,
            'no_items': not lines}, issues


class SharePointCicMixin:
    def import_microsoft_cic(self, envelope, profile, *, source_file='', secret):
        """Durably import once without acknowledging by changing a cloud file."""
        if envelope.get('schema') != SCHEMA or envelope.get('form_id') != profile['form_id']:
            raise ValueError('Wrong CIC form or schema.')
        if not isinstance(envelope.get('answers'), dict):
            raise ValueError('Submission must contain an answer object.')
        response = str(envelope.get('response_id', ''))
        if not re.fullmatch(r'[1-9][0-9]{0,11}', response):
            raise ValueError('Invalid Forms response ID.')
        original = json.dumps(envelope, sort_keys=True, ensure_ascii=False)
        if len(original.encode()) > MAX_BYTES:
            raise ValueError('Card exceeds the intake limit.')
        source = profile['form_id'] + ':' + response
        digest = hashlib.sha256(original.encode()).hexdigest()
        session = 'microsoft:' + profile['form_id']
        request = str(uuid.uuid5(uuid.NAMESPACE_URL, source))
        with closing(self.database.connect()) as c:
            old = c.execute('SELECT * FROM cic_remote WHERE source_key=?', (source,)).fetchone()
            if old:
                if old['payload_hash'] != digest:
                    raise ValueError('Previously received response changed. Existing card was preserved; staff must investigate.')
                return self.get_cic(old['card_id']), False
        answers = decode_answers(envelope, profile)
        parsed, issues = parse_answers(answers, self.cic_catalog())
        valid_identity = True
        try:
            self._validate_cadet_identity(parsed['name'], parsed['email'])
        except Exception as error:
            valid_identity = False
            issues.append(str(error))
        # Create a valid held shell if identity/count answers need staff correction.
        # This identity is never created as an operational cadet while held.
        payload = dict(parsed, request_id=request,
                       receipt_token=hmac.new(secret.encode(), source.encode(), hashlib.sha256).hexdigest(),
                       notes='Microsoft CIC response ' + response + '. Staff must verify identity and catalog mappings.')
        if issues:
            payload['assessment'] = {}
            if len(payload['lines']) > 100 or sum(l['quantity'] for l in payload['lines']) > 500:
                payload.update(lines=[], no_items=True)
        if not valid_identity:
            payload.update(name='Unresolved, Microsoft Intake', email=f'held-{request}@example.invalid')
        # submit_cic commits its own idempotent transaction. A crash after this call is
        # recovered using the same session/request/secret; no stock can change here.
        card = self.submit_cic(payload, session_id=session, intake_issues=issues)
        with closing(self.database.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM cic_remote WHERE source_key=?', (source,)).fetchone()
            if old:
                if old['payload_hash'] != digest:
                    raise ValueError('Concurrent response conflict. Existing card preserved.')
                return self._cic_card(c, old['card_id']), False
            c.execute('INSERT INTO cic_remote(source_key,card_id,payload_hash,original_json,imported_at,source_file) VALUES(?,?,?,?,?,?)',
                      (source, card['card_id'], digest, original, now(), source_file))
            if card['status'] in ('Pending', 'Held'):
                c.execute('UPDATE cic_cards SET intake_issues_json=? WHERE card_id=?', (json.dumps(issues), card['card_id']))
                if issues:
                    c.execute("UPDATE cic_cards SET status='Held' WHERE card_id=?", (card['card_id'],))
                self._cic_event(c, card['card_id'], 'Microsoft intake received', 'Microsoft intake',
                                f'Response {response}; inventory unchanged. Submitted time: {str(envelope.get("submitted_at", "unknown"))[:100]}')
            c.commit()
        self.database.note_write()
        return self.get_cic(card['card_id']), True

    def microsoft_cic_answers(self, card_id, profile):
        with closing(self.database.connect()) as c:
            row = c.execute('SELECT * FROM cic_remote WHERE card_id=?', (card_id,)).fetchone()
            if row is None:
                return None
            return json.loads(row['corrected_json']) if row['corrected_json'] else decode_answers(json.loads(row['original_json']), profile)

    def correct_microsoft_cic(self, card_id, answers, *, approved_by, expected_version):
        actor = self._normalize_admin_identity(approved_by)['label']
        if not isinstance(answers, dict) or set(answers) != {k for k, _ in FIELDS} or any(not isinstance(v, str) for v in answers.values()):
            raise ValueError('Keep all question keys and use text answers.')
        parsed, issues = parse_answers(answers, self.cic_catalog())
        self._validate_cadet_identity(parsed['name'], parsed['email'])
        if len(parsed['lines']) > 100 or sum(l['quantity'] for l in parsed['lines']) > 500:
            raise ValueError('Reduce the card to at most 100 size lines and 500 items.')
        with closing(self.database.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            card = self._cic_card(c, card_id)
            if card['status'] not in ('Pending', 'Held') or card['version'] != expected_version:
                raise ValueError('Card changed or was finalized. Reopen it before correcting.')
            if c.execute('SELECT 1 FROM cic_remote WHERE card_id=?', (card_id,)).fetchone() is None:
                raise ValueError('This is not a Microsoft intake card.')
            c.execute('DELETE FROM cic_lines WHERE card_id=?', (card_id,))
            c.executemany('INSERT INTO cic_lines(card_id,item_no,entered_name,entered_size,quantity,group_key) VALUES(?,?,?,?,?,?)',
                          [(card_id, l['item_no'], l['name'], l['size'], l['quantity'], l['group']) for l in parsed['lines']])
            c.execute("UPDATE cic_cards SET cadet_name=?,cadet_email=?,assessment_json=?,intake_issues_json=?,version=version+1 WHERE card_id=?",
                      (parsed['name'], parsed['email'], json.dumps(parsed['assessment']), json.dumps(issues), card_id))
            c.execute('UPDATE cic_remote SET corrected_json=? WHERE card_id=?', (json.dumps(answers), card_id))
            self._cic_revalidate(c, card_id)
            self._cic_event(c, card_id, 'Microsoft answers corrected', actor, 'Local correction retained alongside original submission. Inventory unchanged.')
            c.commit()
        self.database.note_write()
        return self.get_cic(card_id)


class InboxReader:
    """Bounded polling in a worker; no Tk calls or source filesystem writes."""
    def __init__(self, service, folder, profile, secret):
        self.service, self.folder, self.profile, self.secret = service, Path(folder), profile, secret
        self.seen = {}

    def poll(self):
        if not self.folder.is_dir():
            return [], [('Inbox', 'Synced inbox folder is unavailable. Check OneDrive and the configured path.')]
        cards, errors = [], []
        files = sorted(self.folder.glob('cic-*.json'))
        if len(files) > 10000:
            return [], [('Inbox', 'More than 10,000 files. Configure a dedicated active CIC inbox.')]
        processed = 0
        for path in files:
            try:
                stat = path.stat(); signature = (stat.st_mtime_ns, stat.st_size)
                if self.seen.get(path.name) == signature:
                    continue
                if processed >= 50:
                    break
                processed += 1
                envelope = read_envelope(path, self.profile)
                card, added = self.service.import_microsoft_cic(envelope, self.profile, source_file=path.name, secret=self.secret)
                self.seen[path.name] = signature
                if added:
                    cards.append(card)
            except (OSError, ValueError, UnicodeError) as error:
                errors.append((path.name, str(error)))
        return cards, errors
