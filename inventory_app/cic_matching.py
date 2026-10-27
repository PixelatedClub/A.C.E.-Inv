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
        (r'all[ -]?weather|cold[ -]?weather|\bcold\b|\bawb\b|\bawp\b', 'allweather'),
        (r'summer[ -]?weight|\bsummer\b|hot[ -]?weather|\bhot\b|\bihwcu\b|\bswb\b', 'summer'),
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
    aliases = {'small':'s', 'smal':'s', 'sm':'s', 'medium':'m', 'meduim':'m', 'med':'m', 'large':'l', 'lg':'l',
               'regular':'r', 'reg':'r', 'regualr':'r', 'short':'s', 'sh':'s', 'sht':'s',
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
    return row.strip(), None


def match_human(text, group, catalog):
    entered = canonical(text)
    matches = []
    for cat in catalog:
        if cat.get('group') != group:
            continue
        size = canonical(cat['size'])
        if group in ('ocp.flag', 'ocp.afrotc'):
            size = [word for word in size if word != 'ocp']
        remaining = list(entered)
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
