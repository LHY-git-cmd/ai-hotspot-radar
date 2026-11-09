"""报告契约纯函数/本地能力边界，22项独立预期；无数据库/Provider。"""

from copy import deepcopy
import pytest

from services.research.report_validation import validate_candidate,verify_envelope,default_candidate,attempt_state,check_previous
from services.research.report_confirmation import LocalReportReviewSession,verify_intent,HumanConfirmationIntent
from tests.research_report_cases import CASES,ERRORS,mutate,block


def bundle():
    e={'evidence_id':1,'question_id':'Q1','statement_ref':'atom-1','template_id':'evidence_statement',
       'claim':{'entity':'Oracle','metric':'revenue','value':'20','unit':'%', 'basis':'year_over_year','speaker':'company'},
       'quality':{'final_category':'single_source','independence_status':'unknown'},
       'temporal':{'temporal_type':'unknown','event_kind':'actual_result','speaker_kind':'company',
           'fiscal_year':2027,'fiscal_quarter':1,'coverage_start':None,'coverage_end':None,'label_raw':'FY2027 Q1'},
       'source_bindings':[{'source_id':1,'quote':'fixed quote','snapshot_hash':'fixed'}]}
    return {'questions':[{'id':'Q1'}],'evidence_catalog':[e],
       'mandatory_gaps':[{'gap_id':'g1','question_id':'Q1','detail':'单来源，周期未知','code':'single_origin'}],
       'basis':{'project_id':1,'production_project_id':1,'research_run_id':1,'evidence_analysis_id':1,'evidence_set_hash':'pool-1'},
       'model_materials_hash':'model-1'}


@pytest.mark.parametrize('case_id',CASES)
def test_case(case_id):
    b=bundle();c=default_candidate(b)
    if case_id in ERRORS:
        invalid=mutate(c,b,case_id)
        with pytest.raises(ValueError) as caught:validate_candidate(invalid,b,checked_at='fixed')
        assert caught.value.diagnostic['code']==ERRORS[case_id]
    elif case_id=='R14':
        assert attempt_state({'status':'failed'},'provider')=='provider_failed'
        assert attempt_state({'status':'uncertain'})=='uncertain'
    elif case_id=='R16':
        doc=validate_candidate(c,b,checked_at='fixed')
        doc['document']['categories']['single_source'][0]['claim']['value']='999'
        with pytest.raises(ValueError,match='报告'):verify_envelope(doc,b)
    elif case_id=='R17':
        check_previous(1,1)
        with pytest.raises(ValueError):check_previous(2,1)
        with pytest.raises(ValueError):check_previous(True,1)
    elif case_id=='R18':
        doc=validate_candidate(c,b,checked_at='fixed')
        b['basis']['evidence_set_hash']='new-pool'
        with pytest.raises(ValueError):verify_envelope(doc,b)
    elif case_id=='R20':
        doc=validate_candidate(c,b,checked_at='fixed');report={'id':2,'content':doc}
        for intent in (None,{},HumanConfirmationIntent()):
            with pytest.raises(ValueError):verify_intent(intent,1,report,'action')
    elif case_id=='R21':
        doc=validate_candidate(c,b,checked_at='fixed');report={'id':2,'content':doc}
        intent=LocalReportReviewSession().reviewed(1,report,checked=True)
        assert verify_intent(intent,1,report,'action')['origin']=='local_interactive_operator'
        with pytest.raises(ValueError):verify_intent(intent,2,report,'action')
    elif case_id=='R22':
        with pytest.raises(ValueError) as caught:verify_envelope({'basis':{},'document':{}},b)
        assert caught.value.diagnostic['code']=='report_legacy_unreviewed'
    else:
        doc=validate_candidate(c,b,checked_at='fixed')
        assert verify_envelope(doc,b)==doc
        assert doc['document']['categories']['verified']==[]
        assert doc['document']['categories']['single_source'][0]['temporal']['fiscal_year']==2027
        assert doc['document']['categories']['gaps'][0]['gap_id']=='g1'


@pytest.mark.parametrize('field',['source_id','url','quote','text','actor','validation','final_category'])
def test_model_has_no_free_text_source_or_authority_channel(field):
    b=bundle();c=default_candidate(b);c[field]='Bearer synthetic-token'
    with pytest.raises(ValueError):validate_candidate(c,b,checked_at='fixed')


@pytest.mark.parametrize('grade,template',[('opinion','attributed_opinion'),('inference','limited_inference'),
    ('disputed','preserve_dispute'),('unverified','unresolved_lead'),('single_source','evidence_statement')])
def test_grade_inheritance_and_no_cross_grade_template(grade,template):
    b=bundle();e=b['evidence_catalog'][0];e['quality']['final_category']=grade;e['template_id']=template
    c=default_candidate(b);c['question_sections'][0]['blocks']=[block(e,slot='premise' if grade=='inference' else 'evidence')]
    doc=validate_candidate(c,b,checked_at='fixed')
    assert doc['document']['categories'][grade][0]['category']==grade
    if grade!='single_source':
        c['question_sections'][0]['blocks'][0]['template_id']='evidence_statement'
        with pytest.raises(ValueError):validate_candidate(c,b,checked_at='fixed')
