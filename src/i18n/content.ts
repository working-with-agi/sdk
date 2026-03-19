import type { Lang } from './ui';

export interface HeroSlide {
  badge: string;
  title: string;
  titleAccent: string;
  subtitle: string;
}

export interface HeroContent {
  slides: HeroSlide[];
  ctaPrimary: string;
  ctaSecondary: string;
  stat1Value: string;
  stat1Label: string;
  stat2Value: string;
  stat2Label: string;
  stat3Value: string;
  stat3Label: string;
}

export interface FeatureCard {
  icon: string;
  title: string;
  desc: string;
}

export interface FeaturesContent {
  eyebrow: string;
  title: string;
  subtitle: string;
  cards: FeatureCard[];
}

export interface DemoContent {
  eyebrow: string;
  title: string;
  subtitle: string;
  placeholder: string;
  sendBtn: string;
  suggestions: string[];
  demoResponses: Record<string, { text: string; widgets?: { type: string; title: string; items: string[] }[] }>;
}

export interface IntegrationContent {
  eyebrow: string;
  title: string;
  subtitle: string;
  steps: { step: string; title: string; desc: string }[];
}

export interface UseCaseItem {
  icon: string;
  title: string;
  desc: string;
}

export interface UseCasesContent {
  eyebrow: string;
  title: string;
  items: UseCaseItem[];
}

export interface FAQItem {
  question: string;
  answer: string;
}

export interface FAQContent {
  eyebrow: string;
  title: string;
  items: FAQItem[];
}

export interface PricingTier {
  name: string;
  price: string;
  period: string;
  desc: string;
  features: string[];
  cta: string;
  featured?: boolean;
  badge?: string;
}

export interface PricingContent {
  eyebrow: string;
  title: string;
  subtitle: string;
  tiers: PricingTier[];
}

export interface CTAContent {
  title: string;
  desc: string;
  primaryBtn: string;
  secondaryBtn: string;
  note: string;
}

export interface PageContent {
  hero: HeroContent;
  features: FeaturesContent;
  demo: DemoContent;
  integration: IntegrationContent;
  useCases: UseCasesContent;
  pricing: PricingContent;
  faq: FAQContent;
  cta: CTAContent;
}

