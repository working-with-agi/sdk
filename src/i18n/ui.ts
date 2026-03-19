export const languages = {
  ja: '日本語',
  en: 'English',
} as const;

export type Lang = keyof typeof languages;

export const defaultLang: Lang = 'ja';

export const ui = {
  ja: {
    'nav.features': '機能',
    'nav.demo': 'デモ',
    'nav.integration': '導入方法',
    'nav.pricing': '料金',
    'nav.cta': '導入を相談',
    'nav.menu': 'メニュー',
    'meta.title': 'Work with AI — Secretary.io AIアシスタントウィジェット',
    'meta.description': 'プロジェクトデータに基づくAI対話ウィジェット。Vue / React / Angular で簡単に組み込み。リスク分析、進捗要約、アクション提案をリアルタイムで。',
    'meta.og.description': 'AIと対話してプロジェクトを前に進める。Secretary.io Work with AI ウィジェット。',
    'footer.product': 'プロダクト',
    'footer.features': '機能',
    'footer.integration': '導入方法',
    'footer.pricing': '料金',
    'footer.company': '企業情報',
    'footer.about': '会社概要',
    'footer.privacy': 'プライバシーポリシー',
    'footer.terms': '利用規約',
    'footer.support': 'サポート',
    'footer.contact': 'お問い合わせ',
    'footer.tagline': 'AIと一緒に、プロジェクトを前へ',
    'footer.copyright': '© 2026 RE-X K.K. All rights reserved.',
    'footer.powered': 'powered by',
    'footer.secretary': 'Secretary.io Platform',
  },
  en: {
    'nav.features': 'Features',
    'nav.demo': 'Demo',
    'nav.integration': 'Integration',
    'nav.pricing': 'Pricing',
    'nav.cta': 'Get Started',
    'nav.menu': 'Menu',
    'meta.title': 'Work with AI — Secretary.io AI Assistant Widget',
    'meta.description': 'AI conversation widget powered by your project data. Easy integration with Vue / React / Angular. Real-time risk analysis, progress summaries, and action suggestions.',
    'meta.og.description': 'Have AI conversations to move your projects forward. Secretary.io Work with AI widget.',
    'footer.product': 'Product',
    'footer.features': 'Features',
    'footer.integration': 'Integration',
    'footer.pricing': 'Pricing',
    'footer.company': 'Company',
    'footer.about': 'About Us',
    'footer.privacy': 'Privacy Policy',
    'footer.terms': 'Terms of Service',
    'footer.support': 'Support',
    'footer.contact': 'Contact Us',
    'footer.tagline': 'Move your projects forward, with AI',
    'footer.copyright': '© 2026 RE-X K.K. All rights reserved.',
    'footer.powered': 'powered by',
    'footer.secretary': 'Secretary.io Platform',
  },
} as const;

export function getLangFromUrl(url: URL): Lang {
  const [, lang] = url.pathname.split('/');
  if (lang in languages) return lang as Lang;
  return defaultLang;
}

export function useTranslations(lang: Lang) {
  return function t(key: keyof (typeof ui)[typeof defaultLang]): string {
    return (ui[lang] as Record<string, string>)[key] || (ui[defaultLang] as Record<string, string>)[key] || key;
  };
}

export function getLocalePath(lang: Lang, path: string = '/'): string {
  return `/${lang}${path}`;
}

export function getAlternateLang(lang: Lang): Lang {
  return lang === 'ja' ? 'en' : 'ja';
}
