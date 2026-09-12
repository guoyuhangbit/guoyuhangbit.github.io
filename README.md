# 郭宇航 · 个人学术主页

适用于 GitHub Pages 的静态网站。中文为主，保留英文姓名、研究方向和原文论文标题。不展示职称。

页面包括个人介绍、三个研究方向、五项代表成果、完整论文目录、学生与合作信息、点击显示的联系邮箱，以及 2026 年本科数据结构课程入口。课程尚未发布，不包含虚构课件或教学安排。

## 预览

需要 Python 3.10 或更新版本，无第三方依赖。

```sh
python3 build.py
python3 check.py
python3 -m http.server 8765 --directory dist
```

打开 `http://localhost:8765`。`dist` 是可直接发布的静态文件；不需要服务器端 Python。直接双击 `dist/index.html` 也可以阅读首页，但推荐通过本机预览访问完整路由。

## 发布到 GitHub Pages

本站账号为 `guoyuhangbit`，正式地址为 `https://guoyuhangbit.github.io`，对应仓库为 `guoyuhangbit/guoyuhangbit.github.io`。

1. 确定您拥有的发布账号和网站地址。
2. `content/site.json` 中的 `site_url` 已配置为 `https://guoyuhangbit.github.io`，用于规范网址、站点地图和 404 页。
3. 将本项目上传至该账号下的 `<账号>.github.io` 仓库，分支使用 `main`。
4. 打开仓库 Settings → Pages，将 Source 设为 **GitHub Actions**。
5. 在 Actions 中运行 **Publish academic homepage**。此后推送修改会自动构建并发布。

也可以将 `dist` 文件夹内的内容直接作为发布分支的根目录上传，保留 `.nojekyll`，再选择从该分支的根目录发布。

官方说明：[创建 GitHub Pages 网站](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site)。

## 更新内容

- 个人信息、公开链接、网站网址、课程网址、更新日期：`content/site.json`。
- 页面文字、研究方向、代表成果：`build.py` 中 `home()` 和 `FEATURED`。
- 视觉样式：`assets/style.css`。
- 论文书目：`content/publications.bib`。

更新论文时，可从原始 BibTeX 重新导入：

```sh
python3 build.py --import-bib /path/to/mypapers.bib
python3 check.py
```

导入器只保留公开引用字段，移除 Zotero 本地附件路径、私人笔记、摘要和阅读标签。原始文件不受修改，也不要把原始文件放到公开仓库。`content/corrections.json` 保存两处有来源的书目修正，重新导入后会继续应用。增加或删除论文时应同时检查代表成果的文献键。

### 数据结构课程

固定入口是 `/teaching/data-structures/`。有独立课件网址后，填入 `content/site.json` 的 `course_url`，重新构建即可自动显示“进入课程课件”按钮，首页也会更新状态。现阶段为空，页面明确标为筹备中。若之后在本站内制作课件，也可沿用此目录并相应修改生成器，保持学生收藏的入口稳定。

### 邮箱防简单采集

邮箱使用编码字符串保存在 `email_encoded`，页面加载时不呈现明文邮箱或 `mailto:` 链接，访客点击按钮才解码显示并可唤起邮件客户端。更换邮箱时可使用下面的交互命令生成编码：

```sh
python3 -c 'import base64; print(base64.b64encode(input("Email: ").encode()).decode())'
```

将结果填入 `email_encoded`。不在公开配置、HTML 或说明中写出明文邮箱。这只能减少简单采集，无法阻止会运行 JavaScript 或主动解码的爬虫；静态公开网站不能保证隐藏最终要展示的地址。关闭 JavaScript 时提供学院个人页作为联系信息入口。

## 资料来源与修订

原始论文来源：用户提供的 `mypapers.bib`，共 41 条。完整目录按出版年份归档，作者順序照原文保留，将本人姓名加粗。不推断贡献比例、会议等级或引用指标。

作者身份配置见 `content/authorship.json`。26 篇通讯作者身份依据论文作者标记、脚注或出版方通讯说明核对；仅在本人身份得到明确证据时显示。8 篇“等效一作”依据本人确认的学生指导关系及“学生第一作者、导师第二作者”的学校成果认定口径，区别于论文中的共同第一作者声明。2013 年 EMNLP 论文按署名顺序标为第一作者。两类标签可以同时存在。公开证据仅保存来源链接、页码和简短摘录，不包含本地文件路径或明文邮箱。

身份、单位及联系信息核对自[北京理工大学学院个人页](https://cs.bit.edu.cn/szdw/jsml2/yyznyskjsyjs2/46c68d5f9f064fc6bd6b510a62f7c189.htm)。按本人要求不在网站上显示职称。研究分类和中文成果简介为基于论文的编辑性归纳。GitHub BITHLP 是研究组组织；ORCID 使用本人提供的公开记录链接。Google Scholar 在制作时触发访问限流，因此未抄录其引用数量。

两处书目修正均留有来源，见 `content/corrections.json`：一篇论文的作者整组重复已去重；医疗语音翻译论文根据官方 PDF 首页搜索索引补齐作者、2026 年、期刊、卷页及 DOI。未对无法访问的 PDF 声称全文核验，也没有根据 DOI 中的数字猜测出版年。网站公开 BibTeX 为整理版；原始导出文件保持不变。

纯静态页面，无追踪脚本、远程字体或第三方前端依赖。所有论文可在不运行 JavaScript 的情况下阅读，支持手机菜单、键盘访问、年份导航、BibTeX 展开与下载。
