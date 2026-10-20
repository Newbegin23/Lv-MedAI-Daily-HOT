"""Human-labelled scoring evaluation; offline mode never calls a model."""
import argparse
import csv
import json
from pathlib import Path
import random
import statistics

LABELS = {'精选': 2, '收录': 1, '不收': 0}


def label_for(score):
    score = float(score or 0)
    return '精选' if score >= 7 else '收录' if score >= 3 else '不收'


def ranks(values):
    return [1 + sum(v < x for v in values) + (sum(v == x for v in values) - 1) / 2 for x in values]


def sample(n):
    pool = {}
    for file in sorted(Path('data/pool').glob('*.jsonl')):
        for line in file.read_text(encoding='utf-8').splitlines():
            if line.strip():
                row = json.loads(line); pool[row['id']] = row
    if not pool:
        for file in sorted(Path('data/archive').glob('*.json')):
            for row in json.loads(file.read_text(encoding='utf-8')):
                pool[row['id']] = {**row, 'model_score': row.get('score'), 'model_keep': True}
    target = Path('eval/labels.csv'); target.parent.mkdir(exist_ok=True)
    old = list(csv.DictReader(target.open(encoding='utf-8-sig', newline=''))) if target.exists() else []
    known = {p['id'] for p in old}
    groups = {}
    for row in pool.values():
        if row['id'] not in known:
            groups.setdefault((row.get('source'), label_for(row.get('model_score'))), []).append(row)
    rng = random.Random(0)
    for rows in groups.values(): rng.shuffle(rows)
    chosen = []
    while len(chosen) < n and any(groups.values()):
        for rows in groups.values():
            if rows and len(chosen) < n: chosen.append(rows.pop())
    fields = ['id', 'title', 'source', 'score', 'model_keep', 'label', 'note', 'input_json']
    with target.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields); writer.writeheader(); writer.writerows(old)
        for p in chosen:
            writer.writerow(dict(id=p['id'], title=p.get('title', ''), source=p.get('source', ''), score=p.get('model_score', ''), model_keep=p.get('model_keep'), label='', note='', input_json=json.dumps(p, ensure_ascii=False)))
    print(f'Added {len(chosen)} samples to {target}; label them manually before evaluation.')


def evaluate(offline=True):
    target = Path('eval/labels.csv')
    if not target.exists(): raise ValueError('First run sample and add human labels.')
    rows = [p for p in csv.DictReader(target.open(encoding='utf-8-sig', newline='')) if p['label'] in LABELS]
    if not rows: raise ValueError('No valid human labels; no evaluation claimed.')
    if not offline:
        import run
        for key in ('LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL'):
            if not run.os.getenv(key): raise ValueError('Missing model configuration: ' + key)
        for p in rows:
            raw = json.loads(p['input_json']); raw['desc'] = raw.get('desc') or raw.get('abstract') or ''
            result = run.hub.enrich([raw])
            if raw.get('_verdict') is None: raise RuntimeError('Model evaluation incomplete; old report retained.')
            p['score'] = result[0].get('score') if result else 0
    predicted = [label_for(p['score']) if str(p.get('model_keep')).lower() != 'false' or not offline else '不收' for p in rows]
    truth = [p['label'] for p in rows]
    tp = sum(a == b == '精选' for a, b in zip(truth, predicted))
    precision = tp / predicted.count('精选') if '精选' in predicted else None
    recall = tp / truth.count('精选') if '精选' in truth else None
    scores = [float(p['score'] or 0) for p in rows]
    x, y = ranks(scores), ranks([LABELS[v] for v in truth])
    spearman = statistics.correlation(x, y) if len(rows) > 1 and len(set(x)) > 1 and len(set(y)) > 1 else None
    fmt = lambda v: '不可计算（样本不足或分母为零）' if v is None else f'{v:.3f}'
    text = f'# 评分评测\n\n人工标签样本：{len(rows)}；模式：{"离线历史分数" if offline else "当前提示词重评分"}。\n\n精选阈值≥7；收录阈值≥3。\n\n- 精选 precision：{fmt(precision)}\n- 精选 recall：{fmt(recall)}\n- Spearman：{fmt(spearman)}\n\n## 主要分歧\n'
    for p, actual in zip(rows, predicted):
        if p['label'] != actual: text += f"- {p['title']}：人工 {p['label']}，模型 {actual}（{p['score']}）；{p['note']}\n"
    Path('eval/last_report.md').write_text(text, encoding='utf-8'); print(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['sample', 'run']); parser.add_argument('--n', type=int, default=100); parser.add_argument('--offline', action='store_true'); args = parser.parse_args()
    sample(args.n) if args.action == 'sample' else evaluate(args.offline)
