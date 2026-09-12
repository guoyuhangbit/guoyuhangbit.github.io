#!/usr/bin/env python3
"""Build a dependency-free static academic site from public bibliography fields."""
import argparse
import html
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'dist'
CONTENT = ROOT / 'content'
KEEP = {'title', 'author', 'date', 'year', 'booktitle', 'journal', 'journaltitle', 'volume', 'number', 'pages', 'publisher', 'doi', 'url', 'note'}

def parse_bib(text):
    records = []
    for match in re.finditer(r'@(\w+)\s*\{\s*([^,\s]+)\s*,', text):
        i = match.end()
        fields = {}
        while i < len(text):
            while i < len(text) and text[i] in ' \t\r\n,': i += 1
            if i >= len(text) or text[i] == '}': break
            field = re.match(r'([\w-]+)\s*=\s*', text[i:])
            if not field: raise ValueError(f'Invalid field in {match[2]} near {text[i:i+35]!r}')
            name = field[1].lower()
            i += field.end()
            if text[i] == '{':
                i += 1
                start, depth = i, 1
                while i < len(text) and depth:
                    if text[i] == '\\': i += 2; continue
                    if text[i] == '{': depth += 1
                    elif text[i] == '}': depth -= 1
                    i += 1
                if depth: raise ValueError(f'Unbalanced braces in {match[2]}')
                value = text[start:i-1]
            elif text[i] == '"':
                i += 1
                start = i
                while i < len(text) and text[i] != '"':
                    i += 2 if text[i] == '\\' else 1
                value = text[start:i]
                i += 1
            else:
                start = i
                while i < len(text) and text[i] not in ',}\n': i += 1
                value = text[start:i].strip()
            fields[name] = value
        records.append({'id': match[2], 'type': match[1].lower(), **fields})
    return records

def plain(value):
    value = value.replace(r'\textasciicircum', '^').replace(r'\&', '&').replace(r'\%', '%')
    return re.sub(r'\s+', ' ', value.replace('{', '').replace('}', '')).strip()

def esc(value): return html.escape(str(value), quote=True)

def text_element(tag, value, attrs=''):
    return f'<{tag}{attrs}>{esc(value)}</{tag}>' if value else ''

def has_text(value):
    if isinstance(value, dict): return any(has_text(item) for item in value.values())
    if isinstance(value, list): return any(has_text(item) for item in value)
    return bool(value and str(value).strip())

def safe_url(value):
    if value and not re.match(r'^https?://[^\s]+$', value): raise ValueError(f'Invalid public URL: {value}')
    return esc(value)

def bib_record(record):
    kind = record['type']
    if kind == 'online': kind = 'misc'
    fields = []
    for key, value in record.items():
        if key not in KEEP: continue
        output_key = 'journal' if key == 'journaltitle' else key
        fields.append(f'  {output_key} = {{{value}}}')
    if not record.get('year') and record.get('date'): fields.append(f'  year = {{{record["date"][:4]}}}')
    return '@' + kind + '{' + record['id'] + ',\n' + ',\n'.join(fields) + '\n}'

def authors_html(record):
    names = []
    for author in re.split(r'\s+and\s+', record.get('author', '')):
        name = plain(author)
        if ',' in name:
            last, first = name.split(',', 1)
            name = f'{first.strip()} {last.strip()}'
        names.append('<strong>' + esc(name) + '</strong>' if name in (SITE['name_en'], SITE['name']) else esc(name))
    return ', '.join(names) if record.get('author') else '作者信息待补充'

def authorship_html(record):
    status = AUTHORSHIP.get(record['id'], {})
    labels = []
    if status.get('first_author'): labels.append(('第一作者', '按论文署名顺序'))
    if status.get('student_first_supervisor_second'): labels.append(('学生一作，导师二作', '学生第一作者、导师第二作者'))
    if status.get('corresponding'): labels.append(('通讯作者', '依据论文作者标记及通讯说明'))
    if not labels: return ''
    return f'<div class="role-tags" aria-label="{esc(SITE["name"])}的作者身份">' + ''.join(f'<span class="role-tag" title="{esc(note)}">{label}</span>' for label,note in labels) + '</div>'

