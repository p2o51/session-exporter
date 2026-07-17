import * as path from 'node:path';
import { defineConfig } from 'rspress/config';

const GITHUB = 'https://github.com/p2o51/session-exporter';

// One shared page structure → nav + sidebar are generated per language, so the
// three locales never drift. `label` maps lang → display text.
type L = { en: string; zh: string; ja: string };
const t = (en: string, zh: string, ja: string): L => ({ en, zh, ja });

const GUIDE: { slug: string; label: L }[] = [
  { slug: 'getting-started', label: t('Getting started', '快速开始', 'はじめに') },
  { slug: 'browsing-exporting', label: t('Browse & export', '浏览与导出', '閲覧とエクスポート') },
  { slug: 'tokens-and-cost', label: t('Tokens & cost', 'Token 与花费', 'トークンとコスト') },
  { slug: 'notion', label: t('Export to Notion', '导出到 Notion', 'Notion へエクスポート') },
  { slug: 'data-sources', label: t('Data & privacy', '数据与隐私', 'データとプライバシー') },
];

const NAV_GUIDE = t('Guide', '指南', 'ガイド');
const SIDEBAR_GUIDE = t('Guide', '指南', 'ガイド');

function prefix(lang: string) {
  return lang === 'en' ? '' : `/${lang}`;
}

function navFor(lang: keyof L) {
  return [
    { text: NAV_GUIDE[lang], link: `${prefix(lang)}/guide/getting-started` },
    { text: 'GitHub', link: GITHUB },
  ];
}

function sidebarFor(lang: keyof L) {
  return {
    [`${prefix(lang)}/guide/`]: [
      {
        text: SIDEBAR_GUIDE[lang],
        items: GUIDE.map((g) => ({
          text: g.label[lang],
          link: `${prefix(lang)}/guide/${g.slug}`,
        })),
      },
    ],
  };
}

export default defineConfig({
  root: path.join(__dirname, 'docs'),
  base: '/session-exporter/',
  title: 'Session Exporter',
  icon: '/logo.svg',
  logo: '/logo.svg',
  logoText: 'Session Exporter',
  lang: 'en',
  locales: [
    { lang: 'en', label: 'English', title: 'Session Exporter', description: 'Browse & export your local AI coding-agent history' },
    { lang: 'zh', label: '简体中文', title: 'Session Exporter', description: '浏览并导出本地 AI 编程代理会话历史' },
    { lang: 'ja', label: '日本語', title: 'Session Exporter', description: 'ローカル AI コーディングエージェントの履歴を閲覧・エクスポート' },
  ],
  themeConfig: {
    footer: { message: 'MIT Licensed · © 2026 Session Exporter' },
    socialLinks: [{ icon: 'github', mode: 'link', content: GITHUB }],
    locales: [
      { lang: 'en', label: 'English', outlineTitle: 'On this page', prevPageText: 'Previous', nextPageText: 'Next', nav: navFor('en'), sidebar: sidebarFor('en') },
      { lang: 'zh', label: '简体中文', outlineTitle: '本页目录', prevPageText: '上一页', nextPageText: '下一页', nav: navFor('zh'), sidebar: sidebarFor('zh') },
      { lang: 'ja', label: '日本語', outlineTitle: '目次', prevPageText: '前へ', nextPageText: '次へ', nav: navFor('ja'), sidebar: sidebarFor('ja') },
    ],
  },
});
