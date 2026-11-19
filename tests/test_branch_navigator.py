"""Offline regression tests for advisory-only branch navigation."""
import importlib.util
from pathlib import Path
import sys
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'branch_navigator.py'
spec = importlib.util.spec_from_file_location('branch_navigator', MODULE)
nav = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = nav
spec.loader.exec_module(nav)


def branch(name, sha, protected=False):
    return {'name': name, 'commit': {'sha': sha}, 'protected': protected}


def pr(head, base, draft=False):
    return {'head': {'ref': head, 'repo': {'full_name': 'owner/repo'}},
            'base': {'ref': base, 'repo': {'full_name': 'owner/repo'}},
            'html_url': f'https://github.com/owner/repo/pull/{head}', 'draft': draft}


def data(branch_list=None, prs=None, compares=None, ancestry=None, ci=None, selected='main'):
    branches = branch_list or [branch('main','sha-main',True), branch('feature','sha-feature')]
    ci = ci or {b['name']: {'green': True, 'blockers': []} for b in branches}
    compare = compares or {b['name']: {'ahead_by': 1, 'behind_by': 0} for b in branches if b['name'] != 'main'}
    return nav.plan(branches, prs or [], 'main', selected, compare, ancestry or {}, ci, ['Ethos Aegis CI'])


class PlanTests(unittest.TestCase):
    def test_no_pr_only_compare_not_merge(self):
        row = data()['next']
        self.assertEqual(row['action'], 'COMPARE')
        self.assertEqual(row['base'], 'main')

    def test_ready_pr_has_human_gate(self):
        row = data(prs=[pr('feature','main')])['next']
        self.assertEqual(row['action'], 'REVIEW_MERGE')
        self.assertIn('merge box', row['reason'])

    def test_behind_head_requires_sync(self):
        row = data(prs=[pr('feature','main')], compares={'feature': {'ahead_by': 1, 'behind_by': 4}})['next']
        self.assertEqual(row['action'], 'SYNC')

    def test_non_green_ci_never_merge(self):
        ci = {'main': {'green': True, 'blockers': []}, 'feature': {'green': False, 'blockers': ['check:unit=failure']}}
        self.assertEqual(data(prs=[pr('feature','main')], ci=ci)['next']['action'], 'FIX_CI')

    def test_default_red_blocks_merge(self):
        ci = {'main': {'green': False, 'blockers': ['missing-workflow:security']}, 'feature': {'green': True, 'blockers': []}}
        self.assertEqual(data(prs=[pr('feature','main')], ci=ci)['next']['action'], 'FIX_BASE_CI')

    def test_delete_requires_exact_ancestry_and_green_default(self):
        self.assertEqual(data(ancestry={'feature': True})['next']['action'], 'DELETE')
        self.assertEqual(data(ancestry={'feature': False})['next']['action'], 'COMPARE')

    def test_delete_forbidden_if_head_or_base_open_pr(self):
        rows = data(prs=[pr('feature','main')], ancestry={'feature': True})['branches']
        self.assertNotEqual(rows[0]['action'], 'DELETE')
        branches = [branch('main','sha-main',True), branch('parent','sha-parent'), branch('child','sha-child')]
        rows = data(branch_list=branches, prs=[pr('child','parent')],
                    ancestry={'parent': True,'child': False})['branches']
        self.assertEqual(next(r for r in rows if r['head']=='parent')['action'], 'COMPARE')

    def test_protected_and_selected_base_are_retained(self):
        self.assertTrue(data(branch_list=[branch('main','s1',True),branch('feature','s2',True)])['complete'])
        self.assertEqual(data(branch_list=[branch('main','s1',True),branch('feature','s2',True)])['branches'][0]['action'], 'RETAIN')

    def test_custom_base_does_not_form_self_cycle(self):
        branches=[branch('main','a',True),branch('integration','b'),branch('feature','c')]
        rows=data(branch_list=branches,selected='integration')['branches']
        self.assertEqual(next(r for r in rows if r['head']=='integration')['action'], 'RETAIN')
        self.assertEqual(next(r for r in rows if r['head']=='feature')['base'], 'integration')
        self.assertEqual(next(r for r in rows if r['head']=='feature')['action'], 'COMPARE')

    def test_dependencies_parent_first(self):
        branches=[branch('main','a',True),branch('parent','b'),branch('child','c')]
        rows=data(branch_list=branches,prs=[pr('parent','main'),pr('child','parent')])['branches']
        self.assertEqual([x['head'] for x in rows], ['parent','child'])

    def test_cycles_no_recommendation_to_merge(self):
        branches=[branch('main','a',True),branch('a','b'),branch('b','c')]
        rows=data(branch_list=branches,prs=[pr('a','b'),pr('b','a')])['branches']
        self.assertTrue(all(r['action']=='REVIEW_DEPENDENCY' for r in rows))

    def test_duplicate_or_missing_sha_fail_closed(self):
        with self.assertRaises(nav.EvidenceError):
            data(branch_list=[branch('main','a',True),branch('f','')])

    def test_complete_requires_default_ci_green(self):
        res=data(branch_list=[branch('main','a',True)])
        self.assertTrue(res['complete'])
        res=data(branch_list=[branch('main','a',True)], ci={'main':{'green': False,'blockers':['bad']}})
        self.assertFalse(res['complete'])

    def test_markdown_has_next_link_and_sha(self):
        res=data(prs=[pr('feature','main')]);res['created_at']='2026-11-19T00:00:00+00:00'
        md=nav.render(res,'owner/repo')
        self.assertIn('**NEXT — REVIEW_MERGE**',md)
        self.assertIn('sha-feature',md)
        self.assertIn('does not authorize',md)