export const content: Record<Lang, PageContent> = {
  ja: {
    hero: {
      slides: [
        {
          badge: 'Work with AI',
          title: 'あなたのサービスに',
          titleAccent: 'AIワークスペースを組み込む',
          subtitle: 'まるでソフトウェアのような対話画面で、ユーザーがAIと一緒に作業を進められるウィジェット。Vue / React / Angular 対応で簡単に統合可能。',
        },
        {
          badge: 'Concept — MAGI',
          title: '3人の賢者が合議する',
          titleAccent: 'AI エージェント',
          subtitle: 'MAGI（Multi Agent General Instrument）— 複数のAIエージェントが異なる視点から議論し、多角的に検証された結論を導きます。賛成・反対・中立の立場から分析を繰り返し、偏りのない判断を支援します。',
        },
        {
          badge: 'Skill Registry',
          title: '組み込まれたシステムの操作を',
          titleAccent: 'AIから実現',
          subtitle: 'あなたのサービスに特化したスキルを登録し、AIがデータ分析からタスク実行まで自律的にこなします。「これをやって」と指示するだけ。',
        },
      ],
      ctaPrimary: 'デモを試す',
      ctaSecondary: '導入ガイドを見る',
      stat1Value: '5分',
      stat1Label: '導入時間',
      stat2Value: '3+',
      stat2Label: '対応フレームワーク',
      stat3Value: '5種',
      stat3Label: 'AIスキル',
    },
    features: {
      eyebrow: 'Features',
      title: 'Knowledge Hub と Skill Registry',
      subtitle: 'Work with AI の中核は2つの基盤で構成されています。Knowledge Hub がドキュメントやデータを蓄積・検索可能にし、Skill Registry がそのデータを活用してシステム操作を AI から実現します。まるでソフトウェアのような対話画面で、ユーザーは AI と一緒に作業を進められます。',
      cards: [
        { icon: 'risk', title: 'Knowledge Hub', desc: 'サービスに蓄積されたドキュメント・データを知識基盤として管理。RAG（検索拡張生成）により、AIが常に最新の文脈を把握した上で応答します。' },
        { icon: 'compare', title: 'Skill Registry', desc: 'Knowledge Hub の上で動くスキルを登録。スキルが「何を知っているか」はナレッジが提供し、「何ができるか」をスキルが定義。システム操作を AI から実現します。' },
        { icon: 'progress', title: 'レポート自動生成', desc: '散在するデータを Knowledge Hub から横断的に収集し、レポートやサマリーを自動生成。定型作業を大幅に削減します。' },
        { icon: 'action', title: 'アクション提案と実行', desc: 'ナレッジの文脈から次にやるべきアクションを提案。承認フロー付きで、AIが実際のタスク実行まで支援します。' },
        { icon: 'timeline', title: 'エージェント自律実行', desc: '「これをやって」と指示するだけ。AIが Knowledge Hub からデータを収集し、スキルを使って分析・レポート作成まで一貫して遂行します。' },
        { icon: 'chat', title: 'MCP連携', desc: 'Model Context Protocol対応。外部ツールやAPIに直接アクセスし、Knowledge Hub とスキルの能力を拡張。エコシステム全体と統合できます。' },
      ],
    },
    demo: {
      eyebrow: 'Live Demo',
      title: '今すぐ体験してみましょう',
      subtitle: 'AIがプロジェクトデータにアクセスし、分析やタスク実行を行う様子を体験できます。',
      placeholder: 'メッセージを入力...',
      sendBtn: '送信',
      suggestions: [
        '今週のプロジェクト状況をまとめて',
        'リスクがあれば検知して対策を立てて',
        '次のスプリントの計画を作って',
        '全プロジェクトの共通課題を分析して',
      ],
      demoResponses: {
        '今週のプロジェクト状況をまとめて': {
          text: 'プロジェクトデータを分析中...\n\n進捗レポートを作成しました。',
          widgets: [{
            type: 'progress_summary',
            title: '進捗レポート（自動生成）',
            items: [
              'API開発: 78% 完了 — Sprint 3のエンドポイント実装が順調',
              'フロントエンド: 62% 完了 — デザインレビュー待ちが2件',
              'インフラ: 91% 完了 — 本番環境のセットアップ完了',
              '→ 全体: 予定通り進行中。リリース目標日 4/15 は達成可能',
            ],
          }],
        },
        'リスクがあれば検知して対策を立てて': {
          text: '会議データとタスク状況を横断分析中...\n\nリスクを3件検知しました。対策案を生成します。',
          widgets: [{
            type: 'risk_analysis',
            title: 'リスク検知結果 + 対策案',
            items: [
              '🔴 高: 外部API連携テストが未着手（期限まで5日）→ 対策: 田中さんの担当タスクを再優先度付け、明日中にテスト計画を作成',
              '🟡 中: デザイナーリソース競合 → 対策: プロジェクトBのデザインタスクを来週にずらす提案をPMに送信',
              '🟡 中: 認証モジュールの技術選定が未確定 → 対策: 比較資料のドラフトを作成し、次回の技術会議のアジェンダに追加',
            ],
          }],
        },
        '次のスプリントの計画を作って': {
          text: '前回スプリントの残タスクと優先度を分析中...\n\nSprint 4の計画案を作成しました。',
          widgets: [{
            type: 'action_items',
            title: 'Sprint 4 計画案',
            items: [
              '1. 外部API連携の結合テスト実施 → 田中（5pt）',
              '2. 認証モジュールの実装 → 鈴木（8pt）',
              '3. デザインレビュー完了 + フロントエンド実装 → 佐藤（5pt）',
              '4. E2Eテスト環境構築 → チーム（3pt）',
              '→ 合計: 21pt / キャパシティ: 25pt — 余裕あり',
            ],
          }],
        },
        '全プロジェクトの共通課題を分析して': {
          text: '3プロジェクトのデータを横断分析中...\n\n共通課題を特定し、改善提案を作成しました。',
          widgets: [{
            type: 'comparative_analysis',
            title: '横断分析レポート',
            items: [
              'テスト自動化の遅れ: 3プロジェクト中2つでカバレッジ目標未達 → 共通テスト基盤の構築を提案',
              'ドキュメント負債: API仕様書の更新が全プロジェクトで滞留 → CI/CDにドキュメント生成を組み込む提案',
              'リソース競合: シニアエンジニア2名が3プロジェクトを兼任 → リソース配分の見直しを経営層に報告',
            ],
          }],
        },
      },
    },
    integration: {
      eyebrow: 'Integration',
      title: 'あなたのプロダクトにAIエージェントを組み込む',
      subtitle: 'Vue / React / Angular 対応。数行のコードでプロダクトにAI対話画面を埋め込めます。',
      steps: [
        { step: '01', title: 'パッケージをインストール', desc: 'npm でウィジェットパッケージをインストール。AI対話UIが含まれます。' },
        { step: '02', title: 'AgentServerに接続', desc: 'AgentServer（AetherTerm）のURLを指定。APIキーとスキル・コンテキストを設定します。' },
        { step: '03', title: 'コンポーネントを配置', desc: 'コンポーネントを配置するだけ。ユーザーはソフトウェアのような対話画面でAIと作業を進められます。' },
      ],
    },
    useCases: {
      eyebrow: 'Use Cases',
      title: 'こんなシーンで活用できます',
      items: [
        { icon: 'dashboard', title: 'プロジェクトダッシュボード', desc: '社内ダッシュボードに埋め込んで、チームメンバーが自然言語でプロジェクト状況を照会。エージェントモードなら分析からレポート生成まで自律実行。' },
        { icon: 'standup', title: 'デイリースタンドアップ', desc: '朝会の前にAIに状況をまとめてもらい、議論のポイントを事前に把握。専門知識がなくてもAIに指示するだけで準備が完了。' },
        { icon: 'review', title: 'スプリントレビュー', desc: 'スプリント全体の進捗と残課題をAIが構造化。レビュー会議の準備を効率化。' },
        { icon: 'exec', title: '経営報告', desc: '複数プロジェクトの横断サマリーを自動生成。経営層への報告資料作成を支援。' },
      ],
    },
    faq: {
      eyebrow: 'FAQ',
      title: 'よくある質問',
      items: [
        { question: 'チャットボットとどう違うのですか？', answer: 'チャットボットは質問に答えるだけですが、Work with AI のAIエージェントは自律的にタスクを計画・実行します。「レポートを作って」と指示すれば、データ収集から構成・生成まで一貫して遂行。作業過程が見え、途中で方向修正もできます。まるでソフトウェアのような対話画面で、AIに仕事を「やってもらう」体験を提供します。' },
        { question: 'どのようなデータにアクセスしますか？', answer: 'Secretary.io に蓄積された会議議事録、タスク、プロジェクト構造にアクセスします。MCP（Model Context Protocol）経由でLinear、Jira、Google Calendarなどの外部ツールにも接続可能です。テナントごとにデータは完全に分離されています。' },
        { question: 'エージェントは勝手に操作を実行しますか？', answer: 'いいえ。破壊的な操作（チケット作成、データ更新など）は承認フローを経由します。分析やレポート生成は自律的に実行しますが、外部への書き込みはユーザーの確認を待ちます。' },
        { question: '導入は簡単ですか？', answer: 'はい。npm パッケージをインストールし、接続先のURLとAPIキーを設定するだけです。最短5分で動作します。' },
        { question: 'オンプレミス環境でも利用できますか？', answer: 'Enterpriseプランでは、AgentServerとAIバックエンドのセルフホスト版を提供しています。お客様のインフラ内で完結する構成が可能です。' },
      ],
    },
    pricing: {
      eyebrow: 'Pricing',
      title: 'Secretary.io プランに含まれています',
      subtitle: 'Work with AI は Secretary.io の全有料プランでご利用いただけます。AIクレジットは議事録要約・プロジェクト分析・エージェント実行で共有されます。',
      tiers: [
        {
          name: 'Starter',
          price: '¥4,980',
          period: '/月',
          desc: '小規模チーム向け',
          features: ['月1,800分の録音', '10プロジェクト', 'AIクレジット: 2,000/月', 'Work with AI 利用可', 'メールサポート'],
          cta: '早期アクセスを申請',
        },
        {
          name: 'Business',
          price: '¥14,800',
          period: '/月',
          desc: '成長中のチーム向け',
          features: ['無制限の録音', '無制限プロジェクト', 'AIクレジット: 10,000/月', 'Work with AI 利用可', 'バッジ非表示', 'チーム管理', '優先サポート'],
          cta: '早期アクセスを申請',
          featured: true,
          badge: 'おすすめ',
        },
        {
          name: 'Enterprise',
          price: 'お問い合わせ',
          period: '',
          desc: '大規模組織向け',
          features: ['全Business機能', 'AIクレジット: 無制限', 'セルフホスト対応', 'SSO / SAML', 'SLA保証', '専任サポート'],
          cta: 'お問い合わせ',
        },
      ],
    },
    cta: {
      title: 'AIアシスタントをあなたのプロダクトに',
      desc: 'Work with AI ウィジェットの導入相談や、カスタマイズのご要望はお気軽にお問い合わせください。',
      primaryBtn: '導入を相談する',
      secondaryBtn: 'ドキュメントを見る',
      note: '初期導入サポート無料 · 14日間トライアル',
    },
  },
  en: {
    hero: {
      slides: [
        {
          badge: 'Work with AI',
          title: 'Embed an AI workspace',
          titleAccent: 'into your service',
          subtitle: 'A software-like interface where users work alongside AI. Supports Vue / React / Angular. Just say "do this" and AI handles the rest.',
        },
        {
          badge: 'Concept — MAGI',
          title: 'Three wise agents',
          titleAccent: 'deliberate together',
          subtitle: 'MAGI (Multi Agent General Instrument) — Multiple AI agents discuss from different perspectives, delivering conclusions verified from multiple angles. Pros, cons, and neutral viewpoints eliminate blind spots.',
        },
        {
          badge: 'Skill Registry',
          title: 'Let AI operate',
          titleAccent: 'your integrated systems',
          subtitle: 'Register skills tailored to your service. AI autonomously handles data analysis, report generation, and task execution. Just say "do this".',
        },
      ],
      ctaPrimary: 'Try the Demo',
      ctaSecondary: 'Integration Guide',
      stat1Value: '5 min',
      stat1Label: 'Setup time',
      stat2Value: '3+',
      stat2Label: 'Frameworks',
      stat3Value: 'Autonomous',
      stat3Label: 'Not just chat',
    },
    features: {
      eyebrow: 'Capabilities',
      title: 'Knowledge Hub & Skill Registry',
      subtitle: 'Work with AI is built on two foundations. Knowledge Hub accumulates and makes your documents and data searchable. Skill Registry enables AI to operate your systems using that knowledge — through a software-like interface.',
      cards: [
        { icon: 'risk', title: 'Knowledge Hub', desc: 'Manage documents and data as a knowledge foundation. RAG (Retrieval-Augmented Generation) ensures AI always responds with up-to-date context from your service.' },
        { icon: 'compare', title: 'Skill Registry', desc: 'Register skills that run on top of Knowledge Hub. Knowledge provides "what AI knows", skills define "what AI can do". Enable system operations from AI.' },
        { icon: 'progress', title: 'Auto-Generated Reports', desc: 'Cross-collect data from Knowledge Hub and autonomously generate reports and summaries. Drastically reduce routine work.' },
        { icon: 'action', title: 'Action Proposals & Execution', desc: 'Propose next actions from knowledge context. With approval workflows, AI supports actual task execution.' },
        { icon: 'timeline', title: 'Autonomous Agent Execution', desc: 'Just say "do this". AI collects data from Knowledge Hub, uses skills to analyze, and produces reports end-to-end.' },
        { icon: 'chat', title: 'MCP Integration', desc: 'Model Context Protocol support. Access external tools and APIs directly, extending the capabilities of Knowledge Hub and skills across your ecosystem.' },
      ],
    },
    demo: {
      eyebrow: 'Live Demo',
      title: 'Experience the AI agent in action',
      subtitle: 'See how the AI agent accesses project data and autonomously executes tasks through a software-like interface.',
      placeholder: 'Enter instructions...',
      sendBtn: 'Run',
      suggestions: [
        'Summarize this week\'s project status',
        'Detect risks and create mitigation plans',
        'Plan the next sprint',
        'Analyze common issues across all projects',
      ],
      demoResponses: {
        'Summarize this week\'s project status': {
          text: 'Analyzing project data...\n\nProgress report generated.',
          widgets: [{
            type: 'progress_summary',
            title: 'Progress Report (auto-generated)',
            items: [
              'API Development: 78% complete — Sprint 3 endpoint implementation on track',
              'Frontend: 62% complete — 2 items awaiting design review',
              'Infrastructure: 91% complete — Production environment setup done',
              '→ Overall: On schedule. Release target date 4/15 is achievable',
            ],
          }],
        },
        'Detect risks and create mitigation plans': {
          text: 'Cross-analyzing meeting data and task status...\n\n3 risks detected. Generating mitigation plans.',
          widgets: [{
            type: 'risk_analysis',
            title: 'Risk Detection + Mitigation Plans',
            items: [
              '🔴 High: External API integration testing not started (5 days to deadline) → Action: Reprioritize Tanaka\'s tasks, create test plan by tomorrow',
              '🟡 Medium: Designer resource conflict → Action: Propose deferring Project B design tasks to next week',
              '🟡 Medium: Auth module tech selection undecided → Action: Draft comparison doc and add to next tech meeting agenda',
            ],
          }],
        },
        'Plan the next sprint': {
          text: 'Analyzing remaining tasks and priorities from last sprint...\n\nSprint 4 plan created.',
          widgets: [{
            type: 'action_items',
            title: 'Sprint 4 Plan',
            items: [
              '1. External API integration testing → Tanaka (5pt)',
              '2. Auth module implementation → Suzuki (8pt)',
              '3. Design review completion + frontend → Sato (5pt)',
              '4. E2E test environment setup → Team (3pt)',
              '→ Total: 21pt / Capacity: 25pt — room to spare',
            ],
          }],
        },
        'Analyze common issues across all projects': {
          text: 'Cross-analyzing 3 projects...\n\nCommon issues identified with improvement proposals.',
          widgets: [{
            type: 'comparative_analysis',
            title: 'Cross-Project Analysis Report',
            items: [
              'Test automation lag: 2 of 3 projects below coverage targets → Propose shared test infrastructure',
              'Documentation debt: API spec updates stalled everywhere → Propose CI/CD doc generation integration',
              'Resource conflicts: 2 senior engineers across 3 projects → Recommend reallocation report to leadership',
            ],
          }],
        },
      },
    },
    integration: {
      eyebrow: 'Integration',
      title: 'Embed an AI agent in your product',
      subtitle: 'Supports Vue / React / Angular. Embed a software-like AI workspace in your product with a few lines of code.',
      steps: [
        { step: '01', title: 'Install the package', desc: 'Install via npm. Includes the AI workspace UI component.' },
        { step: '02', title: 'Connect to AgentServer', desc: 'Point to your AgentServer (AetherTerm) URL. Configure API key, skills, and context.' },
        { step: '03', title: 'Place the component', desc: 'Drop in the component. Users interact with the AI agent through a software-like interface.' },
      ],
    },
    useCases: {
      eyebrow: 'Use Cases',
      title: 'AI agents for everyone, not just engineers',
      items: [
        { icon: 'dashboard', title: 'Project Managers', desc: 'Just say "find risks and create mitigation plans." The agent analyzes data and auto-generates reports.' },
        { icon: 'standup', title: 'Sales & Customer Success', desc: 'The agent creates client progress reports, extracting accurate information from meeting data.' },
        { icon: 'review', title: 'Executives', desc: 'One instruction — "show me all project status" — and the agent generates a cross-project executive summary.' },
        { icon: 'exec', title: 'Back Office', desc: 'Minutes organization, action item tracking, document creation — delegate routine tasks to the agent.' },
      ],
    },
    faq: {
      eyebrow: 'FAQ',
      title: 'Frequently Asked Questions',
      items: [
        { question: 'How is this different from a chatbot?', answer: 'Chatbots only answer questions. Work with AI agents autonomously plan and execute tasks. Say "create a report" and the agent collects data, structures it, and generates the output. You can see the work process and redirect at any point — a software-like experience of letting AI do the work for you.' },
        { question: 'What data does it access?', answer: 'Meeting minutes, tasks, and project structure stored in Secretary.io. Via MCP (Model Context Protocol), it can also connect to Linear, Jira, Google Calendar, and other tools. Data is completely isolated per tenant.' },
        { question: 'Does the agent execute actions without permission?', answer: 'No. Destructive operations (ticket creation, data updates) go through an approval flow. Analysis and report generation run autonomously, but writes to external systems wait for user confirmation.' },
        { question: 'Is it easy to integrate?', answer: 'Yes. Install the npm package, set the connection URL and API key. Up and running in 5 minutes.' },
        { question: 'Can it run on-premise?', answer: 'Enterprise plans include self-hosted AgentServer and AI backend, enabling a fully on-premise deployment.' },
      ],
    },
    pricing: {
      eyebrow: 'Pricing',
      title: 'Included in every Secretary.io plan',
      subtitle: 'Work with AI is available on all paid Secretary.io plans. AI credits are shared across meeting summaries, project analysis, and agent execution.',
      tiers: [
        {
          name: 'Starter',
          price: '$33',
          period: '/mo',
          desc: 'For small teams',
          features: ['1,800 min/month recording', '10 projects', 'AI credits: 2,000/mo', 'Work with AI included', 'Email support'],
          cta: 'Request Early Access',
        },
        {
          name: 'Business',
          price: '$99',
          period: '/mo',
          desc: 'For growing teams',
          features: ['Unlimited recording', 'Unlimited projects', 'AI credits: 10,000/mo', 'Work with AI included', 'No badge', 'Team management', 'Priority support'],
          cta: 'Request Early Access',
          featured: true,
          badge: 'Popular',
        },
        {
          name: 'Enterprise',
          price: 'Contact us',
          period: '',
          desc: 'For large organizations',
          features: ['All Business features', 'AI credits: unlimited', 'Self-hosted option', 'SSO / SAML', 'SLA guarantee', 'Dedicated support'],
          cta: 'Contact us',
        },
      ],
    },
    cta: {
      title: 'Bring AI agents to your entire team',
      desc: 'Let\'s discuss how Work with AI can add AI-powered productivity to your product.',
      primaryBtn: 'Talk to us',
      secondaryBtn: 'View docs',
      note: 'Free onboarding support · 14-day trial',
    },
  },
};
