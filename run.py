"""Independent public-feed pipeline; never reads personal workspace files."""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
import config

EXCLUDED = re.compile(r'数字健康|生命科学|药物|药品|制药|蛋白|基因组|转录组|\bdrugs?\b|pharmac|\bproteins?\b|genomic|transcriptom|proteomic|single.cell|digital.health|wearable|telehealth|telemedicine', re.I)
SLUGS = dict(zip(config.SECTIONS, config.SECTION_SLUGS))
config.SECTIONS[:] = [s for s in config.SECTIONS if s not in ('数字健康', '生命科学与药物')]
config.SECTION_SLUGS[:] = [SLUGS[s] for s in config.SECTIONS]
config.SECTION_HINTS = {k: v for k, v in config.SECTION_HINTS.items() if k in config.SECTIONS}
config.SITE.update(title='Lv 每日HOT · 医疗 AI 研究与落地', wordmark='Lv<b>HOT</b>',
                   tagline='医疗 AI 研究与落地日报',
                   url=os.getenv('SITE_URL', 'http://127.0.0.1:8783/'),
                   repo=os.getenv('REPOSITORY_URL', '#'),
                   disclaimer='自动收集的公开医疗 AI 信息，仅供研究参考；未配置模型时只提供原文元数据，不生成AI精读。预印本未经同行评审。')
config.PROMPT += '\n不收录数字健康、生命科学与药物方向。只有摘要或标题时明确阅读范围，不伪称阅读全文。'
import hub
hub.NAV[:] = [entry for entry in hub.NAV if entry[0] != 'papers']


def allowed(item):
    text = ' '.join([item.get('title', ''), item.get('zh_title', ''), *item.get('tags', [])])
    return item.get('section') not in ('数字健康', '生命科学与药物') and not EXCLUDED.search(text)


def collect(fetcher=hub.fetch_source, use_llm=False, max_new=None):
    limit = int(max_new if max_new is not None else os.getenv('MAX_NEW', '200'))
    if not 1 <= limit <= 500:
        raise ValueError('MAX_NEW must be between 1 and 500')
    if use_llm:
        for key in ('LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL'):
            if not os.getenv(key):
                raise RuntimeError('Missing model setting: ' + key)
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        results = list(pool.map(fetcher, config.SOURCES))
    hub.update_status(results)
    if all(error for _, _, error in results):
        raise RuntimeError('All sources failed; retained the last successful digest.')
    previous = json.loads(Path('data/items.json').read_text(encoding='utf-8')) if Path('data/items.json').exists() else []
    pending = [p for p in previous if use_llm and p.get('processing') == 'metadata-only']
    pending_ids = {p['id'] for p in pending}
    previous = [p for p in previous if p['id'] not in pending_ids]
    rejected = hub.load_rejected() if use_llm else {}
    seen = {p['id'] for p in previous} | set(rejected)
    candidates = [dict(p, desc=p.get('abstract', '')) for p in pending]
    seen.update(pending_ids)
    for source, rows, _ in results:
        for item in rows:
            published = hub.parse_date(item.get('date', ''), None)
            if not published or published < hub.NOW - dt.timedelta(days=source.get('max_age', 10)):
                continue
            if item['id'] in seen or not allowed(item):
                continue
            seen.add(item['id'])
            duplicate = next((p for p in previous + candidates if hub.similar(item['title'], p['title'])), None)
            if duplicate:
                hub.add_also(duplicate, item)
                continue
            candidates.append(item)
    # Source-balanced selection; no claim that metadata ranking is a full-paper review.
    picked = hub.select(candidates, limit)
    if use_llm:
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            list(pool.map(hub.fill_abstract, picked))
        done = [p for p in hub.enrich_all(picked) if allowed(p)]
        hub.save_pool(picked)
        hub.save_rejected(rejected, picked)
        failed = sum(p.get('_verdict') is None for p in picked)
        if picked and failed == len(picked):
            raise RuntimeError('Model returned no usable results; retained previous digest for retry.')
        for p in done:
            p['processing'] = 'model-enriched'
            abstract = p.pop('desc', '') or ''
            if not p.get('thin') and len(abstract) >= 200 and not hub.is_teaser(abstract):
                p['abstract'] = abstract
        hub.translate_all(done)
        for p in done:
            p['day'] = hub.TODAY
        hub.backfill(previous + done, results)
        done = hub.cluster(done, [p for p in previous if p.get('day', '') >= (hub.NOW - dt.timedelta(days=3)).strftime('%Y-%m-%d')])
    else:
        done = []
        for raw in picked:
            p = dict(raw, score=None, zh_title='', tags=[], evidence='待核验',
                     summary='未接入模型：仅提供公开题名与原始摘要，不是 AI 精读结论。',
                     abstract=raw.get('desc', ''), key_points=[], thin=False, processing='metadata-only')
            p['section'] = hub.section_of(p)
            done.append(p)
    for p in done:
        p.pop('_verdict', None)
        p['day'] = hub.TODAY
    cutoff = (hub.NOW - dt.timedelta(days=30)).strftime('%Y-%m-%d')
    # Keep metadata-only entries outside this round's budget or with a failed verdict for later retry.
    completed = {p['id'] for p in done} | set(rejected)
    previous += [p for p in pending if p['id'] not in completed]
    db = [p for p in previous if p.get('day', '') >= cutoff and allowed(p)] + [p for p in done if allowed(p)]
    db.sort(key=lambda p: (p.get('day', ''), hub.rank(p)), reverse=True)
    Path('data/items.json').write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding='utf-8')
    for day in {p['day'] for p in db}:
        hub.save_archive_day(day, [p for p in db if p['day'] == day])
    return db, {'candidates': len(candidates), 'processed': len(picked), 'selected': len(done), 'model': use_llm, 'budget': limit}


