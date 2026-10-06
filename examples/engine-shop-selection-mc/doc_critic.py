#!/usr/bin/env python3
"""A critic for the written results: what a document claims beyond its evidence.

The models produce numbers; the documents (results notes, handover docs, article drafts) turn
them into claims. This module reads a Markdown document and says where the claims outrun the
numbers -- the same two layers as review.py, so the critique is never empty:

  1. rules   a deterministic check list, the same for every run (what the tests cover):
               overclaim      assertive wording (決まっていた, 必ず, 明らか, 証明, ...)
               numbers        decimals in the text that no model output (fleet/*.json,
                              data/**/*.json) contains, after unit shifts (x10, x100, /10 ...)
               assumptions    a stated assumption with no source and no no_source flag
               unverified     what the document itself marks 未確認 / 未照合 (the honesty ledger)
               public         words the public repository must not carry (company names, メタ)
               structure      a limits section, the synthetic-data notice, table widths
  2. AI      Claude reads the document and the rule findings and writes the critique from five
             readers (査読者・経営者・整備計画の担当者・反対論者・初めての読者): overclaims with a
             rewrite, weak numbers, missing alternative explanations, and the five fixes in order.
             Official Anthropic SDK; with no credentials the critique is the rule layer alone
             (mode = "rules"). The same instructions are in .claude/agents/doc-critic.md for a
             Claude Code session to run without an API key.

  python doc_critic.py handover/04_docs/fleet_from_demand_結果.md --out review/doc_critic.json [--no-ai]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("REVIEW_MODEL", "claude-opus-5")
OUTPUTS = ("fleet/*.json", "data/**/*.json")

OVERCLAIM = [(r"決まっていた|決まっている|で決まる", "原因を一つに言い切っている（他の要因・制約は？）"),
             (r"必ず|確実に|間違いなく|疑いなく", "確率の話を確定で書いている"),
             (r"明らか|自明|当然", "根拠を示さずに『明らか』としている"),
             (r"証明|実証した|裏づけた", "モデルの結果を実証のように書いている"),
             (r"すべての|常に|一切|唯一", "全称の言い切り（例外は？）"),
             (r"だけで説明|しかない|ほかにない", "別の説明を排除している")]
COMPANY = r"日本航空|全日本空輸|全日空|スカイマーク|ＡＩＲＤＯ|エア・ドゥ|ソラシド|スターフライヤー|ピーチ|ジェットスター|\bJAL\b|\bANA\b"
FORBIDDEN = r"メタ認知|メタメタ|メタ"
ASSUME = r"仮定|想定|と置く|とした"
SOURCED = r"no_source|https?://|出典|原典|公開値|国交省|統計|文献|（.*\d{4}.*）"


def outputs_numbers(globs=OUTPUTS) -> dict[int, set[float]]:
    """Every number in the model outputs, as {decimals: values rounded to that many decimals}."""
    vals: dict[int, set[float]] = {d: set() for d in range(0, 7)}
    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)) and math.isfinite(x):
            for d in vals:
                vals[d].add(round(abs(float(x)), d))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for g in globs:
        for p in HERE.glob(g):
            try:
                walk(json.loads(p.read_text(encoding="utf-8")))
            except (ValueError, UnicodeDecodeError):
                continue
    return vals


def number_found(text: str, vals: dict[int, set[float]]) -> bool:
    """A decimal from the text, matched against the outputs at the precision it is shown with,
    allowing a unit shift by a power of ten (千人 -> 万人, share -> %, k$ -> 億円 is not a power
    of ten and is not matched)."""
    x = abs(float(text.replace(",", "")))
    dec = len(text.split(".")[1]) if "." in text else 0
    for p in range(-4, 5):
        dc = dec + p                                   # x / 10**p shown with dec + p decimals
        if 0 <= dc <= 6 and round(x / 10 ** p, dc) in vals[dc]:
            return True
    return False


def lines_of(md: str) -> list[tuple[int, str]]:
    out, code = [], False
    for i, ln in enumerate(md.splitlines(), 1):
        if ln.strip().startswith("```"):
            code = not code; continue
        if not code:
            out.append((i, ln))
    return out


def rules(md: str, vals: dict[int, set[float]] | None = None, public: bool = True) -> list[dict]:
    F = []
    add = lambda kind, sev, line, text, why, ask="": F.append({"kind": kind, "severity": sev, "line": line, "quote": text.strip()[:160], "why": why, "ask": ask})  # noqa: E731
    L = lines_of(md)
    for i, ln in L:
        for pat, why in OVERCLAIM:
            if re.search(pat, ln):
                add("overclaim", "中", i, ln, why, "言い切りを弱めるか、他の要因を並べる")
                break
        if re.search(ASSUME, ln) and re.search(r"\d", ln) and not re.search(SOURCED, ln):
            add("assumption", "中", i, ln, "数値を伴う仮定に出典も no_source の印もない", "出典を足すか no_source と書く")
        if re.search(r"未確認|未照合|原典を取得できず|確認できていない", ln):
            add("unverified", "情報", i, ln, "文書自身が未確認としている箇所", "確認するか、結論の重みを下げる")
        if public and re.search(COMPANY, ln):
            add("public", "高", i, ln, "公開リポジトリに実在の会社名", "A社／B社に置き換える")
        if re.search(FORBIDDEN, ln):
            add("public", "高", i, ln, "使わない語（メタ）", "言い換える")
    if vals is not None:
        miss = []
        for i, ln in L:
            if ln.lstrip().startswith("#"):
                continue
            for m in re.finditer(r"(?<![\w.])[+−-]?(\d{1,3}(?:,\d{3})+|\d+)\.\d+(?![\w.])", ln):
                s = m.group(0).lstrip("+−-")
                if not number_found(s, vals):
                    miss.append((i, s, ln))
        for i, s, ln in miss[:40]:
            add("number", "低", i, ln, f"{s} はモデルの出力（{', '.join(OUTPUTS)}）に見つからない（手計算・丸め・古い値の可能性）", "出力から引くか、計算のしかたを書く")
        if miss:
            F.append({"kind": "number_summary", "severity": "情報", "line": 0, "quote": "", "why": f"小数 {len(miss)} 個が出力に見つからない", "ask": ""})
    heads = [ln for _, ln in L if ln.startswith("#")]
    if not any(re.search(r"限界|注意|前提", h) for h in heads):
        add("structure", "高", 0, "", "限界・前提の節がない", "限界の節を足す")
    if not re.search(r"合成", md):
        add("structure", "中", 0, "", "合成データであることの断りがない", "冒頭に 1 行で断る")
    block = None
    for i, ln in L:
        if ln.startswith("|"):
            n = ln.count("|") - ln.count("\\|")
            if block is None:
                block = (i, n)
            elif n != block[1]:
                add("structure", "低", i, ln, f"表の列数が見出し（{block[1] - 1} 列）と違う", "列をそろえる")
        else:
            block = None
    return F


SYSTEM = """あなたは、航空会社の機材・整備計画のシミュレーション結果を書いた文書の批判役です。文書を壊すためではなく、主張を根拠の強さに合わせるために読みます。
五つの読み手として読む：
- 査読者：方法と仮定。結論が仮定のどこに依存しているか、感度は示されているか
- 経営者：だから何をするのか。数字は意思決定に使える粒度か、幅は示されているか
- 整備計画の担当者：現場で起きることと合うか。エンジン・工場・部品の制約が抜けていないか
- 反対論者：同じ数字を別の原因で説明できないか（例：羽田の枠ではなく運賃・機材・競合・需要の質）
- 初めての読者：用語・単位・図表が説明なしに出ていないか
与えられるのは (1) 文書の本文と (2) 規則で作った指摘表（言い過ぎの語、出力に見つからない数値、出典のない仮定、未確認の箇所）。
形式（Markdown、日本語、簡潔に）：
## 総評（3 行：いちばん強い主張、いちばん弱い根拠、全体の確からしさ）
## 言い過ぎ（最大 5 件：引用 → なぜ言い過ぎか → 直し案の文）
## 根拠の弱い数字（最大 5 件：数字 → 何に依存しているか → どう示せば強くなるか）
## 抜けている別の説明・反論（最大 5 件）
## 読み手ごとの引っかかり（五つの読み手、各 1〜2 行）
## 直す順番（5 点、番号つき、それぞれ 1 行）
禁止：メタ／メタメタ／メタ認知という語。数値の捏造（文書と指摘表にない数値を作らない）。実在の会社名・個人名を出すこと。文書の内容は合成データを含むので、その前提で読む。"""


def rules_text(F: list[dict]) -> str:
    lines = ["（規則層のみ）", ""]
    for kind, title in (("public", "公開してはいけない語"), ("overclaim", "言い過ぎの語"), ("assumption", "出典のない仮定"),
                        ("unverified", "未確認の箇所"), ("number", "出力に見つからない数値"), ("structure", "構成")):
        xs = [f for f in F if f["kind"] == kind]
        if xs:
            lines.append(f"## {title}（{len(xs)}）")
            lines += [f"- [{f['severity']}] {('L' + str(f['line']) + ' ') if f['line'] else ''}{f['why']}" + (f"：「{f['quote'][:80]}」" if f["quote"] else "") for f in xs[:15]]
            lines.append("")
    return "\n".join(lines)


def ai_critique(md: str, F: list[dict]) -> dict:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return {"mode": "rules", "reason": "no credentials (ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN unset)", "text": rules_text(F)}
    try:
        import anthropic
    except ImportError:
        return {"mode": "rules", "reason": "anthropic package not installed (pip install anthropic)", "text": rules_text(F)}
    user = "## 文書\n" + md + "\n\n## 指摘表（規則層）\n```json\n" + json.dumps(F, ensure_ascii=False) + "\n```\n\n上の形式で批判を書いてください。"
    try:
        client = anthropic.Anthropic()
        with client.messages.stream(model=MODEL, max_tokens=6000, thinking={"type": "adaptive"}, system=SYSTEM,
                                    messages=[{"role": "user", "content": user}]) as stream:
            msg = stream.get_final_message()
        text = "".join(blk.text for blk in msg.content if getattr(blk, "type", "") == "text")
        return {"mode": "ai", "model": msg.model, "text": text, "usage": {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}}
    except Exception as e:  # noqa: BLE001 - any API failure degrades to the rule layer, never to no critique
        return {"mode": "rules", "reason": f"{type(e).__name__}: {e}"[:300], "text": rules_text(F)}


def build(doc: Path, out: Path | None = None, use_ai: bool = True, public: bool = True, check_numbers: bool = True) -> dict:
    md = doc.read_text(encoding="utf-8")
    F = rules(md, outputs_numbers() if check_numbers else None, public)
    count = {}
    for f in F:
        count[f["kind"]] = count.get(f["kind"], 0) + 1
    crit = ai_critique(md, F) if use_ai else {"mode": "rules", "reason": "--no-ai", "text": rules_text(F)}
    res = {"document": str(doc), "findings": F, "count": count, "critique": crit,
           "note": "規則層は毎回同じ判定、AI 層は Claude が本文と指摘表から書く（資格情報がなければ規則層のみ）"}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("doc", type=Path)
    a.add_argument("--out", type=Path)
    a.add_argument("--md", type=Path, help="write the critique text here as Markdown")
    a.add_argument("--no-ai", action="store_true")
    a.add_argument("--private", action="store_true", help="a private draft: skip the public-repository word check")
    args = a.parse_args(argv)
    r = build(args.doc, args.out, not args.no_ai, not args.private)
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(r["critique"]["text"], encoding="utf-8")
    print(f"{args.doc}: {r['count']}, mode = {r['critique']['mode']}" + (f" ({r['critique'].get('reason')})" if r["critique"]["mode"] == "rules" else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
