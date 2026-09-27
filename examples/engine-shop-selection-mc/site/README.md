# レポートを Cloudflare に公開する

`handover/03_reports/` の HTML（自己完結、外部依存なし）を Cloudflare Workers の静的アセットとして配信する。

```bash
cd examples/engine-shop-selection-mc/site
mkdir -p public && cp ../handover/03_reports/*.html public/   # index.html＝ダッシュボード、report/monthly/annual/track、文書の HTML
export CLOUDFLARE_API_TOKEN=...   # Workers Scripts:Edit の権限
export CLOUDFLARE_ACCOUNT_ID=...
npx wrangler@latest deploy         # → https://engine-plan-report.<account>.workers.dev/
```

- 公開 URL は誰でも見られる。社外秘の数値を載せる前に Cloudflare Access で認証を掛ける（Zero Trust → Access → Applications → workers.dev のホスト名）。
- 更新は同じコマンドを再実行するだけ。`public/` は生成物なので Git には入れない。