def build(db):
    # Remove only obsolete generated library entrypoints, never personal literature data.
    for file in (Path('site/conf.json'), Path('site/papers/index.html')):
        file.unlink(missing_ok=True)
    if not getattr(hub, '_local_template_ready', False):
        original_open = hub.__dict__.get('open', open)
        hub.open = lambda filename, *a, **kw: original_open(ROOT / 'vendor/template.html' if filename == 'template.html' else filename, *a, **kw)
        hub._local_template_ready = True
    hub.build(db, None)
    if not db:
        home = Path('site/index.html')
        html = home.read_text(encoding='utf-8').replace('<div id="feed">', '<p class="muted">尚无已生成的日报；请查看数据源状态或执行首次检索。空页面不代表39个来源均无新增。</p><div id="feed">')
        home.write_text(html, encoding='utf-8')
    for p in db:
        if p.get('processing') == 'metadata-only':
            item = Path('site/items') / p['id'] / 'index.html'
            if item.exists():
                html = item.read_text(encoding='utf-8').replace('导读与中文摘要由 AI 生成 / 翻译，仅供参考，请以原文为准；不构成医疗建议。', '本条未调用模型，只提供原文元数据；没有生成中文AI导读或精读报告。')
                item.write_text(html, encoding='utf-8')
    # Candidate counters are distinct from the number finally retained by the model.
    file = Path('site/status.html')
    html = file.read_text(encoding='utf-8').replace('连续 3 次为 0 会自动开 issue', '连续3次为0由GitHub工作流更新告警issue；零条不一定是故障。表中为候选量，不是最终入选量')
    run_status = json.loads(Path('data/run-status.json').read_text(encoding='utf-8')) if Path('data/run-status.json').exists() else {}
    if run_status.get('state') == 'failed':
        html = html.replace('<main class="wrap">', '<main class="wrap"><p class="muted">本轮生成失败，保留上次成功内容。请检查GitHub Actions日志；不能把旧内容当作今日新日报。</p>')
    file.write_text(html, encoding='utf-8')
    for relative, fallback in [('items.json', []), ('status.json', {'runs': [], 'streak': {}})]:
        src = Path('data') / relative
        (Path('site') / relative).write_text(src.read_text(encoding='utf-8') if src.exists() else json.dumps(fallback), encoding='utf-8')
    for page in Path('site').rglob('*.html'):
        html = page.read_text(encoding='utf-8')
        html = html.replace('<script async src="https://busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js"></script>', '')
        html = html.replace('</footer>', '<p style="text-align:center">Adapted from <a href="https://github.com/ChunXiaostudy/AI4Health-Hub">AI4Health-Hub</a> · MIT · Copyright © 2026 ChunXiaostudy</p></footer>')
        page.write_text(html, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--llm', action='store_true')
    parser.add_argument('--weekly', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ.setdefault('PYTHONUTF8', '1')
    Path('data').mkdir(exist_ok=True)
    if args.build_only:
        db = json.loads(Path('data/items.json').read_text(encoding='utf-8')) if Path('data/items.json').exists() else []
    else:
        try:
            db, stats = collect(use_llm=args.llm)
        except Exception:
            Path('data/run-status.json').write_text(json.dumps({'state':'failed','at':hub.NOW.isoformat()}),encoding='utf-8')
            raise
        Path('data/run-status.json').write_text(json.dumps({'state':'done','at':hub.NOW.isoformat(),'model':args.llm}),encoding='utf-8')
        Path('data/selection.json').write_text(json.dumps(stats), encoding='utf-8')
    if args.weekly or (not args.build_only and hub.NOW.astimezone(hub.CST).weekday() == 0):
        from weekly import generate
        generate(hub, allowed, use_llm=args.llm)
    build(db)


if __name__ == '__main__':
    main()
