from __future__ import annotations

import argparse
import json
import re
import sqlite3
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

parser = argparse.ArgumentParser(description='화학물질정보처리시스템 엑셀을 findol 검색 DB로 변환합니다.')
parser.add_argument('xlsx', type=Path, help='다운로드한 .xlsx 파일')
parser.add_argument('--out-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'backend' / 'app' / 'data')
parser.add_argument('--data-date', default=None, help='YYYY-MM-DD, 생략 시 파일명 숫자에서 추출')
args = parser.parse_args()
XLSX = args.xlsx.resolve()
OUT_DIR = args.out_dir.resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = OUT_DIR / 'substances.sqlite3'
META_PATH = OUT_DIR / 'substance_dataset_meta.json'

NS = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
CELL_RE = re.compile(r'([A-Z]+)(\d+)')


def col_to_index(ref: str) -> int:
    m = CELL_RE.match(ref)
    letters = m.group(1) if m else ref
    idx = 0
    for ch in letters:
        idx = idx * 26 + ord(ch) - 64
    return idx - 1


def normalize(value: str | None) -> str:
    value = (value or '').strip().lower()
    value = re.sub(r'[\s\-_/·ㆍ,().]+', '', value)
    return value


def read_shared_strings(z: zipfile.ZipFile) -> list[str]:
    values: list[str] = []
    with z.open('xl/sharedStrings.xml') as fh:
        for event, elem in ET.iterparse(fh, events=('end',)):
            if elem.tag.endswith('}si'):
                parts = [node.text or '' for node in elem.iter() if node.tag.endswith('}t')]
                values.append(''.join(parts))
                elem.clear()
    return values


def iter_rows():
    with zipfile.ZipFile(XLSX) as z:
        shared = read_shared_strings(z)
        with z.open('xl/worksheets/sheet1.xml') as fh:
            for event, elem in ET.iterparse(fh, events=('end',)):
                if not elem.tag.endswith('}row'):
                    continue
                row: dict[int, str] = {}
                for c in elem:
                    if not c.tag.endswith('}c'):
                        continue
                    ref = c.attrib.get('r', '')
                    idx = col_to_index(ref)
                    cell_type = c.attrib.get('t')
                    value = ''
                    if cell_type == 'inlineStr':
                        parts = [node.text or '' for node in c.iter() if node.tag.endswith('}t')]
                        value = ''.join(parts)
                    else:
                        v = next((node for node in c if node.tag.endswith('}v')), None)
                        if v is not None and v.text is not None:
                            if cell_type == 's':
                                try:
                                    value = shared[int(v.text)]
                                except (ValueError, IndexError):
                                    value = v.text
                            else:
                                value = v.text
                    row[idx] = value.strip()
                yield row
                elem.clear()


headers = []
records = []
for n, row in enumerate(iter_rows()):
    if n == 0:
        max_col = max(row) if row else -1
        headers = [row.get(i, '') for i in range(max_col + 1)]
        continue
    if not row:
        continue
    vals = [row.get(i, '') for i in range(13)]
    if not any(vals[1:4]):
        continue
    records.append(vals)

if DB_PATH.exists():
    DB_PATH.unlink()
conn = sqlite3.connect(DB_PATH)
conn.executescript('''
PRAGMA journal_mode=OFF;
PRAGMA synchronous=OFF;
CREATE TABLE substances (
  id INTEGER PRIMARY KEY,
  source_no TEXT,
  cas_no TEXT,
  name_en TEXT,
  name_ko TEXT,
  existing_no TEXT,
  hazard_designation TEXT,
  accident_preparedness TEXT,
  restricted_prohibited_authorized TEXT,
  priority_substance TEXT,
  persistent_pollutant TEXT,
  criteria_text TEXT,
  registered_existing TEXT,
  is_existing TEXT,
  normalized_cas TEXT,
  normalized_en TEXT,
  normalized_ko TEXT
);
CREATE TABLE aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  substance_id INTEGER NOT NULL,
  alias_text TEXT NOT NULL,
  alias_norm TEXT NOT NULL,
  alias_type TEXT NOT NULL DEFAULT 'manual',
  UNIQUE(substance_id, alias_norm),
  FOREIGN KEY(substance_id) REFERENCES substances(id)
);
CREATE INDEX idx_substances_cas ON substances(normalized_cas);
CREATE INDEX idx_substances_ko ON substances(normalized_ko);
CREATE INDEX idx_substances_en ON substances(normalized_en);
CREATE INDEX idx_alias_norm ON aliases(alias_norm);
''')

insert = '''INSERT INTO substances (
source_no,cas_no,name_en,name_ko,existing_no,hazard_designation,accident_preparedness,
restricted_prohibited_authorized,priority_substance,persistent_pollutant,criteria_text,
registered_existing,is_existing,normalized_cas,normalized_en,normalized_ko
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''

for vals in records:
    no, cas, en, ko, existing, hazard, accident, restricted, priority, persistent, criteria, registered, is_existing = vals
    conn.execute(insert, (
        no, cas, en, ko, existing, hazard, accident, restricted, priority, persistent,
        criteria, registered, is_existing, normalize(cas), normalize(en), normalize(ko)
    ))
conn.commit()

# Add aliases by exact CAS. User-friendly aliases are deliberately small and transparent.
alias_map = {
    '7664-38-2': [
        ('인산', 'common_ko'), ('오르토인산', 'common_ko'), ('정인산', 'common_ko'),
        ('phosphoric acid', 'common_en'), ('orthophosphoric acid', 'official_en'), ('H3PO4', 'formula'),
    ],
    '7681-52-9': [
        ('차아염소산나트륨', 'normalized_ko'), ('차아염소산 나트륨', 'official_ko'),
        ('차아염소산소다', 'common_ko'), ('차염', 'abbreviation'), ('sodium hypochlorite', 'official_en'),
        ('NaOCl', 'formula'), ('차야염소산나트륨', 'common_typo'),
    ],
    '68-12-2': [('DMF', 'abbreviation'), ('디메틸포름아미드', 'common_ko'), ('디메틸포름아마이드', 'common_ko')],
    '78-93-3': [('MEK', 'abbreviation'), ('메틸에틸케톤', 'common_ko'), ('2-부타논', 'common_ko')],
    '7664-39-3': [('불산', 'common_ko'), ('플루오르화수소', 'common_ko'), ('hydrofluoric acid', 'common_en')],
}
for cas, aliases in alias_map.items():
    ids = [r[0] for r in conn.execute('SELECT id FROM substances WHERE normalized_cas=?', (normalize(cas),))]
    for substance_id in ids:
        for text, kind in aliases:
            conn.execute('INSERT OR IGNORE INTO aliases(substance_id, alias_text, alias_norm, alias_type) VALUES (?,?,?,?)',
                         (substance_id, text, normalize(text), kind))
conn.commit()

counts = {
    'row_count': conn.execute('SELECT COUNT(*) FROM substances').fetchone()[0],
    'cas_count': conn.execute("SELECT COUNT(*) FROM substances WHERE TRIM(cas_no) <> ''").fetchone()[0],
    'name_en_count': conn.execute("SELECT COUNT(*) FROM substances WHERE TRIM(name_en) <> ''").fetchone()[0],
    'name_ko_count': conn.execute("SELECT COUNT(*) FROM substances WHERE TRIM(name_ko) <> ''").fetchone()[0],
    'alias_count': conn.execute('SELECT COUNT(*) FROM aliases').fetchone()[0],
}
meta = {
    'dataset_name': '화학물질정보처리시스템 다운로드 자료',
    'source_file': XLSX.name,
    'data_date': args.data_date or (lambda m: f'{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}' if m else '확인 필요')(re.search(r'(20\d{6})', XLSX.stem)),
    'generated_on': __import__('datetime').date.today().isoformat(),
    'headers': headers,
    **counts,
    'notice': '검색 결과 없음은 비규제 물질을 의미하지 않습니다. 최신 고시·행정예고와 원문을 함께 확인해야 합니다.',
}
META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
conn.close()
print(json.dumps(meta, ensure_ascii=False, indent=2))
print('DB bytes', DB_PATH.stat().st_size)