def classification_html(record):
    status = CLASSIFICATIONS.get(record['id'], {})
    labels = []
    checked = CLASSIFICATION_DATA.get('checked_on')
    checked_note = f'；核对于 {checked}' if checked else ''
    rank = status.get('ccf_rank')
    if rank:
        domestic = rank.startswith('T')
        catalog = CLASSIFICATION_DATA.get('domestic_catalog' if domestic else 'ccf_catalog')
        note = 'CCF 高质量科技期刊分级目录' if domestic else 'CCF 推荐国际学术会议和期刊目录'
        if catalog: note += f' {catalog}'
        labels.append((f'CCF {rank}', note + checked_note, status.get('ccf_source')))
    indexing = status.get('indexing')
    if indexing:
        note = f'期刊收录类别：{indexing}；期刊层面，不表示单篇论文已检索' + checked_note
        labels.append((f'{indexing} 期刊', note, status.get('indexing_source')))
    if not labels: return ''
    tags = []
    for label, note, source in labels:
        attrs = f'class="classification-tag" title="{esc(note)}"'
        if source:
            tags.append(f'<a {attrs} href="{safe_url(source)}" target="_blank" rel="noopener noreferrer">{esc(label)} <span aria-hidden="true">↗</span></a>')
        else:
            tags.append(f'<span {attrs}>{esc(label)}</span>')
    return '<div class="classification-tags" aria-label="CCF 分级与期刊收录类别">' + ''.join(tags) + '</div>'

def venue(record):
    url = record.get('url', '')
    year = record.get('date', record.get('year', ''))[:4]
    if '.findings-' in url:
        conf = re.search(r'\.findings-([a-z]+)', url)[1].upper()
        return f'{esc(conf)} {esc(year)}<br>Findings'
    for fragment, label in [('acl-long','ACL'), ('emnlp-main','EMNLP'), ('D13-', 'EMNLP'), ('lrec-main', 'LREC–COLING'), ('iwslt-', 'IWSLT'), ('autosimtrans-', 'AutoSimTrans'), ('ccl-', 'CCL')]:
        if fragment in url: return f'{label} {esc(year)}'
    full = plain(record.get('journaltitle', record.get('journal', record.get('booktitle', ''))))
    if re.search(r'\bEMNLP\b|Empirical Methods in Natural Language Processing', full, re.I):
        track = '<br>Findings' if re.search(r'\bFindings\b', full, re.I) else ('<br>主会' if plain(record.get('note', '')) == 'Accepted, to appear' else '')
        return f'EMNLP {esc(year)}{track}'
    for marker,label in [('AAAI','AAAI'), ('Neurocomputing','Neurocomputing'), ('Frontiers of Computer Science','FCS'), ('Data Intelligence','Data Intelligence'), ('ICASSP','ICASSP'), ('ICNLP','ICNLP')]:
        if marker in full: return f'{label} {esc(year)}'
    for marker, label in [('Pacific Asia Conference', 'PACLIC'), ('Semantic Evaluation', 'SemEval'), ('International Joint Conference on Natural Language Processing', 'IJCNLP'), ('Conference on Computational Natural Language Learning', 'CoNLL')]:
        if marker in full: return f'{label} {esc(year)}'
    return esc(year or '条目信息待补充')

def paper(record, featured=False):
    url = record.get('url') or ('https://doi.org/' + record['doi'] if record.get('doi') else '')
    title = esc(plain(record.get('title', '')))
    title_html = f'<a href="{safe_url(url)}" target="_blank" rel="noopener noreferrer">{title}</a>' if url else title
    links = f'<a href="{safe_url(url)}" target="_blank" rel="noopener noreferrer">论文 <span aria-hidden="true">↗</span></a>' if url else ''
    extra = FEATURED.get(record['id'])
    highlights = HIGHLIGHTS.get(record['id'], [])
    highlight_html = '<div class="paper-highlights">' + ''.join(f'<span class="paper-highlight"><span aria-hidden="true">★</span> {esc(label)}</span>' for label in highlights) + '</div>' if highlights else ''
    if extra and extra.get('url'): links += f'<a href="{safe_url(extra["url"])}" target="_blank" rel="noopener noreferrer">代码与数据 <span aria-hidden="true">↗</span></a>'
    summary = text_element('p', extra.get('summary'), ' class="pub-summary"') if featured and extra else ''
    full = plain(record.get('journaltitle', record.get('journal', record.get('booktitle', ''))))
    full_html = f'<p class="paper-venue-full">{esc(full)}</p>' if not featured and full else ''
    status_html = '<p class="publication-status">已录用 · 待正式出版</p>' if plain(record.get('note', '')) == 'Accepted, to appear' else ''
    citation = '' if featured else f'<details class="citation"><summary>BibTeX 引用</summary><pre>{esc(bib_record(record))}</pre></details>'
    return f'<article class="publication" id="{esc(record["id"])}"><div class="venue">{venue(record)}</div><div class="pub-body">{highlight_html}<h3>{title_html}</h3>{classification_html(record)}<p class="authors">{authors_html(record)}</p>{authorship_html(record)}{full_html}{status_html}{summary}<div class="pub-links">{links}</div>{citation}</div></article>'

