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
KEEP = {'title', 'author', 'date', 'year', 'booktitle', 'journal', 'journaltitle', 'volume', 'number', 'pages', 'publisher', 'doi', 'url'}

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
        names.append('<strong>' + esc(name) + '</strong>' if name in ('Yuhang Guo', '郭宇航') else esc(name))
    return ', '.join(names) if record.get('author') else '作者信息待补充'

def authorship_html(record):
    status = AUTHORSHIP.get(record['id'], {})
    labels = []
    if status.get('first_author'): labels.append(('第一作者', '按论文署名顺序'))
    if status.get('equivalent_first'): labels.append(('等效一作', '学生第一作者、导师第二作者；指导关系经本人确认'))
    if status.get('corresponding'): labels.append(('通讯作者', '依据论文作者标记及通讯说明'))
    if not labels: return ''
    return '<div class="role-tags" aria-label="郭宇航的作者身份">' + ''.join(f'<span class="role-tag" title="{esc(note)}">{label}</span>' for label,note in labels) + '</div>'

def venue(record):
    url = record.get('url', '')
    year = record.get('date', record.get('year', ''))[:4]
    if '.findings-' in url:
        conf = re.search(r'\.findings-([a-z]+)', url)[1].upper()
        return f'{conf} {year}<br>Findings'
    for fragment, label in [('acl-long','ACL'), ('emnlp-main','EMNLP'), ('D13-', 'EMNLP'), ('lrec-main', 'LREC–COLING'), ('iwslt-', 'IWSLT'), ('autosimtrans-', 'AutoSimTrans'), ('ccl-', 'CCL')]:
        if fragment in url: return f'{label} {year}'
    full = plain(record.get('journaltitle', record.get('journal', record.get('booktitle', ''))))
    for marker,label in [('AAAI','AAAI'), ('Neurocomputing','Neurocomputing'), ('Frontiers of Computer Science','FCS'), ('Data Intelligence','Data Intelligence'), ('ICASSP','ICASSP'), ('ICNLP','ICNLP')]:
        if marker in full: return f'{label} {year}'
    return esc(year or '条目信息待补充')

FEATURED = {
 'lan_peap_2026': ('PEAP', '结合视觉与音频感知，研究具身智能体如何主动规划动作序列。', 'https://github.com/BITHLP/PEAP'),
 'tian_beyond_2026': ('RATE', '面向非字面翻译建立评估基准，探索更贴近语义的翻译质量评价。', 'https://github.com/BITHLP/RATE'),
 'li2025': ('HomeBench', '覆盖单设备、多设备及有效与无效指令，评估大模型在智能家居中的指令理解能力。', 'https://github.com/BITHLP/HomeBench'),
 'yao2025': ('ReFF', '围绕输出格式遵循开展强化学习研究，提高大模型跨任务的格式可靠性。', 'https://github.com/BITHLP/ReFF'),
 'xia2025': ('SafeToolBench', '从工具调用的潜在后果出发，评估大模型使用工具时的安全性。', 'https://github.com/BITHLP/SafeToolBench')
}

def paper(record, featured=False):
    url = record.get('url') or ('https://doi.org/' + record['doi'] if record.get('doi') else '')
    title = esc(plain(record.get('title', '')))
    title_html = f'<a href="{safe_url(url)}" target="_blank" rel="noopener noreferrer">{title}</a>' if url else title
    links = f'<a href="{safe_url(url)}" target="_blank" rel="noopener noreferrer">论文 <span aria-hidden="true">↗</span></a>' if url else ''
    extra = FEATURED.get(record['id'])
    if extra: links += f'<a href="{safe_url(extra[2])}" target="_blank" rel="noopener noreferrer">代码与数据 <span aria-hidden="true">↗</span></a>'
    summary = f'<p class="pub-summary">{esc(extra[1])}</p>' if featured and extra else ''
    full = plain(record.get('journaltitle', record.get('journal', record.get('booktitle', ''))))
    full_html = f'<p class="paper-venue-full">{esc(full)}</p>' if not featured and full else ''
    citation = '' if featured else f'<details class="citation"><summary>BibTeX 引用</summary><pre>{esc(bib_record(record))}</pre></details>'
    return f'<article class="publication" id="{esc(record["id"])}"><div class="venue">{venue(record)}</div><div class="pub-body"><h3>{title_html}</h3><p class="authors">{authors_html(record)}</p>{authorship_html(record)}{full_html}{summary}<div class="pub-links">{links}</div>{citation}</div></article>'

