import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.temp.name)
        Path('data').mkdir()

    def tearDown(self):
        os.chdir(self.old)
        self.temp.cleanup()

    def test_sources_filter_and_metadata_without_fake_ai(self):
        self.assertEqual(len(run.config.SOURCES), 39)
        def source(src):
            return src, [dict(id=src['name'], title='Medical AI segmentation ' + src['name'],
                             desc='Medical image segmentation research with a clinical model and independently evaluated medical image data. ' * 3,
                             source=src['name'], source_group=src['name'],
                             date=run.hub.NOW.isoformat(), link='https://example.org/' + str(len(src['name'])))], None
        db, stats = run.collect(source)
        self.assertLessEqual(len(db), 200)
        self.assertGreater(len(db), 8)
        self.assertTrue(db)
        self.assertTrue(all(p['score'] is None for p in db))
        self.assertTrue(all('未接入模型' in p['summary'] for p in db))
        self.assertEqual(len(json.loads(Path('data/status.json').read_text())['runs'][0]['sources']), 39)
        self.assertFalse(run.allowed({'title': 'Drug discovery agent'}))
        self.assertFalse(run.allowed({'title': 'Test', 'section': '数字健康'}))
        self.assertTrue(run.allowed({'title': 'Multi-agent image segmentation'}))
        second, _ = run.collect(source)
        self.assertEqual(len({p['id'] for p in second}), len(second))
        self.assertTrue({p['id'] for p in db}.issubset({p['id'] for p in second}))
        run.hub.fetch_favicons = lambda hosts: None
        run.build(second)
        self.assertTrue(Path('site/status.html').exists())
        self.assertTrue(Path('site/items.json').exists())
        self.assertNotIn('论文库', Path('site/index.html').read_text(encoding='utf-8'))
        self.assertFalse(Path('site/papers/index.html').exists())
        for p in db:
            self.assertIn('没有生成中文AI导读', (Path('site/items') / p['id'] / 'index.html').read_text(encoding='utf-8'))

    def test_all_failed_retains_previous_data(self):
        Path('data/items.json').write_text('[{"id":"saved"}]')
        with self.assertRaises(RuntimeError):
            run.collect(lambda src: (src, [], 'network unavailable'))
        self.assertEqual(json.loads(Path('data/items.json').read_text()), [{'id': 'saved'}])

    def test_full_model_path_uses_abstract_backfill_pool_and_translation(self):
        item = dict(id='a', title='Medical segmentation agent', desc='Medical image study. ' * 30,
                    source='PubMed', source_group='PubMed', link='https://example.org/a', date=run.hub.NOW.isoformat())
        def fetch(src): return src, [dict(item)] if src == run.config.SOURCES[0] else [], None
        def enrich(items):
            for p in items: p.update(_verdict=True, score=7, zh_title='医学分割智能体', tags=['医学影像'], evidence='同行评审', summary='测试导读')
            return items
        with patch.dict(os.environ, {'LLM_BASE_URL':'https://example.invalid','LLM_API_KEY':'test','LLM_MODEL':'test'}), patch.object(run.hub,'fill_abstract') as fill, patch.object(run.hub,'enrich_all',side_effect=enrich), patch.object(run.hub,'translate_all') as translate, patch.object(run.hub,'backfill') as backfill, patch.object(run.hub,'cluster',side_effect=lambda done, old: done):
            db, stats = run.collect(fetch, use_llm=True)
        self.assertEqual(stats['budget'],200); self.assertEqual(db[0]['processing'],'model-enriched')
        fill.assert_called_once(); translate.assert_called_once(); backfill.assert_called_once()
        self.assertTrue(list(Path('data/pool').glob('*.jsonl')))
        self.assertIn('abstract',db[0])

    def test_weekly_and_alerts(self):
        from weekly import generate
        from alerts import source_alerts
        import datetime as dt
        Path('data/archive').mkdir()
        p=dict(id='w', title='Medical imaging', source='PubMed', link='https://example.org/w', score=7, date='2026-10-18', day='2026-10-18', tags=[])
        Path('data/archive/2026-10-18.json').write_text(json.dumps([p]))
        target=generate(run.hub,run.allowed,today=dt.date(2026,10,19))
        self.assertTrue(target.exists()); self.assertIn('未调用模型',json.loads(target.read_text(encoding='utf-8'))['summary'])
        self.assertEqual(source_alerts({'streak':{'A':3,'B':2},'runs':[{'sources':{'A':{'error':None}}}]}),[('A',3,None)])

    def test_budget_and_scoring_evaluation(self):
        import evalset
        with self.assertRaises(ValueError): run.collect(max_new=0)
        Path('data/pool').mkdir()
        row={'id':'e','title':'Medical AI','source':'PubMed','model_score':8,'model_keep':True}
        Path('data/pool/test.jsonl').write_text(json.dumps(row)+'\n')
        evalset.sample(10)
        import csv
        file=Path('eval/labels.csv')
        with file.open(encoding='utf-8-sig',newline='') as reader: rows=list(csv.DictReader(reader))
        rows[0]['label']='精选'
        with file.open('w',encoding='utf-8-sig',newline='') as writer:
            output=csv.DictWriter(writer,fieldnames=rows[0].keys());output.writeheader();output.writerows(rows)
        evalset.evaluate(True)
        self.assertIn('precision：1.000',Path('eval/last_report.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
