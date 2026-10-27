"""Quantity-first bag-drag questionnaire, separate from exact catalog IDs."""
QUESTIONS=[
 ('ocp.cover','OCP','Patrol caps / covers'),('ocp.coat','OCP','Blouses / coats'),
 ('ocp.trousers','OCP','Trousers'),('ocp.shirt','OCP','Undershirts'),('ocp.boots','OCP','Boots (pairs)'),
 ('ocp.belt','OCP','Rigger belts'),('ocp.socks','OCP','Socks (pairs)'),('ocp.fleece','OCP','Fleece jackets'),
 ('ocp.afrotc','OCP','AFROTC patches'),('ocp.flag','OCP','Flag patches'),('ocp.rank','OCP','Rank patches'),
 ('ocp.other','OCP','Other OCP items'),
 ('ptg.shirt','PTGs','PT shirts'),('ptg.shorts','PTGs','PT shorts'),('ptg.pants','PTGs','PT pants'),
 ('ptg.jacket','PTGs','PT jackets'),('ptg.other','PTGs','Other PTG items'),
 ('blues.cover','Blues','Flight caps / covers'),('blues.shirt','Blues','Blues shirts'),
 ('blues.trousers','Blues','Trousers / slacks'),('blues.skirt','Blues','Skirts'),('blues.shoes','Blues','Dress shoes (pairs)'),
 ('blues.belt','Blues','Belts / buckles'),('blues.tie','Blues','Ties'),('blues.tietab','Blues','Tie tabs'),('blues.rank','Blues','Cloth / metal ranks'),
 ('blues.jacket','Blues','Lightweight jackets / windbreakers'),('blues.other','Blues','Other blues items'),
 ('service.coat','Service dress','Service dress coats'),('service.cap','Service dress','Service / wheel caps'),
 ('service.other','Service dress','Other service dress items'),
 ('other.flight','Other uniforms','Flight suits'),('other.other','Other uniforms','Other uniform items')]

def question_for(item):
    text=' '.join(str(item.get(k,'')) for k in ('item_name','category','subcategory')).casefold()
    name=str(item.get('item_name','')).casefold()
    # Broad categories such as PANTS/SKIRT and Shorts/Pants are not item types.
    # Prefer the actual name, then the more specific subcategory.
    details=(name,str(item.get('subcategory','')).casefold())
    if 'afrotc patch' in name and 'colored' not in name:return 'ocp.afrotc'
    if 'brown cotton shirt' in name:return 'ocp.shirt'
    if 'nametape' in name or 'name tape' in name:return 'ocp.other'
    if 'service coat' in text or 'service dress coat' in text:return 'service.coat'
    if 'service cap' in text or 'wheel cap' in text:return 'service.cap'
    if 'flight suit' in text:return 'other.flight'
    if 'tie tab' in text or 'tie-tab' in text:return 'blues.tietab'
    if any(x in text for x in ('ocp','patrol','coyote','rigger')):
        for detail in details:
            for words,key in [(('afrotc','af rotc'),'afrotc'),(('flag',),'flag'),(('rank','insignia'),'rank'),(('patrol','cap','cover'),'cover'),(('fleece',),'fleece'),(('boot',),'boots'),(('sock',),'socks'),(('belt','rigger'),'belt'),(('t-shirt','tshirt','undershirt','shirt tan'),'shirt'),(('trouser','pant'),'trousers'),(('blouse','coat','shirt'),'coat')]:
                if any(word in detail for word in words):return 'ocp.'+key
        return 'ocp.other'
    if any(x in text for x in ('physical training','ptg','ptu','iptu','pt wear','track',' pt ','pt shirt','pt pant','pt jacket','pt short')):
        for detail in details:
            for words,key in [(('short','trunk'),'shorts'),(('pant',),'pants'),(('jacket',),'jacket'),(('shirt',),'shirt')]:
                if any(word in detail for word in words):return 'ptg.'+key
        return 'ptg.other'
    if any(x in text for x in ('blues','blue','flight cap','lightweight','windbreaker','shirt, mens','shirt, womens','trousers, mens','slacks','shoes, mens','shoes, womens','tie','buckle')):
        for detail in details:
            for words,key in [(('rank','insignia'),'rank'),(('cap','cover'),'cover'),(('skirt',),'skirt'),(('trouser','slack','pant'),'trousers'),(('shoe',),'shoes'),(('buckle','belt'),'belt'),(('tie',),'tie'),(('jacket','windbreaker'),'jacket'),(('shirt',),'shirt')]:
                if any(word in detail for word in words):return 'blues.'+key
        return 'blues.other'
    return 'other.other'