def frame(body, title, depth='', current='home', page_path=''):
    nav = [('research', '研究方向', depth+'index.html#research'), ('publications', '学术成果', depth+'publications/'), ('students', '学生与合作', depth+'index.html#students'), ('teaching', '教学', depth+'teaching/data-structures/'), ('contact', '联系', depth+'index.html#contact')]
    nav_html = ''.join(f'<a href="{url}"' + (' aria-current="page"' if key==current else '') + f'>{name}</a>' for key,name,url in nav)
    canonical = f'<link rel="canonical" href="{safe_url(SITE["site_url"].rstrip("/")+"/"+page_path)}">' if SITE.get('site_url') else ''
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{esc(title)} · 郭宇航 Yuhang Guo</title><meta name="description" content="郭宇航，北京理工大学计算机学院。研究自然语言处理、机器翻译、多模态交互与大模型智能体。学术论文、开源成果及数据结构课程。"><meta property="og:title" content="{esc(title)} · 郭宇航 Yuhang Guo"><meta property="og:type" content="website">{canonical}<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='4' fill='%23152e2a'/%3E%3Ctext x='20' y='28' text-anchor='middle' fill='white' font-family='Georgia' font-size='27'%3EG%3C/text%3E%3C/svg%3E"><link rel="stylesheet" href="{depth}assets/style.css"><script src="{depth}assets/site.js" defer></script></head>
<body><a class="skip" href="#main">跳至正文</a><header class="site-header"><div class="wrap header-inner"><a class="brand" href="{depth}index.html" aria-label="郭宇航，返回首页"><span class="monogram" aria-hidden="true">G</span><span>郭宇航 <small>YUHANG GUO</small></span></a><button class="menu-button" aria-expanded="false" aria-controls="site-nav">菜单</button><nav class="nav" id="site-nav" aria-label="主导航">{nav_html}</nav></div></header>
<main id="main" class="wrap">{body}</main><footer class="footer"><div class="wrap footer-inner"><span>© {SITE['updated'][:4]} 郭宇航 · Yuhang Guo</span><span>北京理工大学 · 计算机学院</span><span>更新于 {SITE['updated']}</span></div></footer></body></html>'''

def contact():
    if SITE.get('email_encoded'):
        action = f'<button class="button" data-contact="{esc(SITE["email_encoded"])}" aria-controls="contact-email">显示联系邮箱 <span aria-hidden="true">↗</span></button><span id="contact-email" class="email-result" aria-live="polite"></span><noscript><a class="inline-link" href="{safe_url(SITE["faculty"])}">学院个人页面联系方式</a></noscript>'
    else: action = f'<a class="button" href="{safe_url(SITE["faculty"])}" target="_blank" rel="noopener noreferrer">学院个人页面 ↗</a>'
    return f'<section class="contact" id="contact"><div><h2>联系我</h2><p>研究交流、学生指导与合作探讨</p></div><div class="contact-action">{action}</div></section>'

def home(records):
    selected = ''.join(paper(next(r for r in records if r['id']==key), True) for key in FEATURED)
    course_status = '进入网页版课件' if SITE.get('course_url') else '网页版课件筹备中'
    return frame(f'''
