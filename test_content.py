"""Exercise content edits through the same build used by online publishing."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ContentEditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('build.py', 'check.py'):
            shutil.copy2(ROOT / name, self.root / name)
        for name in ('assets', 'content'):
            shutil.copytree(ROOT / name, self.root / name)

    def edit(self, name, change):
        path = self.root / 'content' / name
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False))

    def build(self, succeeds=True):
        result = subprocess.run([sys.executable, 'build.py'], cwd=self.root,
                                capture_output=True, text=True)
        if not succeeds:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        checked = subprocess.run([sys.executable, 'check.py'], cwd=self.root,
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def read(self, name):
        return (self.root / 'dist' / name).read_text()

    def test_clear_optional_sections_and_escape_user_text(self):
        def change(page):
            page['home']['intro'] = '<img src=x onerror=alert(1)> & 研究'
            for key in ('research', 'students', 'collaboration'):
                page[key] = None
            page['publications'] = {'intro': None, 'note': ''}
        self.edit('page.json', change)
        self.edit('site.json', lambda site: site.update(affiliation_en=None))
        self.build()
        home = self.read('index.html')
        self.assertIn('&lt;img src=x onerror=alert(1)&gt; &amp; 研究', home)
        self.assertNotIn('<img src=x', home)
        self.assertNotIn('href="index.html#research"', home)
        self.assertNotIn('href="index.html#students"', home)
        self.assertNotIn('class="course-banner"', home)
        self.assertNotIn('作者身份标签均指', self.read('publications/index.html'))

    def test_course_link_and_text_are_editable(self):
        self.edit('site.json', lambda site: site.update(course_url='https://example.org/course?a=1&b=2'))
        self.edit('page.json', lambda page: page['course'].update(title='数据结构与算法', open_label='开始学习'))
        self.build()
        course = self.read('teaching/data-structures/index.html')
        self.assertIn('https://example.org/course?a=1&amp;b=2', course)
        self.assertIn('开始学习', course)
        self.assertIn('数据结构与算法', course)
        self.assertNotIn('课件正在准备中', course)

    def test_reorder_and_remove_featured_papers(self):
        self.edit('page.json', lambda page: page.update(featured=list(reversed(page['featured'][:2]))))
        self.build()
        home = self.read('index.html')
        self.assertLess(home.index('id="tian_beyond_2026"'), home.index('id="lan_peap_2026"'))
        self.assertNotIn('id="li2025"', home)
        self.assertIn('id="li2025"', self.read('publications/index.html'))

    def test_invalid_reference_or_link_blocks_publication(self):
        self.edit('page.json', lambda page: page['featured'][0].update(id='unknown-paper'))
        self.assertIn('Unknown featured paper IDs', self.build(succeeds=False))
        self.edit('page.json', lambda page: page['featured'][0].update(id='lan_peap_2026'))
        self.edit('site.json', lambda site: site.update(course_url='javascript:alert(1)'))
        self.assertIn('Invalid public URL', self.build(succeeds=False))

    def test_analytics_can_be_enabled_for_all_pages_and_disabled(self):
        self.edit('analytics.json', lambda config: config.update(enabled=False, website_id=''))
        self.build()
        self.assertNotIn('cloud.umami.is', self.read('index.html'))
        website_id = '00000000-0000-4000-8000-000000000001'
        self.edit('analytics.json', lambda config: config.update(enabled=True, website_id=website_id))
        self.build()
        for path in (self.root / 'dist').rglob('*.html'):
            page = path.read_text()
            self.assertEqual(page.count('src="https://cloud.umami.is/script.js"'), 1)
            self.assertIn(f'data-website-id="{website_id}"', page)
            self.assertIn('data-domains="guoyuhangbit.github.io"', page)
            self.assertIn('data-exclude-search="true"', page)
            self.assertIn('data-exclude-hash="true"', page)
            self.assertIn('data-do-not-track="true"', page)
            self.assertNotIn('查看统计与首次设置', page)
        self.assertFalse((self.root / 'dist' / 'content' / 'analytics.json').exists())
        self.edit('analytics.json', lambda config: config.update(enabled=False))
        self.build()
        for path in (self.root / 'dist').rglob('*.html'):
            self.assertNotIn('cloud.umami.is', path.read_text())

    def test_incomplete_or_invalid_analytics_blocks_publication(self):
        self.edit('analytics.json', lambda config: config.update(enabled=True, website_id=''))
        self.assertIn('requires an Umami website ID', self.build(succeeds=False))
        self.edit('analytics.json', lambda config: config.update(website_id='\"><script>alert(1)</script>'))
        self.assertIn('Invalid Umami website ID', self.build(succeeds=False))
        self.edit('analytics.json', lambda config: config.update(website_id='', enabled='false'))
        self.assertIn('must be a boolean', self.build(succeeds=False))


if __name__ == '__main__':
    unittest.main()
