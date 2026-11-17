"""Deterministic, context-scoped aliases for human-entered CIC sizes.

Unknown words and multiple catalog matches are never silently guessed.
"""
from collections import Counter
from fractions import Fraction
from decimal import Decimal
from functools import lru_cache
import re


def canonical(value):
    # Return a fresh list so callers cannot mutate cached vocabulary.
    return list(_canonical(str(value or '')))


@lru_cache(maxsize=8192)
def _canonical(value):
    text = str(value or '').casefold().replace('½', ' 1/2').replace('¼', ' 1/4').replace('¾', ' 3/4')
    numbers = {'zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5',
               'six':'6','seven':'7','eight':'8','nine':'9','ten':'10','eleven':'11',
               'twelve':'12','thirteen':'13','fourteen':'14','fifteen':'15','sixteen':'16',
               'seventeen':'17','eighteen':'18','nineteen':'19','twenty':'20'}
    text = re.sub(r'\b(?:'+'|'.join(numbers)+r')\b', lambda m:numbers[m[0]], text)
    text = re.sub(r'\b(\d+)\s+and\s+(?:a|1)\s+half\b', r'\1 1/2', text)
    text = re.sub(r'\b(\d+)\s+and\s+(?:a|1)\s+quarter\b', r'\1 1/4', text)
    text = re.sub(r'\b(\d+)\s+and\s+3\s+quarters\b', r'\1 3/4', text)
    text = re.sub(r'\b(\d+)\s+point\s+(\d+)\b', r'\1.\2', text)
    def fraction(match):
        try:
            return str(float(Fraction(match[1]) + Fraction(match[2])))
        except (ValueError, ZeroDivisionError):
            return 'invalidfraction'
    text = re.sub(r'\b(\d+)[ -]+(\d+/\d+)\b', fraction, text)
    phrases = [
        (r'all[ -]?weathers?|cold[ -]?weather|\bcold\b|\bawb\b|\bawp\b', 'allweather'),
        (r'summer[ -]?weight|\bsummers?\b|hot[ -]?weathers?|\bhot\b|\bihwcu\b|\bswb\b', 'summer'),
        (r'\b(?:extra|x)[ -]?(?:extra|x)[ -]?small\b|\bxx[ -]?small\b', 'xxs'),
        (r'\b(?:extra|x)[ -]?small\b', 'xs'),
        (r'\b(?:triple|3)[ -]?(?:extra|x)[ -]?large\b|\bxxx[ -]?large\b|\b3xl\b', 'xxxl'),
        (r'\b(?:double|2)[ -]?(?:extra|x)[ -]?large\b|\bxx[ -]?large\b|\b2xl\b', 'xxl'),
        (r'\b(?:extra|x)[ -]?large\b', 'xl'),
        (r'\b(?:extra|x)[ -]?short\b', 'xs'),
        (r'\b(?:extra|x)[ -]?long\b', 'xl'),
        (r'\b(?:one size|standard|osfa|one size fits all)\b', 'onesize'),
        (r'\b(?:women[’\x27]?s|woman[’\x27]?s|female|womens)\b', 'female'),
        (r'\b(?:men[’\x27]?s|man[’\x27]?s|male|mens)\b', 'male'),
        (r'\b(?:second lieutenant|2nd lt|2d lt|2lt)\b', '2 lt'),
        (r'\b(?:first lieutenant|1st lt|1lt)\b', '1 lt'),
        (r'\blieutenant colonel\b|\blt col\b', 'ltcol'),
        (r'\bcolonel\b|\bcol\b', 'col'),
        (r'\bcaptain\b|\bcapt\b', 'capt'),
        (r'\bmajor\b|\bmaj\b', 'maj'),
        (r'\bcadet\b', 'c'),
        (r'\bhard\b|\bmetal\b', 'metal'),
        (r'\bsoft\b|\bcloth\b', 'cloth'),
        (r'\bspice brown\b|\bcoyote(?: brown)?\b', 'brown'),
    ]
    for pattern, replacement in phrases:
        text = re.sub(pattern, replacement, text)
    compact = {'ss':'s s', 'sr':'s r', 'sl':'s l', 'smsh':'s s', 'smreg':'s r',
               'ms':'m s', 'mr':'m r', 'ml':'m l', 'medreg':'m r',
               'ls':'l s', 'lr':'l r', 'll':'l l', 'xss':'xs s', 'xsr':'xs r', 'xsl':'xs l'}
    text = re.sub(r'\b(?:' + '|'.join(compact) + r')\b', lambda m: compact[m[0]], text)
    text = re.sub(r'(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)', ' ', text)
    words = re.findall(r'\d+(?:\.\d+)?|[a-z]+', text)
    aliases = {'small':'s', 'smal':'s', 'sm':'s', 'sml':'s', 'medium':'m', 'meduim':'m', 'medoum':'m', 'med':'m', 'large':'l', 'lg':'l', 'lrg':'l',
               'regular':'r', 'reg':'r', 'rg':'r', 'regualr':'r', 'short':'s', 'sh':'s', 'sht':'s',
               'long':'l', 'lng':'l', 'wide':'w', 'narrow':'n', 'normal':'r',
               'inches':'inch', 'in':'inch', 'trousers':'pants', 'trouser':'pants',
               'blouses':'coat', 'blouse':'coat', 'coats':'coat', 'covers':'cap', 'cover':'cap',
               'hats':'cap', 'hat':'cap', 'caps':'cap', 'patches':'patch', 'ranks':'rank',
               'undershirts':'shirt', 'undershirt':'shirt', 'shirts':'shirt', 'boots':'boot',
               'fleeces':'fleece', 'belts':'belt', 'flags':'flag', 'american':'us'}
    aliases.update({'ocps':'ocp','slacks':'pants','slack':'pants','blues':'blue',
                    'ptgs':'ptg','tshirt':'shirt','tshirts':'shirt','men':'male','women':'female'})
    ignored = {'size', 'sized', 'pair', 'pairs', 'inch', 'inches', 'in', 'i', 'have', 'a', 'an', 'the', 'it', 'is'}
    return tuple(format(Decimal(w).normalize(),'f') if re.fullmatch(r'\d+(?:\.\d+)?',w) else aliases.get(w,w)
                 for w in words if w not in ignored)


