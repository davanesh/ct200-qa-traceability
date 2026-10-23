from app.service import parse_document

def test_skipped_heading_depth_attaches_nearest_existing_parent():
    nodes=parse_document('1 Root\n1.1 Child\n1.1.1.1 Deep heading\nText')
    deep=nodes[-1]
    assert deep['level']==4
    assert deep['parent_num']=='1.1'

def test_out_of_order_siblings_keep_source_order_and_parent():
    nodes=parse_document('3 Operation\n3.4 Later numbered\nBody 4\n3.3 Earlier numbered\nBody 3')
    assert [n['num'] for n in nodes]==['3','3.4','3.3']
    assert nodes[1]['parent_num']==nodes[2]['parent_num']=='3'

def test_duplicate_headings_are_distinct_nodes():
    nodes=parse_document('1 First\n1.1 Error Codes\nA\n2 Second\n2.1 Error Codes\nB')
    matches=[n for n in nodes if n['heading']=='Error Codes']
    assert len(matches)==2
    assert matches[0]['parent_num']=='1'
    assert matches[1]['parent_num']=='2'
