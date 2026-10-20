"""Weekly synthesis from this project's archived public entries only."""
import datetime as dt
import json
from pathlib import Path
import re


def generate(hub, allowed, use_llm=False, today=None):
    today = today or hub.NOW.astimezone(hub.CST).date()
    end = today - dt.timedelta(days=today.weekday() + 1)
    start = end - dt.timedelta(days=6)
    week = start.strftime('%G-W%V')
    target = Path('data/weekly') / (week + '.json')
    if target.exists():
        return target
    items = {}
    for file in sorted(Path('data/archive').glob('*.json')):
        if start.isoformat() <= file.stem <= end.isoformat():
            for p in json.loads(file.read_text(encoding='utf-8')):
                if allowed(p):
                    items[p['id']] = p
    if not items:
        return None
    ordered = sorted(items.values(), key=hub.rank, reverse=True)[:50]
    summary = ''
    if use_llm:
        payload = [{'ref': i + 1, 'title': p.get('zh_title') or p['title'], 'summary': p.get('summary'),
                    'key_points': p.get('key_points'), 'evidence': p.get('evidence'), 'source': p['source']} for i, p in enumerate(ordered)]
        summary = hub.llm_raw([{'role': 'system', 'content': '仅根据输入条目写中文医疗AI周报，分研究进展、落地监管、产业动态、限制与待核实。只写输入支持的事实，不编造趋势或因果。每条关键结论用[编号]引用。只输出纯文本，不输出HTML。不包含数字健康、生命科学与药物。'},
                               {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}], want='text') or ''
        refs = [int(n) for n in re.findall(r'\[(\d+)\]', summary)]
        if not refs or any(n < 1 or n > len(ordered) for n in refs):
            raise RuntimeError('Weekly model returned missing/invalid references; previous reports retained.')
    else:
        summary = '本周条目汇总（未调用模型；不是AI综合解读）。\n' + '\n'.join(
            f"[{i+1}] {p.get('zh_title') or p['title']}；来源：{p['source']}。" for i, p in enumerate(ordered))
    result = {'week': week, 'range': f'{start} 至 {end}', 'generated': hub.NOW.isoformat(),
              'summary': summary, 'items': ordered, 'model': use_llm,
              'coverage': f'本周{len(items)}条去重记录，汇总其中{len(ordered)}条；不代表领域全部进展。'}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    return target
