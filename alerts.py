"""One recoverable GitHub issue for repeated source failures/empty results."""
import json
import os
from pathlib import Path
import re
import urllib.request

TITLE = 'Daily HOT source health'


def source_alerts(status):
    latest = status.get('runs', [{}])[0].get('sources', {}) if status.get('runs') else {}
    return [(name, count, latest.get(name, {}).get('error')) for name, count in status.get('streak', {}).items() if count >= 3]


def main():
    token, repo = os.getenv('GITHUB_TOKEN'), os.getenv('GITHUB_REPOSITORY')
    if not token or not repo or not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        print('Issue sync skipped: requires workflow token and repository.'); return
    path = Path('data/status.json')
    if not path.exists():
        return
    alerts = source_alerts(json.loads(path.read_text(encoding='utf-8')))
    def api(method, suffix, data=None):
        req = urllib.request.Request('https://api.github.com/repos/' + repo + suffix,
            data=json.dumps(data).encode() if data is not None else None, method=method,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'User-Agent': 'Lv-Daily-HOT', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    existing = next((p for p in api('GET', '/issues?state=open&per_page=100') if p.get('title') == TITLE and 'pull_request' not in p), None)
    if alerts:
        body = 'Sources with zero candidates for at least 3 runs (not necessarily broken):\n\n' + '\n'.join(
            f'- {name}: {count} runs; latest error: {error or "none; possibly no matching items"}' for name, count, error in alerts)
        if existing:
            api('PATCH', '/issues/' + str(existing['number']), {'body': body})
        else:
            api('POST', '/issues', {'title': TITLE, 'body': body})
    elif existing:
        api('PATCH', '/issues/' + str(existing['number']), {'state': 'closed'})


if __name__ == '__main__':
    main()
