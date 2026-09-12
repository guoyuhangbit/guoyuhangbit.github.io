#!/usr/bin/env python3
"""Check generated pages, links and publication data before publishing."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import re
import build

class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.ids, self.links, self.h1s = [], [], 0
        self.feed(path.read_text())
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs: self.ids.append(attrs['id'])
        if tag == 'h1': self.h1s += 1
        for key in ('href','src'):
            if attrs.get(key): self.links.append(attrs[key])

def main():
    root = build.OUT
    pages = {p.resolve():Page(p) for p in root.rglob('*.html')}
    for path,page in pages.items():
        assert page.h1s == 1, f'Expected one h1: {path}'
        assert len(page.ids) == len(set(page.ids)), f'Duplicate IDs: {path}'
        for value in page.links:
            url = urlsplit(value)
            if url.scheme or url.netloc: continue
            target = (root / unquote(url.path).lstrip('/')) if url.path.startswith('/') else (path.parent / unquote(url.path)) if url.path else path
            if target.is_dir(): target /= 'index.html'
            assert target.is_file(), f'Broken link: {path.name} -> {value}'
            if url.fragment:
                assert unquote(url.fragment) in pages[target.resolve()].ids, f'Missing anchor: {value}'
        raw = path.read_text()
        assert not re.search(r'/(Users|home)/|Zotero/storage|讲师|副教授|教授|guoyuhang@', raw), f'Private or excluded content in {path}'
    records = build.parse_bib((root/'publications.bib').read_text())
    originals = build.parse_bib((build.CONTENT/'publications.bib').read_text())
    assert {r['id'] for r in records} == {r['id'] for r in originals}, 'Bibliography entries lost'
    for record in records:
        assert record.get('author') and (record.get('year') or record.get('date')), record['id']
        assert 'file' not in record and 'abstract' not in record, record['id']
        names = record['author'].split(' and ')
        assert len(names) == len(set(names)), f'Duplicate authors in {record["id"]}'
    text = (root/'publications.bib').read_text()
    assert '/Users/' not in text and 'Zotero/' not in text
    for key,role in build.AUTHORSHIP.items():
        record = next(r for r in records if r['id'] == key)
        names = [build.plain(n) for n in record['author'].split(' and ')]
        if role.get('equivalent_first'):
            assert names[1] in ('Guo, Yuhang','郭宇航') and role.get('equivalent_first_basis'), key
        if role.get('corresponding'):
            assert role.get('evidence') and role['corresponding_status'] == 'confirmed', key
    public_roles = (build.CONTENT/'authorship.json').read_text()
    assert '/Users/' not in public_roles and 'guoyuhang@' not in public_roles
    print(f'Passed: {len(pages)} pages, local links/anchors, {len(records)} bibliography entries, author/year completeness and public-data checks.')

if __name__ == '__main__': main()