def frame(body, title, depth='', current='home', page_path=''):
    nav = [('research', '研究方向', depth+'index.html#research'), ('publications', '学术成果', depth+'publications/'), ('students', '学生与合作', depth+'index.html#students'), ('teaching', '教学', depth+'teaching/data-structures/'), ('contact', '联系', depth+'index.html#contact')]
    hidden = set()
    if not PAGE.get('research'): hidden.add('research')
    if not has_text(PAGE.get('students')) and not has_text(PAGE.get('collaboration')): hidden.add('students')
    nav_html = ''.join(f'<a href="{esc(url)}"' + (' aria-current="page"' if key==current else '') + f'>{name}</a>' for key,name,url in nav if key not in hidden)
    canonical = f'<link rel="canonical" href="{safe_url(SITE["site_url"].rstrip("/")+"/"+page_path)}">' if SITE.get('site_url') else ''
    name = esc(SITE['name'])
    name_en = esc(SITE['name_en'])
    full_title = esc(f'{title} · {SITE["name"]} {SITE["name_en"]}')
    description = esc('。'.join(value for value in [SITE['name'], SITE.get('affiliation', ''), (PAGE.get('home') or {}).get('intro', '')] if value))
    initial = esc(SITE['name_en'].split()[-1][:1].upper()) if SITE['name_en'].split() else 'G'
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{full_title}</title><meta name="description" content="{description}"><meta property="og:title" content="{full_title}"><meta property="og:type" content="website">{canonical}<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='4' fill='%23152e2a'/%3E%3Ctext x='20' y='28' text-anchor='middle' fill='white' font-family='Georgia' font-size='27'%3EG%3C/text%3E%3C/svg%3E"><link rel="stylesheet" href="{esc(depth)}assets/style.css"><script src="{esc(depth)}assets/site.js" defer></script></head>
<body><a class="skip" href="#main">跳至正文</a><header class="site-header"><div class="wrap header-inner"><a class="brand" href="{esc(depth)}index.html" aria-label="{name}，返回首页"><span class="monogram" aria-hidden="true">{initial}</span><span>{name} <small>{esc(SITE['name_en'].upper())}</small></span></a><button class="menu-button" aria-expanded="false" aria-controls="site-nav">菜单</button><nav class="nav" id="site-nav" aria-label="主导航">{nav_html}</nav></div></header>
<main id="main" class="wrap">{body}</main><footer class="footer"><div class="wrap footer-inner"><span>© {esc(SITE['updated'][:4])} {name} · {name_en}</span>{text_element('span', SITE.get('affiliation'))}<span>更新于 {esc(SITE['updated'])}</span></div></footer></body></html>'''

def contact():
    if SITE.get('email_encoded'):
        fallback = f'<noscript><a class="inline-link" href="{safe_url(SITE["faculty"])}">学院个人页面联系方式</a></noscript>' if SITE.get('faculty') else ''
        action = f'<button class="button" data-contact="{esc(SITE["email_encoded"])}" aria-controls="contact-email">显示联系邮箱 <span aria-hidden="true">↗</span></button><span id="contact-email" class="email-result" aria-live="polite"></span>{fallback}'
    elif SITE.get('faculty'):
        action = f'<a class="button" href="{safe_url(SITE["faculty"])}" target="_blank" rel="noopener noreferrer">学院个人页面 ↗</a>'
    else:
        action = ''
    subtitle = text_element('p', (PAGE.get('contact') or {}).get('subtitle'))
    return f'<section class="contact" id="contact"><div><h2>联系我</h2>{subtitle}</div><div class="contact-action">{action}</div></section>'

def home(records):
    by_id = {record['id']: record for record in records}
    selected = ''.join(paper(by_id[key], True) for key in FEATURED)
    selected_section = f'<section class="section" id="selected"><div class="section-heading"><h2>代表成果</h2><span class="label">SELECTED WORK</span><a class="more" href="publications/">完整论文列表 <span aria-hidden="true">↗</span></a></div>{selected}</section>' if selected else ''
    research_items, research_blocks = [], []
    for number, item in enumerate((PAGE.get('research') or []), 1):
        item_id = esc(item['id'])
        title = esc(item.get('title', ''))
        research_items.append(f'<a class="index-item" href="#{item_id}"><span>{number:02}</span><div><b>{title}</b>{text_element("small", item.get("title_en"))}</div></a>')
        label = f'{number:02}' + (' / ' + esc(item['label']) if item.get('label') else '')
        keywords = text_element('p', item.get('keywords'), ' class="keywords"')
        research_blocks.append(f'<article class="research-block" id="{item_id}"><span class="number">{label}</span>{text_element("h3", item.get("title"))}{text_element("p", item.get("text"))}{keywords}</article>')
    research_index = '<aside class="research-index" aria-label="研究领域"><p>RESEARCH FOCUS</p>' + ''.join(research_items) + '</aside>' if research_items else ''
    research_section = '<section class="section" id="research"><div class="section-heading"><h2>研究方向</h2><span class="label">RESEARCH</span></div><div class="research-grid">' + ''.join(research_blocks) + '</div></section>' if research_blocks else ''
    student = (PAGE.get('students') or {})
    collaboration = (PAGE.get('collaboration') or {})
    student_articles = []
    if has_text(student):
        topics = ''.join(text_element('li', topic) for topic in (student.get('topics') or []))
        topic_list = '<ul>' + topics + '</ul>' if topics else ''
        student_articles.append('<article>' + text_element('h3', student.get('title')) + text_element('p', student.get('text')) + topic_list + '</article>')
    if has_text(collaboration):
        student_articles.append('<article>' + text_element('h3', collaboration.get('title')) + text_element('p', collaboration.get('text')) + text_element('p', collaboration.get('invitation')) + '<a class="inline-link" href="#contact">联系交流</a> <span aria-hidden="true">↗</span></article>')
    students_section = '<section class="section" id="students"><div class="section-heading"><h2>学生与合作</h2><span class="label">STUDENTS & COLLABORATION</span></div><div class="student-grid">' + ''.join(student_articles) + '</div></section>' if student_articles else ''
    social_links = []
    for key, label in [('scholar', 'Google Scholar'), ('acl_anthology', 'ACL Anthology'), ('github', 'GitHub'), ('orcid', 'ORCID')]:
        if SITE.get(key): social_links.append(f'<a href="{safe_url(SITE[key])}" target="_blank" rel="noopener noreferrer">{label} <span class="external" aria-hidden="true">↗</span></a>')
    social = '<div class="social">' + ''.join(social_links) + '</div>' if social_links else ''
    institution = (SITE.get('affiliation_en') or '').split(',')[-1].strip().upper()
    hero = '<section class="hero"><div>' + text_element('p', institution, ' class="eyebrow"') + text_element('h1', SITE['name']) + text_element('p', SITE.get('name_en'), ' class="english-name" lang="en"') + text_element('p', SITE.get('affiliation'), ' class="affiliation"') + text_element('p', (PAGE.get('home') or {}).get('intro'), ' class="intro"') + social + '</div>' + research_index + '</section>'
    return frame(hero + research_section + selected_section + students_section + contact(), '个人学术主页')

def bibliography(records):
    groups = defaultdict(list)
    for record in records:
        groups[record.get('date', record.get('year', ''))[:4] or '其他'].append(record)
    years = sorted(groups, reverse=True)
    years_nav = ''.join(f'<a href="#year-{esc(year)}">{esc(year)} <small>({len(groups[year])})</small></a>' for year in years)
    sections = ''
    for year in years:
        ordered = sorted(groups[year], key=lambda r: (r.get('date', r.get('year','')), plain(r['title'])), reverse=True)
        sections += f'<section class="year-section" id="year-{esc(year)}"><h2>{esc(year)}</h2>' + ''.join(paper(r) for r in ordered) + '</section>'
    intro = text_element('p', (PAGE.get('publications') or {}).get('intro'))
    note = text_element('p', (PAGE.get('publications') or {}).get('note'), ' class="subtle-note"')
    profiles = ''.join(f'<a class="button" href="{safe_url(SITE[key])}" target="_blank" rel="noopener noreferrer">{label} ↗</a>' for key, label in [('scholar', 'Google Scholar'), ('acl_anthology', 'ACL Anthology')] if SITE.get(key))
    return frame(f'<div class="page-heading"><p class="eyebrow">PUBLICATIONS</p><h1>学术成果</h1>{intro}{note}<div class="page-actions"><a class="button" href="../publications.bib" download>下载全部 BibTeX</a>{profiles}</div></div><div class="bibliography-layout"><nav class="year-nav" aria-label="论文年份">{years_nav}</nav><div>{sections}</div></div>', '学术成果', '../', 'publications', 'publications/')

def teaching():
    course = (PAGE.get('course') or {})
    if SITE.get('course_url'):
        status = text_element('h2', course.get('open_title')) + text_element('p', course.get('open_text')) + f'<a class="button" href="{safe_url(SITE["course_url"])}" target="_blank" rel="noopener noreferrer">{esc(course.get("open_label") or "进入课程课件")} ↗</a>'
    else:
        status = text_element('h2', course.get('pending_title')) + text_element('p', course.get('pending_text')) + text_element('p', course.get('pending_hint'))
    details = ''.join('<dt>' + label + '</dt><dd>' + esc(course[key]) + '</dd>' for key,label in [('audience','授课对象'), ('year','教学年份'), ('format','课件形式')] if course.get(key))
    title = course.get('title') or '课程'
    year_label = 'TEACHING' + (' / ' + str(course['year']) if course.get('year') else '')
    subtitle = ' · '.join(value for value in [course.get('subtitle'), SITE.get('name'), SITE.get('affiliation')] if value)
    heading = '<div class="page-heading">' + text_element('p', year_label, ' class="eyebrow"') + text_element('h1', title) + text_element('p', course.get('title_en'), ' class="english-name" lang="en"') + text_element('p', subtitle) + '</div>'
    status += text_element('p', course.get('notice'), ' class="subtle-note"')
    return frame(f'<div class="course-page">{heading}<div class="course-layout"><section class="course-state">{status}</section><aside class="course-details"><h2>课程信息</h2><dl>{details}<dt>课程联系</dt><dd><a class="inline-link" href="../../index.html#contact">教师联系方式 ↗</a></dd></dl></aside></div><div class="page-actions"><a class="inline-link" href="../../index.html">← 返回学术主页</a></div></div>', title, '../../', 'teaching', 'teaching/data-structures/')

def build():
    parser = argparse.ArgumentParser()
    parser.add_argument('--import-bib', type=Path)
    args = parser.parse_args()
    if args.import_bib:
        raw = parse_bib(args.import_bib.read_text())
        clean = [{key:value for key,value in r.items() if key in KEEP or key in {'id','type'}} for r in raw]
        (CONTENT/'publications.bib').write_text('\n\n'.join(bib_record(r) for r in clean)+'\n')
    records = parse_bib((CONTENT/'publications.bib').read_text())
    corrections = json.loads((CONTENT/'corrections.json').read_text())
    for record in records:
        record.update({k:v for k,v in corrections.get(record['id'], {}).items() if k in KEEP or k == 'type'})
    if len({r['id'] for r in records}) != len(records): raise ValueError('Duplicate bibliography keys')
    missing = set(FEATURED) - {record['id'] for record in records}
    if missing: raise ValueError('Unknown featured paper IDs: ' + ', '.join(sorted(missing)))
    missing_highlights = set(HIGHLIGHTS) - {record['id'] for record in records}
    if missing_highlights: raise ValueError('Unknown highlighted paper IDs: ' + ', '.join(sorted(missing_highlights)))
    missing_classifications = set(CLASSIFICATIONS) - {record['id'] for record in records}
    if missing_classifications: raise ValueError('Unknown classified paper IDs: ' + ', '.join(sorted(missing_classifications)))
    OUT.mkdir(exist_ok=True)
    shutil.copytree(ROOT/'assets', OUT/'assets', dirs_exist_ok=True)
    (OUT/'index.html').write_text(home(records))
    (OUT/'publications').mkdir(exist_ok=True)
    (OUT/'publications/index.html').write_text(bibliography(records))
    (OUT/'publications.bib').write_text('\n\n'.join(bib_record(r) for r in records)+'\n')
    (OUT/'teaching/data-structures').mkdir(parents=True, exist_ok=True)
    (OUT/'teaching/data-structures/index.html').write_text(teaching())
    (OUT/'404.html').write_text(frame('<section class="not-found"><p class="eyebrow">404</p><h1>这个页面暂时找不到</h1><p>请从学术主页访问论文与课程。</p><div class="page-actions"><a class="button" href="' + (safe_url(SITE['site_url']).rstrip('/')+'/' if SITE.get('site_url') else '/') + '">返回主页</a></div></section>', '页面未找到', depth=(SITE['site_url'].rstrip('/')+'/' if SITE.get('site_url') else '/')))
    (OUT/'.nojekyll').touch()
    if SITE.get('site_url'):
        urls = [SITE['site_url'].rstrip('/')+'/'+path for path in ('', 'publications/', 'teaching/data-structures/')]
        (OUT/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{esc(url)}</loc><lastmod>{esc(SITE["updated"])}</lastmod></url>' for url in urls)+'</urlset>')
        (OUT/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+SITE['site_url'].rstrip('/')+'/sitemap.xml\n')
    print(f'Built homepage, publication archive ({len(records)} entries), course page, and 404 page.')

SITE = json.loads((CONTENT/'site.json').read_text())
PAGE = json.loads((CONTENT/'page.json').read_text())
FEATURED = {item['id']: item for item in (PAGE.get('featured') or [])}
HIGHLIGHTS = defaultdict(list)
for item in (PAGE.get('highlights') or []):
    label = (item.get('label') or '').strip()
    if label and label not in HIGHLIGHTS[item['id']]:
        HIGHLIGHTS[item['id']].append(label)
if len(FEATURED) != len((PAGE.get('featured') or [])): raise ValueError('Duplicate featured paper IDs')
research_ids = [item.get('id', '') for item in (PAGE.get('research') or [])]
if len(research_ids) != len(set(research_ids)): raise ValueError('Duplicate research IDs')
reserved_ids = {'main', 'site-nav', 'research', 'selected', 'students', 'contact', 'contact-email'} | set(FEATURED)
for item_id in research_ids:
    if not re.fullmatch(r'[a-z][a-z0-9_-]*', item_id) or item_id in reserved_ids:
        raise ValueError(f'Invalid or reserved research ID: {item_id}')
AUTHORSHIP = json.loads((CONTENT/'authorship.json').read_text())
classification_path = CONTENT/'classifications.json'
CLASSIFICATION_DATA = json.loads(classification_path.read_text()) if classification_path.exists() else {}
CLASSIFICATIONS = {}
for item in (CLASSIFICATION_DATA.get('papers') or []):
    item_id = item.get('id')
    if not isinstance(item_id, str) or not item_id: raise ValueError('Missing classified paper ID')
    if item_id in CLASSIFICATIONS: raise ValueError(f'Duplicate classified paper ID: {item_id}')
    for key, allowed in [('ccf_rank', {'A', 'B', 'C', 'T1', 'T2', 'T3'}), ('indexing', {'SCIE', 'ESCI'})]:
        value = item.get(key)
        if value not in (None, '') and (not isinstance(value, str) or value not in allowed):
            raise ValueError(f'Invalid {key} for {item_id}: {value}')
    for key in ('ccf_source', 'indexing_source'):
        value = item.get(key)
        if value not in (None, ''):
            if not isinstance(value, str): raise ValueError(f'Invalid {key} for {item_id}')
            safe_url(value)
    CLASSIFICATIONS[item_id] = item
if __name__ == '__main__': build()
