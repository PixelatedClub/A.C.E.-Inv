import unittest
from inventory_app.cic_matching import canonical, match_human
from inventory_app.cic_sharepoint import FIELDS, parse_answers


def item(no, group, name, size, sex=''):
    return dict(item_no=no, group=group, name=name, size=size, sex=sex)


class HumanCicTests(unittest.TestCase):
    def setUp(self):
        self.catalog = [item('1','ocp.cover','OCP Patrol Cap','7-3/8'),
            item('2','ocp.coat','OCP COAT','S-R'),
            item('3','ocp.coat','COAT OCP IHWCU','S-R'),
            item('4','ocp.shirt','OCP Undershirt','MEDIUM'),
            item('5','ocp.fleece','FLEECE JACKET OCP','MED/REG'),
            item('6','ocp.boots','Coyote boots','10.5R','M'),
            item('7','ocp.boots','Coyote boots','10.5R','F'),
            item('8','ocp.rank','OCP Rank Patch','C/2D LT')]
    def answers(self, key, count, sizes):
        a={k:'' for k,_ in FIELDS}
        a.update(first_name='Jane',last_name='Example',email='jane@example.invalid')
        a.update({k:'No' for k in a if k.endswith(('.has_items','.has_item'))})
        a[key.split('.')[0]+'.has_items']='Yes';a[key+'.has_item']='Yes'
        a[key+'.count']=str(count);a[key+'.sizes']=sizes
        return a
    def test_case_abbreviations_and_limited_known_typos(self):
        for text in ['medium regular brown','MED REG','m-r','MR','meduim regualr']:
            self.assertEqual(match_human(text,'ocp.fleece',self.catalog)[0]['item_no'],'5')
    def test_fraction_and_context_do_not_need_item_id(self):
        parsed,issues=parse_answers(self.answers('ocp.cover',2,'7 3/8'),self.catalog)
        self.assertEqual(issues,[]);self.assertEqual(parsed['lines'][0]['quantity'],2)
        self.assertEqual(parsed['lines'][0]['item_no'],'1')
    def test_decimal_fraction_unicode_and_words_agree(self):
        catalog=[item('hat','ocp.cover','OCP Patrol Cap','7-1/2')]
        for size in ['7.5','7.50','7 1/2','7-1/2','7½','seven and a half','seven point five','Size 7.5','it is a size seven and one half']:
            with self.subTest(size=size):
                parsed,issues=parse_answers(self.answers('ocp.cover','one',size),catalog)
                self.assertFalse(issues);self.assertEqual(parsed['lines'][0]['item_no'],'hat')
        self.assertFalse(match_human('7.75','ocp.cover',catalog))
    def test_full_trouser_sizes_and_season_variants(self):
        catalog=[item('aw','ocp.trousers','TROUSERS, OCP','M-R'),
                 item('sw','ocp.trousers','TROUSERS, OCP IHWCU','M-R')]
        for size in ['medium regular','MED/REG','MR','m-r','Medium Regular']:
            self.assertEqual(len(match_human(size,'ocp.trousers',catalog)),2)
        for size in ['medium regular summer','Medium Regular HOT','mr ihwcu']:
            self.assertEqual([r['item_no'] for r in match_human(size,'ocp.trousers',catalog)],['sw'])
        self.assertEqual([r['item_no'] for r in match_human('medium regular all weather','ocp.trousers',catalog)],['aw'])
    def test_summer_and_all_weather_are_never_conflated(self):
        for text,no in [('Small regular HOT','3'),('S-R summer','3'),('sr all weather','2'),('small regular cold','2')]:
            self.assertEqual([c['item_no'] for c in match_human(text,'ocp.coat',self.catalog)],[no])
        parsed,issues=parse_answers(self.answers('ocp.coat',1,'s-r'),self.catalog)
        self.assertTrue(issues);self.assertEqual(parsed['lines'][0]['item_no'],'')
    def test_multiple_rows_and_explicit_quantities(self):
        a=self.answers('ocp.coat',3,'Small regular summer x2; SR cold x1')
        parsed,issues=parse_answers(a,self.catalog)
        self.assertFalse(issues);self.assertEqual([l['quantity'] for l in parsed['lines']],[2,1])
        a=self.answers('ocp.coat',2,'s-r hot\ns-r cold')
        self.assertFalse(parse_answers(a,self.catalog)[1])
        a['ocp.coat.count']='4'
        self.assertTrue(parse_answers(a,self.catalog)[1])
    def test_shoe_gender_and_width_must_resolve(self):
        self.assertEqual(len(match_human('10.5 regular','ocp.boots',self.catalog)),2)
        self.assertEqual([c['item_no'] for c in match_human('mens 10.5 regular','ocp.boots',self.catalog)],['6'])
        self.assertFalse(match_human('mens 10.5 wide','ocp.boots',self.catalog))
        self.assertFalse(match_human('10.5','ocp.boots',self.catalog))
    def test_rank_alias_and_no_arbitrary_fuzzy_matching(self):
        self.assertEqual(match_human('Cadet second lieutenant','ocp.rank',self.catalog)[0]['item_no'],'8')
        self.assertFalse(match_human('medium wrong item','ocp.shirt',self.catalog))
        self.assertFalse(match_human('7 1/0','ocp.cover',self.catalog))
    def test_mixed_explicit_implicit_quantities_do_not_guess(self):
        parsed,issues=parse_answers(self.answers('ocp.coat',3,'2 x s-r hot\ns-r cold'),self.catalog)
        self.assertTrue(issues)
    def test_count_mismatch_and_unknowns_remain_held(self):
        for text in ['Medium x3','mystery size']:
            self.assertTrue(parse_answers(self.answers('ocp.shirt',2,text),self.catalog)[1])
    def test_patch_color_instead_of_size_or_item_id(self):
        cat=[item('9','ocp.flag','American Flag Patch','OCP (SPICE BROWN)'),
             item('10','ocp.afrotc','AFROTC Patch','STANDARD')]
        for key,text in [('ocp.flag','spice brown'),('ocp.afrotc','1 spice brown')]:
            parsed,issues=parse_answers(self.answers(key,1,text),cat)
            self.assertFalse(issues);self.assertTrue(parsed['lines'][0]['item_no'])


if __name__=='__main__':unittest.main()