def row_quantity(row):
    """Return text and an explicit quantity, or None when only a size was given."""
    for pattern in (r'^\s*(\d+)\s*[x×]\s*(.+)$', r'^\s*(\d+)\s+(?:of|pairs? of)\s+(.+)$'):
        match = re.match(pattern, row, re.I)
        if match:
            return match[2].strip(), int(match[1])
    match = re.match(r'^(.*?)\s*(?:[x×]\s*|qty\s*[:=]?\s*|quantity\s*[:=]?\s*)(\d+)\s*$', row, re.I)
    if match:
        return match[1].strip(), int(match[2])
    match = re.match(r'^(.*?)\s*\((\d+)\)\s*$', row)
    if match:
        return match[1].strip(), int(match[2])
    match = re.fullmatch(r'(.*?)\s*\([x×]\s*(\d+)\)', row, re.I)
    if match:
        return match[1].strip(), int(match[2])
    return row.strip(), None


def match_human(text, group, catalog, *, suggest_incomplete=False):
    text = re.sub(r'^\s*all\s+are\s+', '', text, flags=re.I)
    if group == 'ocp.other':
        text = re.sub(r'\bbeenie\b', 'beanie', text, flags=re.I)
    style = ''
    if group in ('ptg.shirt', 'ptg.shorts'):
        text = re.sub(r'\bathltic\b', 'athletic', text, flags=re.I)
        if group == 'ptg.shirt':
            text = re.sub(r'\bathletic\b', 'dry fit', text, flags=re.I)
        text = re.sub(r'\b(?:ptg?s?|shirts?|shorts?)\b', '', text, flags=re.I)
        styles = (
            ((r'\b(?:new(?:\s+(?:style|issues?))?|dry[\s-]*fit)\b','dryfit'),
             (r'\b(?:old(?:\s+(?:style|issues?))?|cotton)\b','cotton')) if group == 'ptg.shirt' else
            ((r'\b(?:new(?:\s+(?:style|issues?))?|general[\s-]+purp(?:ose)?)\b','general purpose'),
             (r'\b(?:old(?:\s+(?:style|issues?))?|running)\b','running'))
        )
        detected = [(pattern, key) for pattern,key in styles if re.search(pattern,text,re.I)]
        if len(detected) > 1:
            return []
        if detected:
            pattern, style = detected[0]
            text = re.sub(pattern,'',text,flags=re.I)
            text = re.sub(r'\b(small|medium|large)s\b', r'\1', text, flags=re.I)
    if group == 'ocp.cover':
        text = re.sub(r'^\s*pc\s+', '', text, flags=re.I)
    if group == 'ocp.shirt':
        text = re.sub(r'^\s*regular\s+(?=coyote\b|brown\b|tan\b)', '', text, flags=re.I)
        text = re.sub(r'\bboth\s+(?=xs\b|s\b|m\b|l\b|xl\b|small\b|medium\b|large\b)', '', text, flags=re.I)
        text = re.sub(r'\s*\(i have more (?:of|or) my own\)\s*$', '', text, flags=re.I)
    if group == 'blues.trousers':
        text = re.sub(r'^\s*(\d+)\s*m([srl])\s*$',r'\1 MIS \2',text,flags=re.I)
    if group == 'blues.rank' and re.search(r'\bcloth\b',text,re.I):
        text = re.sub(r'\bno hard ranks?\b','',text,flags=re.I)
    if group in ('ocp.rank','blues.rank'):
        text = re.sub(r'\b(?:cadet\s+)?(?:fourth|4th)[ -]+class\b','C/4C',text,flags=re.I)
        text = re.sub(r'\b(?:cadet\s+)?(?:third|3rd)[ -]+class\b','C/3C',text,flags=re.I)
        text = re.sub(r'\b(?:as\s*200(?:\s+patch)?|200\s+rank|gmc\s+200)\b(?:\s*\(C/3C\))?', 'C/3C', text, flags=re.I)
        text = re.sub(r'\b(?:as\s*100(?:\s+patch)?|100\s+rank|gmc\s+100)\b(?:\s*\(C/4C\))?', 'C/4C', text, flags=re.I)
    entered = canonical(text)
    if group == 'ocp.flag' and set(entered) <= {'ocp','flag','patch','us'} and 'flag' in entered:
        return [cat for cat in catalog if cat.get('group') == group]
    if group == 'ocp.afrotc' and set(entered) <= {'ocp','afrotc','patch'} and 'afrotc' in entered:
        return [cat for cat in catalog if cat.get('group') == group]
    if group in ('ocp.afrotc','ocp.flag') and re.fullmatch(r'\s*standard issue(?:,\s*velcro back)?\s*',text,re.I):
        return [cat for cat in catalog if cat.get('group') == group]
    matches = []
    for cat in catalog:
        if cat.get('group') != group:
            continue
        if style:
            name = cat['name'].casefold()
            matches_style = {
                'dryfit': bool(re.search(r'dry[\s-]*fit|t-shirt,\s*athlete,\s*gray', name)),
                'cotton': bool(re.search(r'\bphysical training\b', name)) and bool(cat.get('official', True)),
                'general purpose': 'general purp' in name,
                'running': bool(re.search(r'\brunning (?:pt )?shorts?\b', name)),
            }
            if not matches_style[style]:
                continue
        size = canonical(cat['size'])
        if group.startswith('ptg.') and not size:
            continue
        if group in ('ocp.rank','blues.rank') and size[:1] == ['gmc'] and len(size) > 2:
            size = size[2:]
        if group in ('ocp.flag', 'ocp.afrotc'):
            size = [word for word in size if word != 'ocp']
        remaining = list(entered)
        if style == 'general purpose' and len(size) == 1 and remaining == size + ['r']:
            remaining.pop()
        if suggest_incomplete and group in ('ocp.boots','ptg.shorts','ptg.pants','ptg.jacket') and len(size) > 1:
            size = size[:1]
        if suggest_incomplete and group == 'ocp.socks' and entered == ['brown']:
            size = []
        if size and size != ['onesize']:
            # Contiguous size tokens prevent S-R from accidentally matching R-S.
            positions = [i for i in range(len(remaining)-len(size)+1) if remaining[i:i+len(size)] == size]
            if not positions:
                continue
            start = positions[0]; del remaining[start:start+len(size)]
        descriptor = canonical(cat['name'] + ' ' + cat.get('subcategory', ''))
        sex = str(cat.get('sex', '')).upper()
        if sex in ('M', 'F'):
            descriptor += ['male' if sex == 'M' else 'female']
        elif group == 'ptg.shirt' and style == 'dryfit' and re.search(r't-shirt,\s*athlete,\s*gray', cat['name'], re.I):
            descriptor += ['male']
        elif group in ('ocp.coat','ocp.trousers','ocp.fleece') and size and size[0] in ('xs','s','m','l','xl','xxl','xxxl'):
            descriptor += ['male']
        if group in ('ocp.coat', 'ocp.trousers') and 'summer' not in descriptor:
            descriptor += ['allweather']
        # Brown/tan is the standard OCP context for these specific garment groups.
        if group in ('ocp.fleece', 'ocp.shirt', 'ocp.belt', 'ocp.afrotc'):
            descriptor += ['brown', 'tan']
        if size == ['onesize']:
            descriptor += ['onesize']
        allowed = Counter(descriptor)
        if all(n <= allowed[w] for w, n in Counter(remaining).items()):
            # Empty text must not choose an arbitrary one-size item.
            if entered:
                matches.append(cat)
    return matches