class FakeAPI:
    def __init__(self, checks, statuses, runs):
        self.checks, self.statuses, self.runs = checks, statuses, runs
    def pages(self, path, field=None):
        if 'check-runs' in path: return self.checks
        if '/actions/runs' in path: return self.runs
        raise AssertionError(path)
    def one(self, path):
        if '/status' in path: return {'statuses': self.statuses}
        raise AssertionError(path)


class EvidenceTests(unittest.TestCase):
    def test_expected_workflow_missing_is_red(self):
        e=nav.GitHub.evidence(FakeAPI([],[],[]),'abc',['Ethos Aegis CI'])
        self.assertFalse(e['green'])
        self.assertIn('missing-workflow:Ethos Aegis CI',e['blockers'])

    def test_successful_evidence_is_green(self):
        a=FakeAPI([{'app':{'id':1},'name':'lint','id':1,'status':'completed','conclusion':'success'}],
                  [{'context':'status','state':'success'}],
                  [{'workflow_id':1,'run_number':2,'run_attempt':1,'name':'Ethos Aegis CI','status':'completed','conclusion':'success'}])
        self.assertTrue(nav.GitHub.evidence(a,'abc',['Ethos Aegis CI'])['green'])

    def test_skipped_cancelled_neutral_and_pending_block(self):
        for conclusion in ['skipped','cancelled','neutral',None]:
            a=FakeAPI([{'app':{'id':1},'name':'lint','id':1,'status':'completed' if conclusion else 'queued','conclusion':conclusion}],[],[])
            self.assertFalse(nav.GitHub.evidence(a,'abc',[])['green'])

    def test_new_retry_supersedes_old_failure(self):
        runs=[{'workflow_id':1,'run_number':5,'run_attempt':1,'name':'Build','status':'completed','conclusion':'failure'},
              {'workflow_id':1,'run_number':5,'run_attempt':2,'name':'Build','status':'completed','conclusion':'success'}]
        self.assertTrue(nav.GitHub.evidence(FakeAPI([],[],runs),'abc',['Build'])['green'])

    def test_missing_api_payload_fails_closed(self):
        class Broken(FakeAPI):
            def one(self, path): return {}
        with self.assertRaises(nav.EvidenceError):
            nav.GitHub.evidence(Broken([],[],[]),'abc',[])

    def test_self_report_does_not_block_itself(self):
        runs=[{'workflow_id':1,'name':'Branch navigator','status':'in_progress','conclusion':None}]
        e=nav.GitHub.evidence(FakeAPI([],[],runs),'abc',[])
        self.assertIn('no-CI-evidence',e['blockers'])
        self.assertFalse(any('workflow:Branch navigator' in x for x in e['blockers']))


if __name__ == '__main__':
    unittest.main()