<section class="hero"><div><p class="eyebrow">BEIJING INSTITUTE OF TECHNOLOGY</p><h1>郭宇航</h1><p class="english-name" lang="en">Yuhang Guo</p><p class="affiliation">{SITE['affiliation']}</p><p class="intro">我研究自然语言处理与语言智能，关注机器如何理解语言、连接多模态信息，并在真实场景中可靠地完成任务。</p><div class="social"><a href="{safe_url(SITE['scholar'])}" target="_blank" rel="noopener noreferrer">Google Scholar <span class="external" aria-hidden="true">↗</span></a><a href="{safe_url(SITE['github'])}" target="_blank" rel="noopener noreferrer">GitHub · BITHLP <span class="external" aria-hidden="true">↗</span></a><a href="{safe_url(SITE['orcid'])}" target="_blank" rel="noopener noreferrer">ORCID <span class="external" aria-hidden="true">↗</span></a></div></div>
<aside class="research-index" aria-label="研究领域"><p>RESEARCH FOCUS</p><a class="index-item" href="#language"><span>01</span><div><b>语言理解与机器翻译</b><small>Language Understanding & Translation</small></div></a><a class="index-item" href="#multimodal"><span>02</span><div><b>多模态感知与交互</b><small>Multimodal Perception & Interaction</small></div></a><a class="index-item" href="#agents"><span>03</span><div><b>大模型与可信智能体</b><small>Language Models & Reliable Agents</small></div></a></aside></section>
<a class="course-banner" href="teaching/data-structures/"><span class="course-year">2026<br>本科教学</span><span class="course-info"><strong>数据结构</strong><span class="course-note">Data Structures · {course_status}</span></span><span class="go">课程主页 <span aria-hidden="true">↗</span></span></a>
<section class="section" id="research"><div class="section-heading"><h2>研究方向</h2><span class="label">RESEARCH</span></div><div class="research-grid"><article class="research-block" id="language"><span class="number">01 / LANGUAGE</span><h3>语言理解与机器翻译</h3><p>从实体识别与信息抽取，到同声传译、图像内翻译与非字面翻译评价，研究跨语言、跨场景的信息理解与表达。</p><p class="keywords">信息抽取 · 语音翻译 · 翻译评估</p></article><article class="research-block" id="multimodal"><span class="number">02 / MULTIMODAL</span><h3>多模态感知与交互</h3><p>融合语音、视觉与文本，探索多模态对话、语音生成与具身动作规划，让模型更好地理解情境与交互意图。</p><p class="keywords">语音与音频 · 多模态对话 · 具身规划</p></article><article class="research-block" id="agents"><span class="number">03 / AGENTS</span><h3>大模型与可信智能体</h3><p>围绕模型编辑、输出格式遵循、工具调用与智能家居任务，研究大模型的能力增强，以及可验证的可靠性与安全性。</p><p class="keywords">强化学习 · 模型编辑 · 工具安全</p></article></div></section>
<section class="section" id="selected"><div class="section-heading"><h2>代表成果</h2><span class="label">SELECTED WORK</span><a class="more" href="publications/">完整论文列表 <span aria-hidden="true">↗</span></a></div>{selected}</section>
<section class="section" id="students"><div class="section-heading"><h2>学生与合作</h2><span class="label">STUDENTS & COLLABORATION</span></div><div class="student-grid"><article><h3>从一个感兴趣的问题开始</h3><p>如果你正在了解研究方向、选择导师，可以先阅读一篇感兴趣的论文，或运行一个开源项目，思考你想进一步解决的问题。</p><ul><li>语言理解、机器翻译与信息抽取</li><li>多模态交互与智能体任务规划</li><li>大模型评估、能力增强与安全性</li></ul></article><article><h3>让研究成果成为交流的起点</h3><p>论文与开源项目提供了方法、评测和实验实现。欢迎围绕具体应用场景、数据条件与技术问题展开交流。</p><p>联系时可简要介绍背景、感兴趣的工作与希望讨论的问题。</p><a class="inline-link" href="#contact">联系交流</a> <span aria-hidden="true">↗</span></article></div></section>{contact()}''', '个人学术主页')

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
    return frame(f'<div class="page-heading"><p class="eyebrow">PUBLICATIONS</p><h1>学术成果</h1><p>按年份整理的 {len(records)} 篇论文，涵盖语言理解、机器翻译、多模态交互与大模型智能体。作者按原文顺序列出。</p><p class="authorship-note">作者身份标签均指郭宇航。通讯作者按论文署名说明标注；等效一作采用“学生第一作者、导师第二作者”的成果认定口径，不代表论文声明的共同第一作者。</p><div class="page-actions"><a class="button" href="../publications.bib" download>下载全部 BibTeX</a><a class="button" href="{safe_url(SITE["scholar"])}" target="_blank" rel="noopener noreferrer">Google Scholar ↗</a></div></div><div class="bibliography-layout"><nav class="year-nav" aria-label="论文年份">{years_nav}</nav><div>{sections}</div></div>', '学术成果', '../', 'publications', 'publications/')

def teaching():
    if SITE.get('course_url'):
        status = f'<h2>网页版课件</h2><p>课程课件已开放，请通过下方入口访问。</p><a class="button" href="{safe_url(SITE["course_url"])}" target="_blank" rel="noopener noreferrer">进入课程课件 ↗</a>'
    else:
        status = '<h2>课件正在准备中</h2><p>本课程计划采用网页版课件进行本科教学。目前课件尚未发布。</p><p>课件上线后将在本页提供访问入口。你可以收藏此页，后续从这里进入课程。</p>'
    return frame(f'<div class="course-page"><div class="page-heading"><p class="eyebrow">TEACHING / 2026</p><h1>数据结构</h1><p class="english-name" lang="en">Data Structures</p><p>本科课程 · 郭宇航 · 北京理工大学计算机学院</p></div><div class="course-layout"><section class="course-state">{status}<p class="subtle-note">具体教学安排以课堂通知为准。</p></section><aside class="course-details"><h2>课程信息</h2><dl><dt>授课对象</dt><dd>本科生</dd><dt>教学年份</dt><dd>2026</dd><dt>课件形式</dt><dd>网页版</dd><dt>课程联系</dt><dd><a class="inline-link" href="../../index.html#contact">教师联系方式 ↗</a></dd></dl></aside></div><div class="page-actions"><a class="inline-link" href="../../index.html">← 返回学术主页</a></div></div>', '数据结构 · 本科课程', '../../', 'teaching', 'teaching/data-structures/')

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
        (OUT/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{esc(url)}</loc><lastmod>{SITE["updated"]}</lastmod></url>' for url in urls)+'</urlset>')
        (OUT/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+SITE['site_url'].rstrip('/')+'/sitemap.xml\n')
    print(f'Built homepage, publication archive ({len(records)} entries), course page, and 404 page.')

SITE = json.loads((CONTENT/'site.json').read_text())
AUTHORSHIP = json.loads((CONTENT/'authorship.json').read_text())
if __name__ == '__main__': build()
