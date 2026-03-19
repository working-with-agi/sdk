import type { Lang } from './ui';

export interface HeroContent {
  badge: string;
  title: string;
  titleAccent: string;
  subtitle: string;
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
      badge: 'MAGI — Multi Agent General Instrument',
      title: 'プロジェクトの知識と対話する',
      titleAccent: 'AIウィジェット',
      subtitle: 'あなたのサービスにAI対話機能を組み込むことで、ユーザーがAIと対話しながら作業を進められるようになります。Vue / React / Angular 対応の埋め込みウィジェットとして簡単に統合可能。「これをやって」と指示するだけで、AIがデータの分析からタスク実行まで自律的にこなします。',
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
      title: 'プロジェクトデータを活用するAIスキル',
      subtitle: 'Work with AI は単なるチャットボットではありません。あなたのサービスのデータを文脈として理解し、専門的な分析やタスク実行を行うAIスキルを搭載。MAGI基盤により、エージェントがタスクを自律的に計画・実行することも可能です。',
      cards: [
        { icon: 'risk', title: 'データに基づく分析', desc: 'あなたのサービスに蓄積されたデータを文脈として、AIが専門的な分析を実行。ユーザーは自然言語で問いかけるだけで洞察を得られます。' },
        { icon: 'progress', title: 'レポート自動生成', desc: '散在するデータを統合的にまとめ、レポートやサマリーを自動生成。ユーザーの定型作業を大幅に削減します。' },
        { icon: 'compare', title: 'カスタムAIスキル', desc: 'あなたのサービスに特化したAIスキルを定義可能。ドメイン知識を活かした専門的な分析や提案をユーザーに提供できます。' },
        { icon: 'action', title: 'アクション提案と実行', desc: 'データの文脈から次にやるべきアクションを提案。承認フロー付きで、AIが実際のタスク実行まで支援します。' },
        { icon: 'timeline', title: 'エージェント自律実行', desc: 'MAGI基盤によるエージェントモード。ユーザーが「これをやって」と指示するだけで、AIがデータの収集・分析・レポート作成まで一貫して自律的に遂行します。' },
        { icon: 'chat', title: 'MCP連携', desc: 'Model Context Protocol対応。外部ツールやAPIに直接アクセスし、エージェントの能力を拡張。あなたのサービスのエコシステムと統合できます。' },
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
      subtitle: 'Vue / React / Angular 対応。数行のコードでプロダクトにAIエージェントターミナルを埋め込めます。AgentServer（AetherTerm）がバックエンドのセッション管理を担当します。',
      steps: [
        { step: '01', title: 'パッケージをインストール', desc: 'npm でウィジェットパッケージをインストール。xterm.js ベースのターミナルUIが含まれます。' },
        { step: '02', title: 'AgentServerに接続', desc: 'AgentServer（AetherTerm）のURLを指定。APIキーとスキル・コンテキストを設定します。' },
        { step: '03', title: 'ターミナルを配置', desc: 'コンポーネントを配置するだけ。ユーザーはターミナル上でAIエージェントと対話できます。' },
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
        { question: 'チャットボットとどう違うのですか？', answer: 'チャットボットは質問に答えるだけですが、Work with AI のAIエージェントは自律的にタスクを計画・実行します。「レポートを作って」と指示すれば、データ収集から構成・生成まで一貫して遂行。作業過程が見え、途中で方向修正もできます。AIに仕事を「やってもらう」体験がMAGI（Multi Agent General Instrument）のコンセプトです。' },
        { question: 'どのようなデータにアクセスしますか？', answer: 'Secretary.io に蓄積された会議議事録、タスク、プロジェクト構造にアクセスします。MCP（Model Context Protocol）経由でLinear、Jira、Google Calendarなどの外部ツールにも接続可能です。テナントごとにデータは完全に分離されています。' },
        { question: 'エージェントは勝手に操作を実行しますか？', answer: 'いいえ。破壊的な操作（チケット作成、データ更新など）は承認フローを経由します。分析やレポート生成は自律的に実行しますが、外部への書き込みはユーザーの確認を待ちます。' },
        { question: '導入は簡単ですか？', answer: 'はい。npm パッケージをインストールし、AgentServerのURLとAPIキーを設定するだけです。UIはxterm.jsベースのターミナルとして提供され、最短5分で動作します。' },
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
      badge: 'MAGI — Multi Agent General Instrument',
      title: 'Add AI to your service,',
      titleAccent: 'let users work with it',
      subtitle: 'Embed AI conversation into your service so users can work alongside AI to get things done. An embeddable widget for Vue / React / Angular. Just say "do this" and the AI agent handles data analysis, report generation, and task execution autonomously.',
      ctaPrimary: 'Try the Demo',
      ctaSecondary: 'Integration Guide',
      stat1Value: '5 min',
      stat1Label: 'Setup time',
      stat2Value: 'MAGI',
      stat2Label: 'Agent platform',
      stat3Value: 'Autonomous',
      stat3Label: 'Not just chat',
    },
    features: {
      eyebrow: 'Capabilities',
      title: 'Not a chatbot. An AI agent.',
      subtitle: 'Work with AI is not a chatbot that answers questions. It is an AI agent that understands project context and autonomously plans and executes tasks.',
      cards: [
        { icon: 'risk', title: 'Autonomous Risk Detection', desc: 'Without being asked, the agent proactively detects risks from meeting data and task delays, presenting severity levels and mitigation plans.' },
        { icon: 'progress', title: 'Auto-Generated Reports', desc: 'The agent cross-analyzes project data and autonomously composes and generates stakeholder progress reports.' },
        { icon: 'action', title: 'Task Planning & Execution', desc: 'Understands incomplete tasks and discussion context, plans next actions, and upon approval, creates tickets and updates documents.' },
        { icon: 'compare', title: 'Cross-Project Analysis', desc: 'Integrates data across multiple projects, autonomously identifying common issues and propagating best practices.' },
        { icon: 'timeline', title: 'Interactive Dialogue', desc: 'Converse with the agent in natural language on the terminal. Even vague instructions are interpreted from context, with work progressing step by step.' },
        { icon: 'chat', title: 'MCP Integration', desc: 'Access project management tools, calendars, and ticket systems directly via Model Context Protocol. Extend the tools available to the agent.' },
      ],
    },
    demo: {
      eyebrow: 'Live Demo',
      title: 'Experience the AI agent in action',
      subtitle: 'See how the AI agent accesses project data on a terminal and autonomously executes tasks.',
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
      subtitle: 'Supports Vue / React / Angular. Embed an AI agent terminal in your product with a few lines of code. AgentServer (AetherTerm) handles backend session management.',
      steps: [
        { step: '01', title: 'Install the package', desc: 'Install via npm. Includes an xterm.js-based terminal UI.' },
        { step: '02', title: 'Connect to AgentServer', desc: 'Point to your AgentServer (AetherTerm) URL. Configure API key, skills, and context.' },
        { step: '03', title: 'Place the terminal', desc: 'Drop in the component. Users interact with the AI agent directly on the terminal.' },
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
        { question: 'How is this different from a chatbot?', answer: 'Chatbots only answer questions. Work with AI agents autonomously plan and execute tasks. Say "create a report" and the agent collects data, structures it, and generates the output. You can see the work process and redirect at any point. MAGI (Multi Agent General Instrument) is the concept of letting AI do the work for you.' },
        { question: 'What data does it access?', answer: 'Meeting minutes, tasks, and project structure stored in Secretary.io. Via MCP (Model Context Protocol), it can also connect to Linear, Jira, Google Calendar, and other tools. Data is completely isolated per tenant.' },
        { question: 'Does the agent execute actions without permission?', answer: 'No. Destructive operations (ticket creation, data updates) go through an approval flow. Analysis and report generation run autonomously, but writes to external systems wait for user confirmation.' },
        { question: 'Is it easy to integrate?', answer: 'Yes. Install the npm package, set the AgentServer URL and API key. The UI is an xterm.js terminal — up and running in 5 minutes.' },
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
