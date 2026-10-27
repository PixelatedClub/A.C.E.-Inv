"""One read-only vocabulary for inventory and catalog search.

Search returns alternatives; it never merges records or chooses a CIC match.
"""
from collections import Counter
from .cic_matching import canonical
from .cic_questions import QUESTIONS, question_for

LABELS = {key:(family,label) for key,family,label in QUESTIONS}
ALIASES = {
    'ocp.coat':'ocp coat blouse top jacket', 'ocp.trousers':'ocp pants bottoms',
    'ocp.shirt':'ocp undershirt tshirt t shirt tan brown',
    'ocp.cover':'ocp patrol cap headwear headgear',
    'ocp.boots':'ocp boots footwear', 'ocp.fleece':'ocp fleece jacket brown',
    'ocp.belt':'ocp rigger belt', 'ocp.afrotc':'ocp afrotc patch',
    'ocp.flag':'ocp us flag patch', 'ocp.rank':'ocp rank insignia',
    'ptg.shirt':'ptg pt ptu iptu shirt', 'ptg.shorts':'ptg pt ptu iptu shorts trunks',
    'ptg.pants':'ptg pt ptu iptu pants', 'ptg.jacket':'ptg pt ptu iptu jacket',
    'blues.cover':'blues flight cap headwear headgear',
    'blues.trousers':'blues pants slacks bottoms',
    'blues.shirt':'blues shirt', 'blues.shoes':'blues dress shoes footwear',
    'blues.rank':'blues rank insignia', 'blues.jacket':'blues lightweight windbreaker jacket',
    'service.coat':'blues service dress coat jacket', 'other.flight':'flight suit flightsuit bag pickle',
}


def describe(row):
    name = str(row.get('item_name') or row.get('name') or '')
    sub = ' '.join(str(row.get(k) or '') for k in ('subcategory','item_type','catalog_name','catalog_subcategory'))
    source = dict(item_name=name, category=row.get('category',''), subcategory=sub)
    group = question_for(source)
    family,label = LABELS[group]
    size = str(row.get('variant') or row.get('size') or '')
    sex = str(row.get('sex') or '').upper()
    tokens = canonical(' '.join([name,sub,str(row.get('category') or ''),size,ALIASES.get(group,''),
                                  str(row.get('family') or ''),str(row.get('season') or '')]))
    if sex in ('M','F'):
        tokens.append('male' if sex=='M' else 'female')
    season = 'Summer' if 'summer' in tokens else 'All weather' if group in ('ocp.coat','ocp.trousers') else ''
    if season:
        tokens.extend(canonical(season))
    context = ' / '.join(x for x in (family,label,season,size,{'M':"Men's",'F':"Women's"}.get(sex,'')) if x)
    return tokens, context


def search_match(query, row):
    """AND terms across fields, whole size tokens, partial words, exact IDs first."""
    query = str(query or '').strip()
    if not query:
        return True
    ids = [str(row.get(k) or '').casefold() for k in ('barcode_id','wings_item_no','item_no','stock_number')]
    ids += [str(x).casefold() for x in row.get('barcode_aliases',[])]
    if query.casefold() in ids:
        return True
    if query.isdigit() and any(x.isdigit() and int(x)==int(query) for x in ids):
        return True
    query_tokens=canonical(query)
    primary=canonical(str(row.get('item_name') or row.get('name') or '')+' '+str(row.get('catalog_name') or ''))
    garment_types={'pants','skirt','shorts','trunks'}
    primary_types=set(primary)&garment_types
    if 'trunks' in primary_types:
        primary_types.add('shorts')
    if primary_types and any(word in garment_types and word not in primary_types for word in query_tokens):
        return False
    tokens,_ = describe(row)
    for key in ('tags','search_aliases'):
        value=row.get(key) or []
        tokens.extend(canonical(' '.join(value) if isinstance(value,list) else value))
    tokens.extend(canonical(row.get('notes','')))
    tokens.extend(canonical(' '.join(ids)))
    needed=Counter(query_tokens); available=Counter(tokens)
    if not needed:
        return False
    return all(available[word]>=number or
               (len(word)>=3 and word.isalpha() and any(t.startswith(word) for t in available))
               for word,number in needed.items())
