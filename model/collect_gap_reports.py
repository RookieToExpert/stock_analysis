"""Download the dated issuer reports for a PIT gap CSV from CNINFO's public archive."""
import argparse
import csv
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from zoneinfo import ZoneInfo

import requests


DIRECTORY = 'https://www.cninfo.com.cn/new/data/szse_stock.json'
INDEX = 'https://www.cninfo.com.cn/new/hisAnnouncement/query'
ARCHIVE = 'https://static.cninfo.com.cn/'
local = threading.local()


def session():
    if not hasattr(local, 'http'):
        local.http = requests.Session()
        local.http.trust_env = False
        local.http.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'})
    return local.http


def save(path, content):
    pending = path.with_name(f'{path.name}.partial.{os.getpid()}.{threading.get_ident()}')
    pending.write_bytes(content)
    os.replace(pending, path)


def save_json(path, value):
    save(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def load(path):
    return json.loads(path.read_bytes())


class Pacing:
    def __init__(self, seconds):
        self.seconds = seconds
        self.lock = threading.Lock()
        self.next = 0

    def wait(self):
        with self.lock:
            delay = self.next - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.next = time.monotonic() + self.seconds

    def defer(self, seconds):
        with self.lock:
            self.next = max(self.next, time.monotonic() + seconds)


def request(method, url, pace, **kwargs):
    for attempt in range(3):
        pace.wait()
        try:
            response = session().request(method, url, timeout=(12, 35), **kwargs)
            if response.status_code == 429:
                delay = response.headers.get('Retry-After', '')
                pace.defer(max(30, int(delay) if delay.isdigit() else 0))
            response.raise_for_status()
            return response
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as error:
            status = error.response.status_code if error.response is not None else None
            if attempt == 2 or (status is not None and status < 500 and status != 429):
                raise
            time.sleep(2 ** attempt)


def get_directory(base, pace):
    path = base/'cninfo-directory.json'
    if not path.exists():
        value = request('GET', DIRECTORY, pace).json()['stockList']
        if not value:
            raise ValueError('empty securities directory')
        save_json(path, value)
    return {row['code']: row['orgId'] for row in load(path)}


def disclosures(code, org, years, cutoff, base, pace):
    start = f'{min(years) + 1}-01-01'
    path = base/'index'/f'{code}-{start}-{cutoff}.json'
    if path.exists():
        return load(path)
    notices = {}
    # The public interface caps responses at 30 rows and can repeat the first page
    # even when pageNum advances. Split the date window until each response is complete.
    windows = [(date.fromisoformat(start), date.fromisoformat(cutoff))]
    while windows:
        first, last = windows.pop()
        query = {'pageNum': 1, 'pageSize': 30, 'tabName': 'fulltext',
                 'column': 'sse' if code.startswith('sh.') else 'szse',
                 'stock': code[3:] + ',' + org, 'category': 'category_ndbg_szsh',
                 'seDate': f'{first}~{last}', 'isHLtitle': 'false'}
        data = request('POST', INDEX, pace, data=query).json()
        rows, total = data.get('announcements'), data.get('totalAnnouncement')
        if not isinstance(total, int) or (rows is None and total):
            raise ValueError('malformed annual disclosure index')
        rows = rows or []
        if total > len(rows) or data.get('hasMore'):
            if first == last:
                raise ValueError(f'incomplete issuer index for {first}')
            midpoint = first + (last - first) // 2
            windows.extend([(midpoint + timedelta(days=1), last), (first, midpoint)])
            continue
        for row in rows:
            if row['secCode'] != code[3:] or str(row['orgId']) != org:
                continue
            stamp = datetime.fromtimestamp(row['announcementTime'] / 1000, ZoneInfo('Asia/Shanghai')).date().isoformat()
            if not first.isoformat() <= stamp <= last.isoformat():
                raise ValueError(f'issuer index returned {stamp} outside {first}~{last}')
            link = row.get('adjunctUrl') or ''
            if not link.startswith('finalpage/') or not link.lower().endswith('.pdf'):
                continue
            title = re.sub(r'<[^>]*>|\s+', '', row['announcementTitle'])
            identifier = str(row['announcementId'])
            notices[identifier] = {'id': identifier, 'code': code, 'org_id': org, 'date': stamp,
                                   'title': title, 'source': ARCHIVE + link}
    if not notices:
        raise ValueError('no matched issuer disclosures')
    result = sorted(notices.values(), key=lambda n: (n['date'], n['id']))
    save_json(path, result)
    return result


def report_kind(title, year, publication=None):
    title = title.replace('_', '').replace('年度年度报告', '年度报告').replace('年年年度报告', '年年度报告')
    if re.search('英文|外文|英语|English|H股|境外监管|独立董事|审议|提示性公告|内部控制|工作报告|已取消|书面确认意见', title, re.I):
        return None
    yearless = publication and int(publication[:4]) == year + 1 and re.fullmatch(r'(?:年度报告|年报全文)(?:合并报告)?(?:摘要)?', title)
    if not yearless and not re.search(str(year) + r'年?(?:年度报告|年报)', title):
        return None
    if '摘要' in title:
        return 'summary'
    if '关于' in title and '公告' in title:
        return 'notice'
    return 'full'


def collect_pdf(notice, base, pace):
    name = notice['id']
    pdf = base/'pdf'/(name + '.pdf')
    txt = base/'text'/(name + '.txt.gz')
    meta = base/'text'/(name + '.json')
    if meta.exists() and txt.exists() and pdf.exists():
        if notice.get('pdf_sha256') and load(meta)['pdf_sha256'] != notice['pdf_sha256']:
            raise ValueError('cached PDF differs from the pinned filing')
        return 'cached'
    if not pdf.exists():
        response = request('GET', notice['source'], pace)
        if not response.content.startswith(b'%PDF'):
            raise ValueError('issuer archive did not return a PDF')
        save(pdf, response.content)
    body = pdf.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if notice.get('pdf_sha256') and digest != notice['pdf_sha256']:
        raise ValueError('downloaded PDF differs from the pinned filing')
    proc = subprocess.run(['pdftotext', '-layout', str(pdf), '-'], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True, timeout=100)
    if len(proc.stdout.strip()) < 300:
        raise ValueError('PDF requires OCR')
    save(txt, gzip.compress(proc.stdout, compresslevel=4, mtime=0))
    save_json(meta, {**notice, 'pdf_sha256': digest,
                     'text_sha256': hashlib.sha256(proc.stdout).hexdigest()})
    return 'downloaded'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gaps_csv', type=Path)
    parser.add_argument('cache', type=Path)
    parser.add_argument('--kind', choices=('full', 'summary'), default='full')
    parser.add_argument('--index-workers', type=int, default=4)
    parser.add_argument('--pdf-workers', type=int, default=5)
    parser.add_argument('--inventory', type=Path, help='use the exact archived filing list and pinned PDF hashes')
    args = parser.parse_args()
    base = args.cache
    for subdir in ('index', 'pdf', 'text'):
        (base/subdir).mkdir(parents=True, exist_ok=True)
    if args.inventory:
        with gzip.open(args.inventory, 'rt', encoding='utf-8') as source:
            inventory = json.load(source)
        docs = {doc['id']: doc for years in inventory.values() for period in years.values()
                for doc in period if doc.get('pdf_sha256')}
        pace = Pacing(.22)
        with ThreadPoolExecutor(max_workers=args.pdf_workers) as pool:
            jobs = [pool.submit(collect_pdf, doc, base, pace) for doc in docs.values()]
            for job in as_completed(jobs):
                job.result()
        print('Pinned filings', len(docs))
        return
    requests_by_code = defaultdict(set)
    evaluation_days = set()
    with args.gaps_csv.open(encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            if row['待核事项'] == '财报':
                requests_by_code[row['证券代码']].add(int(row['报告期或标志变化日'][:4]))
                evaluation_days.add(row['评价日'])
    cutoff = max(evaluation_days)
    index_pace, pdf_pace = Pacing(.32), Pacing(.22)
    orgs = get_directory(base, index_pace)
    errors, seen = [], set()
    completed = 0
    with ThreadPoolExecutor(max_workers=args.index_workers) as indexes, ThreadPoolExecutor(max_workers=args.pdf_workers) as pdfs:
        index_jobs = {indexes.submit(disclosures, code, orgs[code[3:]], years, cutoff, base, index_pace): code
                      for code, years in requests_by_code.items() if code[3:] in orgs}
        for code in requests_by_code:
            if code[3:] not in orgs:
                errors.append({'code': code, 'error': 'company absent from current directory'})
        jobs = {}
        for count, job in enumerate(as_completed(index_jobs), 1):
            code = index_jobs[job]
            try:
                notices = job.result()
                for year in sorted(requests_by_code[code]):
                    docs = [n for n in notices if n['date'] < cutoff and report_kind(n['title'], year, n['date']) == args.kind]
                    if not docs:
                        errors.append({'code': code, 'year': year, 'error': 'no matched ' + args.kind})
                    for doc in docs:
                        if doc['id'] not in seen:
                            seen.add(doc['id'])
                            jobs[pdfs.submit(collect_pdf, doc, base, pdf_pace)] = doc
            except Exception as exc:
                errors.append({'code': code, 'error': str(exc)})
            if count % 50 == 0:
                print('indexed', count, '/', len(index_jobs), 'queued documents', len(jobs),
                      'finished requests', sum(job.done() for job in jobs), flush=True)
        for job in as_completed(jobs):
            doc = jobs[job]
            try:
                job.result()
                completed += 1
            except Exception as exc:
                errors.append({**doc, 'error': str(exc)})
            if (completed + len(errors)) % 100 == 0:
                print('documents complete', completed, '/', len(jobs), 'issues', len(errors), flush=True)
    input_digest = hashlib.sha256(args.gaps_csv.read_bytes()).hexdigest()[:16]
    save_json(base/f'{args.kind}-{input_digest}-collection.json', {'companies': len(requests_by_code), 'documents': len(seen),
                                                       'completed': completed, 'errors': errors})
    print('done', len(requests_by_code), 'companies', completed, '/', len(seen), 'documents, issues', len(errors), flush=True)


if __name__ == '__main__':
    main()
