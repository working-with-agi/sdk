#!/usr/bin/env python3
"""Figures of the planning structure: two pages, drawn as SVG so the report can embed them.

  P1 基本計画 (annual to half-year, PDCA): assumptions -> solve -> levers and purchase -> verify
  P2 詳細計画 (monthly to daily, OODA):     actuals -> watch and track -> weekly -> same day

Both pages share the six business-process rows. Frames mark the loops (tab = name, count,
condition), badges the inner repetition of a box, teal tags the hand-over between the pages.
All counts are the synthetic JAL case (see REQUIREMENTS #101-#102).

  python figures.py --out-dir out      # writes plan_basic.html and plan_detail.html
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# palette
BG="#fbfbfd"; ROWA="#ffffff"; ROWB="#f1f3f8"; HEAD="#1e293b"; INK="#0f172a"; MUTE="#64748b"; LINE="#334155"
COL={"mc":("#e0e7ff","#4338ca"),"det":("#d1fae5","#047857"),"judge":("#fef3c7","#b45309")}
PDCA="#475569"; OODA="#0f766e"; LOOP="#be123c"; LOOPF="rgba(190,18,60,0.06)"; INNER="#4338ca"; INNERF="rgba(67,56,202,0.08)"; PORT="#0e7490"
def tw(s,size): return sum(size*0.98 if ord(c)>255 else size*0.58 for c in s)
class Page:
    def __init__(s,W,H,title,tag,tagcol,sub,cols,rows):
        s.W,s.H,s.cols,s.rows=W,H,cols,rows; s.title=title; s.L=232; s.T=130; s.cw=(W-s.L-20)/len(cols); s.rh=(H-s.T-176)/len(rows)
        s.o=[f'<rect width="{W}" height="{H}" fill="{BG}"/>',f'<defs><marker id="ah" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{LINE}"/></marker><marker id="ar" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{LOOP}"/></marker></defs>']
        bw=tw(tag,12)+18
        s.o.append(f'<rect x="20" y="16" width="{bw}" height="24" rx="6" fill="{tagcol}"/><text x="{20+bw/2}" y="33" font-size="12" font-weight="700" fill="#fff" text-anchor="middle">{tag}</text>')
        s.o.append(f'<text x="{28+bw}" y="35" font-size="21" font-weight="700" fill="{INK}">{title}</text>')
        s.o.append(f'<text x="20" y="60" font-size="12" fill="{MUTE}">{sub}</text>')
        for j,c in enumerate(cols):
            x=s.L+j*s.cw; title,stage,scol=c
            s.o.append(f'<rect x="{x}" y="{s.T-56}" width="{s.cw-4}" height="46" rx="6" fill="{HEAD}"/><text x="{x+s.cw/2}" y="{s.T-37}" text-anchor="middle" font-size="12" fill="#fff" font-weight="700">{title}</text>')
            bw=tw(stage,10.5)+16; s.o.append(f'<rect x="{x+s.cw/2-bw/2}" y="{s.T-30}" width="{bw}" height="16" rx="8" fill="{scol}"/><text x="{x+s.cw/2}" y="{s.T-18}" text-anchor="middle" font-size="10.5" fill="#fff" font-weight="700">{stage}</text>')
        for i,r in enumerate(rows):
            y=s.T+i*s.rh; s.o.append(f'<rect x="20" y="{y}" width="{W-40}" height="{s.rh-4}" fill="{ROWA if i%2==0 else ROWB}" stroke="#e2e8f0"/><text x="30" y="{y+s.rh/2}" font-size="12" font-weight="700" fill="{INK}">{r}</text>')
        s.boxes={}; s.BOX=[]; s.BADGE=[]; s.FR=[]; s.TAB=[]; s.AR=[]; s.RET=[]; s.PORTS=[]
    def box(s,key,col,row,slot,label,l1,l2,kind,rep=None):
        x=s.L+col*s.cw+8; y=s.T+row*s.rh+12+slot*84; w=s.cw-20; h=60; f,st=COL[kind]
        s.boxes[key]=(x,y,w,h)
        s.BOX.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{f}" stroke="{st}" stroke-width="1.5"/><text x="{x+9}" y="{y+17}" font-size="12" font-weight="700" fill="{INK}">{label}</text><text x="{x+9}" y="{y+34}" font-size="10.5" fill="{INK}">{l1}</text><text x="{x+9}" y="{y+50}" font-size="10.5" fill="{MUTE}">{l2}</text>')
        if rep:
            bw=tw(rep,10.5)+14; s.BADGE.append(f'<rect x="{x+w-bw-5}" y="{y+h+2}" width="{bw}" height="17" rx="8" fill="{LOOP}"/><text x="{x+w-bw/2-5}" y="{y+h+14}" font-size="10.5" font-weight="700" fill="#fff" text-anchor="middle">{rep}</text>')
    def frame(s,keys,tab,pad=8,inner=False,stage=None):
        b=[s.boxes[k] for k in keys]; x=min(v[0] for v in b)-pad; y=min(v[1] for v in b)-pad; x2=max(v[0]+v[2] for v in b)+pad; y2=max(v[1]+v[3] for v in b)+pad+14
        st,fl,da=(INNER,INNERF,"2 2") if inner else (LOOP,LOOPF,"7 4")
        s.FR.append(f'<rect x="{x}" y="{y}" width="{x2-x}" height="{y2-y}" rx="10" fill="{fl}" stroke="{st}" stroke-width="2" stroke-dasharray="{da}"/>')
        bw=tw(tab,11)+16; s.TAB.append(f'<rect x="{x+6}" y="{y-10}" width="{bw}" height="19" rx="5" fill="{st}"/><text x="{x+14}" y="{y+3}" font-size="11" font-weight="700" fill="#fff">{tab}</text>')
        if stage: s.stagepill(x+6+bw+4,y-10,stage)
        return (x,y,x2,y2)
    def stagepill(s,x,y,stage):
        txt,col=stage; bw=tw(txt,10.5)+14
        s.TAB.append(f'<rect x="{x}" y="{y}" width="{bw}" height="19" rx="5" fill="#fff" stroke="{col}" stroke-width="1.5"/><text x="{x+bw/2}" y="{y+13}" font-size="10.5" font-weight="700" fill="{col}" text-anchor="middle">{txt}</text>')
    def frame_rect(s,x,y,x2,y2,tab,stroke=LOOP,fill="none",dash="10 5",stage=None):
        s.FR.append(f'<rect x="{x}" y="{y}" width="{x2-x}" height="{y2-y}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2.5" stroke-dasharray="{dash}"/>')
        bw=tw(tab,11)+16; s.TAB.append(f'<rect x="{x+8}" y="{y-10}" width="{bw}" height="19" rx="5" fill="{stroke}"/><text x="{x+16}" y="{y+3}" font-size="11" font-weight="700" fill="#fff">{tab}</text>')
        if stage: s.stagepill(x+8+bw+4,y-10,stage)
    def arrow(s,a,b,col=LINE,dash=False,w=1.6,mk="ah"):
        x1,y1,w1,h1=s.boxes[a]; x2,y2,w2,h2=s.boxes[b]; d=' stroke-dasharray="5 4"' if dash else ''
        if abs(x2-x1)<10:
            sx=x1+w1*0.5; sy=y1+h1 if y2>y1 else y1; ey=y2 if y2>y1 else y2+h2; pts=f"{sx},{sy} {sx},{ey}"
        elif x2>x1:
            sx,sy=x1+w1,y1+h1/2; ex,ey=x2,y2+h2/2; gx=x1+w1+6; pts=f"{sx},{sy} {gx},{sy} {gx},{ey} {ex},{ey}"
        else:
            sx,sy=x1,y1+h1/2; ex,ey=x2+w2,y2+h2/2; gx=x1-6; pts=f"{sx},{sy} {gx},{sy} {gx},{ey} {ex},{ey}"
        s.AR.append(f'<polyline fill="none" points="{pts}" stroke="{col}" stroke-width="{w}"{d} marker-end="url(#{mk})" opacity=".85"/>')
    def ret(s,pts): s.RET.append(f'<polyline fill="none" points="{pts}" stroke="{LOOP}" stroke-width="2.6" marker-end="url(#ar)"/>')
    def port(s,key,text,side,dy=0,dx=0):
        x,y,w,h=s.boxes[key]; bw=tw(text,10.5)+14
        px=x+6+dx; py=y+h+2+dy
        s.PORTS.append(f'<rect x="{px}" y="{py}" width="{bw}" height="17" rx="4" fill="{PORT}"/><text x="{px+bw/2}" y="{py+12}" font-size="10.5" font-weight="700" fill="#fff" text-anchor="middle">{text}</text>')
    def legend(s,items):
        y0=s.H-152
        for k,(n,t,c) in enumerate(items):
            y=y0+k*18; s.o.append(f'<rect x="20" y="{y-12}" width="52" height="16" rx="4" fill="{c}"/><text x="46" y="{y}" font-size="10.5" font-weight="700" fill="#fff" text-anchor="middle">{n}</text><text x="80" y="{y}" font-size="11.5" fill="{INK}">{t}</text>')
    def svg(s):
        o=s.o+s.FR+s.AR+s.RET+s.BOX+s.BADGE+s.TAB+s.PORTS
        body="".join(o)
        # text styling as inline style so a host page's stylesheet cannot override it
        def fix(m):
            tag=m.group(0); st=[]
            for k in ("fill","font-size","font-weight"):
                mm=re.search(rf' {k}="([^"]*)"',tag)
                if mm: st.append(f"{k}:{mm.group(1)}{'px' if k == 'font-size' else ''}"); tag=tag.replace(mm.group(0),"")
            return tag[:-1]+f' style="{";".join(st)};font-family:IBM Plex Sans JP,Noto Sans JP,sans-serif">' if st else tag
        body=re.sub(r"<text[^>]*>",fix,body)
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s.W} {s.H}" role="img" aria-label="{s.title}" font-family="IBM Plex Sans JP, sans-serif">'+body+'</svg>'
ROWS=["経営（承認・投資）","整備計画（計画・追跡）","調達・契約（工場・部品・購入）","運航・機材（便の計画・退役）","技術（状態・劣化）","財務（予算・税・資産）"]


def plan_basic() -> str:
    """P1: the basic plan, yearly to half-yearly (PDCA)."""

    p=Page(1400,1470,"基本計画：年に 1 回、20 年先まで見て版を作る（年次〜半期）","P1 基本計画","#4338ca",
     "左から右へ：前提を作る → 基本計画を解く → 打ち手と購入を決める → 半期で確かめる。藍＝確率計画・モンテカルロ、青緑＝決定論・式、琥珀＝判定。深紅の枠＝繰り返し（タブに回数と条件）、藍の点線枠＝内側の 1 回。青緑の札＝詳細計画（P2）との接続。",
     [("① 前提を作る（年 1 回）","PDCA：Plan",PDCA),("② 基本計画を解く（年 1 回・約 4 分）","PDCA：Plan",PDCA),("③ 打ち手と購入（年 1 回・約 1 分）","PDCA：Plan → Do（承認）",PDCA),("④ 半期・四半期で確かめる","PDCA：Check → Act",PDCA)],ROWS)
    p.box("approve",2,0,0,"版の承認（判断ルーム）","購入計画・打ち手・投資案を見て決める","承認／保留／差し戻し。計算なし","judge")
    p.box("invest",2,0,1,"国内工場の新設・段階投資（invest）","3 案を NPV と実物オプションで比べる","案ごとに基本計画を解いて叩く","mc","3 案 × MC 800 本")
    p.box("life",0,1,0,"20 年の履歴（lifecycle）","240 か月を全エンジンで回し、最初の 5 年は捨てる","平年値と、今日の機材状態（残り時間・部品）","det")
    p.box("worlds",1,1,0,"世界と重み（基準・逼迫・…）","世界 5 つ。追跡の事後確率で重みづけ","逼迫＝キット納期 12 か月・手持ち半減","det")
    p.box("freeze",1,1,1,"基準計画の凍結（baseline）","解く：MILP 40 本のシナリオを同時に見て 1 計画","叩く：その計画を MC 800 本 × 24 か月で評価","mc")
    p.box("runout",3,1,0,"退役までの入場列（runout）","決定論。退役順 3 通り（期限順・古い順・乱数）","空の年が出る理由（退役が入場を吸う）を注釈","det","退役順 3 通り")
    p.box("backtest",3,1,1,"過去で検証（backtest）","8 版を過去に当て、学ぶ 5 版／確かめる 5 版","入場時期 +1.5 か月、被覆率 78%（合成）","mc","版 8 × 世界 2")
    p.box("contract",0,2,0,"見積・契約の条件","工場ごとの価格・TAT・所見折半・キット納期","Knowledge Hub から取り込む","det")
    p.box("purchase",1,2,0,"購入計画の輪（purchase_loop）","候補 4（予備・購入・プール・中寿命）を順に試す","欠航 1 点あたり最も安い 1 手を足す","mc","候補 4 × 内側 1 回")
    p.box("levers",2,2,0,"打ち手の値付け（compare）","手 6 つを保険料 × 払い戻しで値付け","基準計画を手ごとに解き直す","mc","手 6 × 内側 1 回")
    p.box("playbook",2,2,1,"打ち手の順番（playbook）","キット → 契約 → 第二工場の順に効く","世界 3 つで順番が変わらないか見る","mc","手 4 × 世界 3")
    p.box("shopresp",3,2,0,"工場の容量反応（shop_response）","約束件数（年 20 件）を割ると増強が止まる","購入計画で入場が減るときの読み返し","det")
    p.box("demand",0,3,0,"客席の需要（demand）","e-Stat 月次・逼迫月・余力の客席換算","市場 A、社別 A／B、上限 C","det","月次 × 3 社")
    p.box("p2d",0,3,1,"需要から前提へ（plan_from_demand）","季節指数・伸び（短期／長期）・稼働上限 1.10","年 1 回、伸び差 3pt で随時","det")
    p.box("flights",1,3,0,"便の計画 → 必要エンジン数","便の計画が「必要」を決める（航空計画に合わせる）","置き換えの受領遅れは退役ペースの引き金","det")
    p.box("growth",3,3,0,"足す計画（growth_plan）","需要の余地 × エンジンの余力 → 足せる便数","半期に見直す","det")
    p.box("wear",0,4,0,"劣化率・寿命部品（wear）","窓の物理。個体差の係数","入場までの回数＝翼上寿命 ÷ 窓","det")
    p.box("typelife",0,4,1,"型式の時計（typelife）","CFM56-7B 晩年：残存価値の減衰、中古の供給","2 年で 4 基が上限（仮定）","det")
    p.box("tax",0,5,0,"税引後・お金の仕組み（tax／finance）","式。購入かリースかは税引後 5 年で見る","資本費 7%＋償却 5%（仮定）","det")
    p.box("mx4",0,5,1,"積立金と機体価値（mx4）","資産側。予備の追加は退役時の残価を変える","半減期で残価","det")
    p.box("budget",1,5,0,"年度の着地（landing）","p10〜p90・予算超過確率","基本計画の MC 800 本から","mc","MC 800 本")
    fI=p.frame(["worlds","freeze"],"内側：解いて叩く 1 回（約 1.5 秒）",6,True)
    fA=p.frame(["purchase"],"A 購入の輪 ×4（AOG 5% まで・内側 32 回）",stage=("Plan の中の小さな輪",PDCA))
    fD=p.frame(["demand","p2d"],"D 需要の見直し 年 1 回（3pt で随時）",stage=("Check → Plan",PDCA))
    fF=p.frame_rect(p.L-2,p.T+2,p.L+3*p.cw-8,p.T+6*p.rh-8,"F 年次の版の輪 年 1 回（前提 → 解く → 打ち手 → 承認。差し戻しなら解き直す）",stage=("PDCA の本体：Plan → Do",PDCA))
    fG=p.frame_rect(p.L+3*p.cw+2,p.T+p.rh+2,p.L+4*p.cw-6,p.T+4*p.rh-8,"G 半期の輪 年 2 回",stage=("PDCA：Check → Act",PDCA))
    for a,b in [("life","worlds"),("p2d","flights"),("flights","freeze"),("wear","freeze"),("contract","purchase"),("typelife","runout"),("freeze","runout"),("freeze","backtest"),("freeze","levers"),("levers","playbook"),("runout","growth"),("freeze","budget"),("tax","budget"),("mx4","budget"),("invest","approve"),("shopresp","purchase")]:
        p.arrow(a,b)
    p.arrow("levers","invest",LINE,True)
    # A loop: purchase -> inner frame (left gutter of col1)
    x,y,w,h=p.boxes["purchase"]; gx=fI[0]-14
    p.ret(f"{fA[0]},{y+h*0.75} {gx},{y+h*0.75} {gx},{fI[1]+(fI[3]-fI[1])*0.5} {fI[0]},{fI[1]+(fI[3]-fI[1])*0.5}")
    ly=(y+h*0.75+fI[1]+(fI[3]-fI[1])*0.5)/2; p.RET.append(f'<text x="{gx-6}" y="{ly}" font-size="11" font-weight="700" fill="{LOOP}" text-anchor="middle" transform="rotate(-90 {gx-6} {ly})">A：次の手へ</text>')
    # F: approve -> freeze (差し戻し), via the gutter left of column 3
    ax,ay,aw,ah=p.boxes["approve"]; fx,fy,fw,fh=p.boxes["freeze"]; wx,wy,ww,wh=p.boxes["worlds"]; gx=p.L+2*p.cw-6
    p.ret(f"{ax},{ay+ah*0.8} {gx},{ay+ah*0.8} {gx},{fy+fh*0.8} {fI[2]},{fy+fh*0.8}")
    p.RET.append(f'<text x="{gx+10}" y="{wy+wh*0.5}" font-size="11" font-weight="700" fill="{LOOP}" text-anchor="middle" transform="rotate(-90 {gx+10} {wy+wh*0.5})">F：差し戻し → 解き直す</text>')
    # G: backtest -> worlds (補正を入れて次の版), growth -> flights (足す計画が必要を変える)
    bx,by,bw_,bh=p.boxes["backtest"]; wx,wy,ww,wh=p.boxes["worlds"]; gx2=p.L+3*p.cw-30
    p.ret(f"{bx},{by+bh*0.8} {gx2},{by+bh*0.8} {gx2},{wy+wh*0.8} {fI[2]},{wy+wh*0.8}")
    p.RET.append(f'<text x="{(gx2+fI[2])/2}" y="{wy+wh*0.8-6}" font-size="11" font-weight="700" fill="{LOOP}" text-anchor="middle">G：補正を入れて次の版</text>')
    gx_,gy_,gw_,gh_=p.boxes["growth"]; flx,fly,flw,flh=p.boxes["flights"]
    p.ret(f"{gx_},{gy_+gh_*0.8} {flx+flw},{gy_+gh_*0.8}")
    p.RET.append(f'<text x="{(gx_+flx+flw)/2}" y="{gy_+gh_*0.8-6}" font-size="11" font-weight="700" fill="{LOOP}" text-anchor="middle">G：足す計画が「必要」を変えたら解き直す</text>')
    p.port("life","← P2 実績（Observe）で今日の状態へ","left")
    p.port("worlds","← P2 変化点で世界を足す","left",0,92)
    p.port("wear","← P2 劣化率・計画外率の実績","left")
    p.port("flights","← P2 便の実績","left")
    p.port("contract","← P2 回答ログ（納期）","left")
    p.port("freeze","→ P2 追跡へ","right")
    p.port("worlds","← P2 学習","right")
    p.port("purchase","← P2 見張り","right")
    p.port("budget","→ P2 月次更新","right")
    p.legend([("内側","解いて叩く 1 回：MILP 40 本を同時に解き、その計画を MC 800 本 × 24 か月で叩く。世界 2 つ分を確率で混ぜる。約 1.5 秒。",INNER),
    ("A","購入の輪：候補 4 つそれぞれで内側を回し、AOG 1 点あたり最も安い手を 1 つ足す。5% を切るまで 4 回 ＝ 内側 32 回・約 50 秒。",LOOP),
    ("D","需要の見直し：年 1 回。過去の伸び（短期／長期）の差が 3pt を超えたら随時。前提が変わるので基本計画を解き直す。",LOOP),
    ("F","年次の版の輪：前提 → 解く（世界 5 × 内側 ≒ 4 分）→ 打ち手と購入 → 承認。差し戻しなら前提を直して解き直す（年 1 回、差し戻しは 1〜2 回が感覚値）。",LOOP),
    ("G","半期の輪：退役までの入場列と過去での検証で版を確かめ、補正（入場時期・計画外率・据置確率）を入れて次の版へ。足す計画が「必要」を変えたら解き直す（年 2 回）。",LOOP),
    ("PDCA","このページは PDCA。Plan＝前提・解く・打ち手（①〜③）、Do＝承認と実行、Check＝半期の検証（④）、Act＝補正して次の版。見直し（review）は症状をこの 4 段に振り分ける。",PDCA),
    ("OODA→P","OODA の出力が Plan の入力：Observe（実績・回答ログ・便の実績）は ① の前提に、Orient（事後確率・変化点・補正）は ② の世界と重みに入る。青緑の札 ← P2 がその口。",OODA),
    ("P2 接続","詳細計画（月次〜当日）との受け渡し。基準計画は追跡へ渡り、学習と見張りの結果がここへ戻る。すべて合成データの目安。",PORT)])
    return p.svg()


def plan_detail() -> str:
    """P2: the detailed plan, monthly to daily (OODA)."""

    q=Page(1400,1470,"詳細計画：月ごとに実績を入れて基本計画を補正する（月次〜当日）","P2 詳細計画","#047857",
     "左から右へ：実績を入れる → 見張りと追跡で補正する → 週次の先行指標 → 当日はルールで動く。色と枠は P1 と同じ。青緑の札＝基本計画（P1）との接続。",
     [("① 実績を入れる（月 1 回）","OODA：Observe",OODA),("② 見張りと追跡（月 1 回・数十秒）","OODA：Orient → Decide",OODA),("③ 週次（先行指標）","OODA：Observe → Orient",OODA),("④ 当日〜数日（計算なし）","OODA：Decide → Act",OODA)],ROWS)
    q.box("facts",0,0,0,"月次の判断材料（fact pack）","入場・遅れ・所見・故障・費用の実績を集める","Secretary.io が会議前に整える","det")
    q.box("review",1,0,0,"PDCA／OODA の見直し（review）","症状表 → 段階（P/D/C/A・O/O/D/A）に振り分け","前提の見直し期限が来ていれば知らせる","judge","月 1 回 ＝ 年 12")
    q.box("approve",3,0,0,"承認（判断ルーム）","承認／保留／差し戻し。承認線 v を超えた提案だけ","計算なし","judge")
    q.box("progress",0,1,0,"計画との差（planned vs actual）","入場月・整備範囲・費用の差分","差が続けば追跡の重みに効く","det")
    q.box("track",1,1,0,"追跡・確率の更新（track）","1. 世界 5 の事後確率を更新（γ=0.5 で緩める）","2. ΔV を出し 3. ヒステリシス K=300 k$／2 か月","mc","世界 5 × 内側 1 回")
    q.box("roll",1,1,1,"次の版への学習（roll）","実績の重み n/(n+K)。変化点なら古い分を捨てる","入場時期・計画外率・据置確率を補正","det","年 1 回")
    q.box("cpd",2,1,0,"変化点検知（cpd）","BOCPD・CUSUM で納期回答の流れを見張る","検知したら「観測世界」を足す","judge","週 1 回 ＝ 年 52")
    q.box("ooda",3,1,0,"暗黙のルール（ooda）","承認線 v・警報・戻り遅れ。その場で判断","毎日、計算なし","judge","毎日")
    q.box("leaseterms",0,2,0,"短期リースの条件","価格・上限・納期（仮定）","見張りの手当ての単価","det")
    q.box("shortage",1,2,0,"不足の見張り（shortage）","在庫機の遅れ・予定入場・故障を 6 か月先まで引く","3 か月先 AOG > 5% → 短期リース → P1 の輪へ","mc","MC 4,000 本 × 6 か月")
    q.box("kits",2,2,0,"キット納期の回答ログ","工場・部品の回答を週次で記録","変化点の入力","judge")
    q.box("lease",3,2,0,"短期リース・代替運航","ルールで当日。上限まで積む","それでも足りなければ欠航","judge")
    q.box("delivery",0,3,0,"受領の見通し（納期回答）","置き換え機の受領遅れ（知っていれば 142 M$ の差）","退役ペースの引き金","judge")
    q.box("flightsact",0,3,1,"便の実績（稼働率）","必要エンジン数の再計算","便の変更は「必要」を動かす","det")
    q.box("reqeng",1,3,0,"必要エンジン数の更新","便の実績 × 稼働 → 必要 − 稼働可能 − 予備","見張りの入力","det")
    q.box("cm",2,3,0,"状態監視（EGT・便ごと）","警報の入力。便ごとに更新","計画外取卸しの前兆","judge","便ごと")
    q.box("unsched",0,4,0,"計画外取卸しの率","実績で更新（月 0.4%／基 が前提）","学習の入力","det")
    q.box("wearact",1,4,0,"劣化率の実績","窓の消費が前提とずれていないか","ずれが続けば次の版へ","det")
    q.box("spend",0,5,0,"月次の支出実績","入場費・所見・リース・欠航","着地の入力","det")
    q.box("budget",1,5,0,"年度の着地の更新（landing）","p10〜p90・予算超過確率を月次で引き直す","MC 800 本","mc","MC 800 本")
    fE=q.frame(["review","approve"],"E 月次の輪 月 1 回",stage=("PDCA の Check → Act と OODA の Decide をつなぐ",PDCA))
    fC=q.frame(["track","roll"],"C 年次の輪 年 1 回",stage=("Orient → PDCA の Act へ",OODA))
    fB=q.frame(["shortage"],"B 見張り 月 1 回（AOG > 5% → P1）",stage=("Orient → Decide",OODA))
    fW=q.frame(["cpd","kits"],"週次 週 1 回",stage=("Observe → Orient",OODA))
    fO=q.frame(["ooda","lease"],"当日 毎日",stage=("Decide → Act",OODA))
    for a,b in [("facts","review"),("progress","track"),("track","roll"),("cpd","track"),("kits","cpd"),("cm","ooda"),("track","ooda"),("track","review"),("leaseterms","shortage"),("reqeng","shortage"),("flightsact","reqeng"),("delivery","reqeng"),("unsched","roll"),("wearact","roll"),("spend","budget"),("shortage","budget")]:
        q.arrow(a,b)
    for a,b in [("review","approve"),("shortage","lease"),("ooda","approve")]: q.arrow(a,b,"#b45309",True)
    x,y,w,h=q.boxes["review"]; q.ret(f"{x+w*0.25},{fE[3]} {x+w*0.25},{fC[1]}")
    q.port("facts","→ P1 前提へ（年 1 回）","left")
    q.port("unsched","→ P1 劣化の前提へ","left")
    q.port("wearact","→ P1 劣化の前提へ","left")
    q.port("flightsact","→ P1 便の計画へ","left")
    q.port("kits","→ P1 契約条件へ","left")
    q.port("cpd","→ P1 世界を足す","left")
    q.port("track","← P1 基準計画","left")
    q.port("roll","→ P1 次の版","right")
    q.port("shortage","→ P1 購入の輪","right")
    q.port("budget","← P1 着地","right")
    q.legend([("E","月次の輪：判断材料 → 見直し → 承認 → 追跡。人の判断の輪で、計算は数十秒。",LOOP),
    ("C","年次の輪：追跡の事後確率と実績の重みで前提を補正し、P1 の「世界と重み」へ戻す（年 1 回、過去 8 版で検証済み）。",LOOP),
    ("B","見張り：月 1 回、在庫の機の遅れ・予定入場・故障を 4,000 本で引く。3 か月先 AOG > 5% なら短期リースを積み、年次を待たずに P1 の購入の輪を回す。",LOOP),
    ("週次／当日","週次は先行指標（納期回答の変化点）だけを計算し、当日はルール（承認線・警報・上限）で動く。感覚値：月次の補正は ±1〜2 基の予備と 1〜2 件の入場前後。",HEAD),
    ("OODA","このページは OODA。Observe＝実績・回答ログ・状態監視、Orient＝追跡・変化点・見張り、Decide＝承認線 v と承認、Act＝短期リース・代替運航。月次の見直しは PDCA の Check → Act と OODA の Decide を一つの板でつなぐ。",OODA),
    ("O→PDCA","OODA の出力が PDCA の入力：ここで観測し整えたもの（→ P1 の札）は年 1 回の版で ① 前提と ② 世界の入力になる。逆に PDCA の Plan（基準計画）が Orient の入力。二つの輪は互いの入力。",PDCA),
    ("P1 接続","基本計画（年次〜半期）との受け渡し。基準計画を受け取り、学習と見張りの結果を返す。乱数の種 5 つで AOG ±1pt。すべて合成データの目安。",PORT)])
    return q.svg()


LOOPS = [  # name, cadence, count, condition, stage, page, report view
    ("内側", "解いて叩く 1 回", "世界 2 ×（MILP 40 本 → MC 800 本 × 24 か月）≈ 1.5 秒", "基準計画 1 回ごと", "Plan の中身", "P1", "budget"),
    ("A", "購入の輪", "候補 4 × 4 手 ＝ 内側 32 回 ≈ 50 秒", "AOG が 5% を切るまで 1 手ずつ", "Plan の中の小さな輪", "P1", "playbook"),
    ("D", "需要の見直し", "年 1 回", "伸びの差が 3pt を超えたら随時", "Check → Plan", "P1", "demand"),
    ("F", "年次の版の輪", "年 1 回（世界 5 × 内側 ≈ 4 分）", "承認まで。差し戻しなら前提を直して解き直す（1〜2 回が感覚値）", "PDCA の本体：Plan → Do", "P1", "budget"),
    ("G", "半期の輪", "年 2 回", "退役までの入場列・過去での検証で補正し次の版へ。足す計画が「必要」を変えたら解き直す", "Check → Act", "P1", "backtest"),
    ("E", "月次の輪", "月 1 回（計算は数十秒）", "判断材料 → 見直し → 承認 → 追跡", "PDCA の Check → Act と OODA の Decide をつなぐ", "P2", "review"),
    ("C", "年次の輪（学習）", "年 1 回", "追跡の事後確率と実績の重みで前提を補正し P1 の世界と重みへ", "Orient → PDCA の Act へ", "P2", "roll"),
    ("B", "見張り", "月 1 回（MC 4,000 本 × 6 か月）", "3 か月先の AOG > 5% なら短期リースを積み、年次を待たずに P1 の購入の輪へ", "Orient → Decide", "P2", "track"),
    ("週次", "先行指標", "週 1 回 ＝ 年 52", "納期回答のログ → 変化点検知 → 追跡へ", "Observe → Orient", "P2", "cpd"),
    ("当日", "暗黙のルール", "毎日（計算なし）", "承認線 v・警報・上限で動く。短期リース・代替運航", "Decide → Act", "P2", "loops"),
]
HANDOVER = [  # what crosses between the pages
    ("P1 → P2", "基準計画（凍結）", "追跡の Orient の入力（月 1 回）"),
    ("P1 → P2", "年度の着地", "月次で引き直す"),
    ("P2 → P1", "実績（Observe）", "20 年の履歴の今日の状態、便の計画、劣化率・計画外率、回答ログ（納期）→ ① 前提"),
    ("P2 → P1", "学習（Orient）", "追跡の事後確率と補正 → ② 世界と重み（年 1 回）"),
    ("P2 → P1", "変化点", "観測世界を足す → ② 世界と重み"),
    ("P2 → P1", "見張り", "AOG > 5% で購入の輪を随時回す"),
]


# ---------------------------------------------------------------- the strategy stack
def strategy_stack() -> str:
    """Left to right: what comes in, the four strategies run side by side, how they are
    bundled, how the plan is solved, and — on the far right — what the result should be.
    Thick crimson = the recommended path; small grey line under a box = where the literature
    for that method sits."""
    W, Hh = 1400, 760
    o = [f'<rect width="{W}" height="{Hh}" fill="{BG}"/>',
         f'<defs><marker id="sa" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{LINE}"/></marker>'
         f'<marker id="sr" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{LOOP}"/></marker></defs>']
    def T(x, y, t, size=12, fill=INK, w="", anchor="start"):
        o.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" {w}>{t}</text>')
    def box(x, y, w, h, title, l1, lit="", kind="det", strong=False):
        f, st = COL[kind]
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{f}" stroke="{LOOP if strong else st}" stroke-width="{2.5 if strong else 1.5}"/>')
        T(x + 9, y + 17, title, 12, INK, 'font-weight="700"'); T(x + 9, y + 33, l1, 10.5)
        if lit: T(x + 9, y + h - 8, lit, 9.5, MUTE)
    def col(x, w, n, title, sub, fill):
        o.append(f'<rect x="{x}" y="70" width="{w}" height="{Hh - 150}" rx="10" fill="{fill}" stroke="#e2e8f0"/>')
        o.append(f'<rect x="{x}" y="70" width="{w}" height="40" rx="10" fill="{HEAD}"/>')
        T(x + w / 2, 88, f"{n} {title}", 13, "#fff", 'font-weight="700"', "middle"); T(x + w / 2, 103, sub, 10, "#cbd5e1", "", "middle")
    def poly(pts, red=False, w=1.6, dash=""):
        o.append(f'<polyline fill="none" points="{pts}" stroke="{LOOP if red else LINE}" stroke-width="{w}" {f"stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""} marker-end="url(#{"sr" if red else "sa"})"/>')
    T(20, 30, "あるべき分析ストラテジー：左から右へ。いちばん右が「あるべき結果」", 20, INK, 'font-weight="700"')
    T(20, 52, "太い深紅の矢印＝推奨する経路。各箱の下の小さな灰色＝その方法が語られている文献の系統。深紅の枠＝この設計で新しく足すところ。", 11, MUTE)
    # five columns
    X = [20, 262, 504, 746, 988]; CW = 232; G = 10
    col(X[0], CW, "①", "観測（入る）", "便ごと〜月次", ROWA)
    col(X[1], CW, "②", "4 つのストラテジー", "同時に回す（新しく足す）", ROWB)
    col(X[2], CW, "③", "束ねる", "①等重み ②採点重み ③幅", ROWB)
    col(X[3], CW, "④", "計画を解く", "年 1 回・見張りで随時", ROWA)
    o.append(f'<rect x="{X[4]}" y="70" width="{W - X[4] - 20}" height="{Hh - 150}" rx="10" fill="rgba(190,18,60,0.05)" stroke="{LOOP}" stroke-width="2.5"/>')
    o.append(f'<rect x="{X[4]}" y="70" width="{W - X[4] - 20}" height="40" rx="10" fill="{LOOP}"/>')
    T(X[4] + (W - X[4] - 20) / 2, 88, "⑤ あるべき結果", 13, "#fff", 'font-weight="700"', "middle"); T(X[4] + (W - X[4] - 20) / 2, 103, "決める人が受け取るもの", 10, "#fecdd3", "", "middle")
    # column 1: observations
    box(X[0] + G, 124, CW - 2 * G, 92, "状態監視・残り寿命（RUL）", "EGT・LLP。複数モデルを束ねる", "RUL のアンサンブル：Sci. Rep. 2025")
    box(X[0] + G, 230, CW - 2 * G, 92, "実績（入場・遅れ・所見・故障・費用）", "計画との差。会議前に整える", "取り込み（Secretary.io）")
    box(X[0] + G, 336, CW - 2 * G, 92, "回答ログ・便の実績・納期回答", "週次の先行指標、必要エンジン数", "変化点検知の入力（cpd.py）")
    box(X[0] + G, 442, CW - 2 * G, 92, "需要（e-Stat・各社月次）", "伸び・季節・逼迫の月", "予測結合：Timmermann 2006")
    # column 2: strategies
    cards = [("平均（既定）", "全期間を等しく。忘却なし、K 大", "予測結合のパズル（等重み）"), ("新しさ優先", "半減期 6〜12 か月で古い月を薄める", "DMA：Raftery ほか 2010"),
             ("クラスタ", "変化点で切る。世界を足す・外す", "BOCPD 2007／DWM 2007"), ("混成（推奨）", "平均を既定に、ゆっくり忘れ、検知で切る", "Gama ほか 2014")]
    for k, (t, l, lit) in enumerate(cards):
        box(X[1] + G, 124 + k * 106, CW - 2 * G, 92, t, l, lit, "mc", strong=(k == 3))
    T(X[1] + CW / 2, 552, "同じ観測から 4 本の「前提」が出る", 10.5, MUTE, "", "middle"); T(X[1] + CW / 2, 567, "（世界の確率・補正・伸び）", 10.5, MUTE, "", "middle")
    # column 3: bundling
    box(X[2] + G, 124, CW - 2 * G, 110, "① 等重み平均（既定）", "4 本を等しく平均 → 束ねた前提", "予測結合のパズル：Bates & Granger 1969", "mc", strong=True)
    box(X[2] + G, 248, CW - 2 * G, 110, "② 採点重み（年 1 回）", "過去での検証の点数で重み。年 1 回だけ", "スタッキング：Yao ほか 2018／BPS 2019", "mc")
    box(X[2] + G, 372, CW - 2 * G, 110, "③ 幅を信号に", "4 本の答えの幅が広い月 → 見直しへ", "spread–skill：Leutbecher & Palmer 2008", "judge", strong=True)
    box(X[2] + G, 496, CW - 2 * G, 92, "過去での検証：4 つを採点", "学ぶ 5 版／確かめる 5 版", "交差検証に相当（backtest.py）", "mc")
    # column 4: solving
    box(X[3] + G, 124, CW - 2 * G, 110, "内側：解いて叩く", "MILP 40 本 → MC 800 本 × 24 か月", "確率計画：SDDP、EJOR 2024", "mc", strong=True)
    box(X[3] + G, 248, CW - 2 * G, 110, "購入の輪（後悔最小）", "どの型でも 5% を満たす手だけ候補", "Savage 1951／RDM 2003／METRIC", "mc", strong=True)
    T(X[3] + G + 9, 248 + 49, "上限：工場の約束・中古市場・予備", 10.5, MUTE)
    box(X[3] + G, 372, CW - 2 * G, 110, "見直し（月次会議）", "幅・変化点・引き金 → Check → Act", "review.py（規則層＋AI 層）", "judge")
    # column 5: the result
    RX = X[4] + G; RW = W - X[4] - 20 - 2 * G
    box(RX, 124, RW, 110, "予算内の年度計画（幅つき）", "p10〜p90 と欠航確率。束ねた前提で 1 本", "", "judge", strong=True)
    box(RX, 248, RW, 110, "壊れにくい購入計画", "4 つのストラテジーすべてで欠航 ≤ 5%。手は最小限", "後悔最小・RDM", "judge", strong=True)
    box(RX, 372, RW, 110, "見直しの引き金（いつ会議か）", "幅が広い月・変化点・伸び差 3pt", "", "judge", strong=True)
    box(RX, 496, RW, 92, "来年のストラテジーと採点表", "4 つの点数と、表紙に記す束ね方", "", "judge", strong=True)
    box(RX + 60, 602, RW - 60, 36, "→ 決める：版の承認・購入・便・投資", "", "", "judge")
    # arrows (recommended path thick crimson)
    for y in (170, 276, 382, 488):
        poly(f"{X[0] + CW - G},{y} {X[1] + G},{y}", True, 3)                       # observations -> strategies (each row)
    poly(f"{X[1] + CW - G},{170} {X[2] + G},{179}", True, 3)                         # strategies -> ①
    poly(f"{X[1] + CW - G},{382} {X[2] + G},{427}", True, 3)                         # -> ③
    poly(f"{X[2] + CW - G},{179} {X[3] + G},{179}", True, 3)                         # ① -> inner
    poly(f"{X[3] + CW / 2},{234} {X[3] + CW / 2},{248}", True, 3)                    # inner -> purchase loop
    poly(f"{X[3] + CW - G},{303} {X[4] + G},{303}", True, 3)                         # purchase loop -> robust plan
    poly(f"{X[3] + CW - G},{179} {X[4] + G},{179}", True, 3)                         # inner -> budget plan
    poly(f"{X[2] + CW - G},{427} {X[3] + G},{427}", True, 3)                         # ③ -> review
    poly(f"{X[3] + CW - G},{427} {X[4] + G},{427}", True, 3)                         # review -> trigger
    poly(f"{X[2] + CW / 2},{496} {X[2] + CW / 2},{358}", False, 1.8, "6 4")           # backtest -> ② (yearly weights)
    poly(f"{X[2] + CW - G},{542} {X[4] + G},{542}", False, 1.8)                      # backtest -> scoring table (through the empty row)
    poly(f"{X[4] + RW / 2 + 30},{588} {X[4] + RW / 2 + 30},{602}", True, 3)          # results -> decide
    # feedback: next year's strategy -> strategies (dashed along the bottom)
    poly(f"{RX + 24},{588} {RX + 24},{Hh - 96} {X[1] + CW / 2},{Hh - 96} {X[1] + CW / 2},{Hh - 118}", False, 1.8, "6 4")
    T(X[1] + CW / 2 + 14, Hh - 102, "年 1 回：採点で来年の型と重みを決めて戻す（点線）", 10.5, MUTE)
    # legend
    y0 = Hh - 60
    T(20, y0, "推奨経路（太い深紅）：観測 → 4 つを同時に回す → ① 等重みで束ねる → 内側で解いて叩く → 購入の輪で後悔最小 → 壊れにくい購入計画と予算内の年度計画 → 決める。③ の幅は見直しの引き金に。", 12, INK, 'font-weight="700"')
    T(20, y0 + 20, "② 採点重みは年 1 回だけ（点線）。月次では重みを動かさない。理由：重みを推定するほど誤差が増える（予測結合のパズル）。", 11.5)
    T(20, y0 + 40, "文献の位置：① の RUL は部品層のアンサンブル、④ は機隊層の確率計画（SDDP）、上限は在庫理論と容量計画。② と ③（学習の型を束ねる）は当たった範囲で論文がなく、ここが新しい。すべて合成データの目安。", 11.5, MUTE)
    body = "".join(o)
    def fix(m):
        tag = m.group(0); st = []
        for k in ("fill", "font-size", "font-weight"):
            mm = re.search(rf' {k}="([^"]*)"', tag)
            if mm: st.append(f"{k}:{mm.group(1)}{'px' if k == 'font-size' else ''}"); tag = tag.replace(mm.group(0), "")
        return tag[:-1] + f' style="{";".join(st)};font-family:IBM Plex Sans JP,Noto Sans JP,sans-serif">' if st else tag
    body = re.sub(r"<text[^>]*>", fix, body)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" role="img" aria-label="あるべき分析ストラテジー" font-family="IBM Plex Sans JP, sans-serif">' + body + "</svg>"


OUTPUTS = [  # key, name, when, who, what, sources (analysis), screen (file or report view), section of the A4 integrated report
    ("annual_report", "年次レポート", "年 1 回（10 月の版）", "整備計画 → 経営", "年度ごとの整備費と予算、欠航率、退役までの入場列、購入計画、次の版で直す決め方", "baseline・runout・purchase_loop・backtest", "annual.html／report.html（年間計画と予算）", "1・3・4・7・8"),
    ("plan", "計画（基準計画と購入計画）", "年 1 回、見張りが警告したら随時", "整備計画", "エンジンごとの入場月・作業範囲・工場、判断期限、購入する手（予備・プール・中寿命機）", "baseline（MILP＋MC）・purchase_loop・playbook", "report.html（エンジン別の明細・購入計画の輪）", "3・4・5"),
    ("monthly_review", "月次見直し", "月 1 回（月次会議）", "整備計画・技術・調達", "実績と計画の差、シナリオの確率、見直しの合図（ばらつき・変化点・引き金）、PDCA／OODA の症状表", "track・cpd・shortage・review（規則層＋AI 層）", "report.html（PDCA／OODA の見直し・計画の追跡）", "6"),
    ("monthly_report", "月次レポート", "月 1 回", "整備計画 → 経営", "今月の判断期限、乗り換えの推奨、不足の見張り（3 か月先の欠航率）、年度の着地の更新", "track・shortage・landing", "monthly.html／track.html", "6"),
    ("plan_revision", "計画修正", "月次の見直しで必要と判断したとき", "整備計画（承認は経営）", "乗り換え先の計画、短期リースの手当て、購入の輪の再実行結果、差分（何基が動くか）", "decide・shortage・purchase_loop（--from-shortage）", "report.html（計画の追跡 → 乗り換え、打ち手の効果）", "6"),
    ("annual_review", "年間見直し", "年 1 回（次の版の前）", "技術・整備計画・経営企画", "過去での検証（8 版）、補正（入場時期・計画外率）、4 つの手法の成績と来年の手法、需要の伸びの見直し", "backtest・roll・plan_from_demand", "report.html（過去で検証・次の版への引き継ぎ・客席の需要）", "7・8・付録 B"),
]


OV_FLIGHT = [("便1", "必要エンジン数＝飛ぶ機数 × 2 − 整備中の機", 0, 2), ("便2", "稼働率 → 劣化の速さと整備までの期間", 3, 1), ("便3", "季節の波 → 整備入りを閑散期に置く", 1, 1),
             ("便4", "増便 → 予備エンジンの数", 0, 1), ("便5", "新機材の受領時期 → 退役の順番と速さ", 1, 0), ("便6", "路線の長さ → 劣化のしかた", 3, 0)]
OV_STAGES = [["Plan 計画", "Do 実行", "Check 評価", "Act 改善"], ["Plan 計画", "Do 実行", "Check 評価", "Act 改善"], ["Plan 計画", "Do 実行", "Check 評価", "Act 改善"], ["Observe 観測", "Orient 状況判断", "Decide 決定", "Act 行動"], ["Observe 観測", "Observe 観測", "Observe 観測", "—"]]
OV_KPI = [["便の運航達成率 100%", "増便の余地 > 0"], ["欠航率 5% 以下", "予算との差 ±5% 以内"], ["約束件数の達成", "納期回答の遅れ 1 か月以内"], ["予測の的中率 80% 以上", "変化の検知遅れ 2 か月以内"], ["欠けた値 2% 以下", "遅れ 1 日以内"]]
OV_AI = {(0, 1): ("計算式", "#475569"), (1, 1): ("数理最適化＋シミュレーション", "#4338ca"), (2, 1): ("計算式＋人（契約の交渉）", "#b45309"), (3, 1): ("機械学習＋統計的な学習", "#4338ca"), (4, 1): ("データ基盤", "#0e7490"), (4, 3): ("データ", "#0e7490"),
         (3, 2): ("AI（文章の生成と振り分け）", "#9333ea"), (0, 3): ("人が決める", "#b45309"), (1, 3): ("人が決める", "#b45309"), (2, 3): ("人（契約）", "#b45309"), (3, 3): ("人＋AI（症状の整理）", "#9333ea")}
OV_LINKS = [[("demand", "客席の需要・足す計画"), ("runout", "退役までの入場列")], [("budget", "年間計画と予算"), ("playbook", "購入計画の輪"), ("month", "今月からの判断")], [("actions", "打ち手の効果"), ("resilience", "立て直しの安さ"), ("lease", "リース返却")],
            [("track", "計画の追跡"), ("cpd", "変化点と前提の整合"), ("backtest", "過去で検証"), ("review", "PDCA／OODA の見直し")], [("sources", "前提と出典")]]


def overview_rows():
    ROWA_, ROWB_ = ROWA, ROWB
    rows = [
        ("① 航空計画", "運航・機材計画｜年 1 回・季節ごと", ROWB_,
         ("需要データと便の計画", ["国の統計と各社の月次の需要", "路線と便数、新機材の受領予定"], "", "det", False),
         ("需要の伸びを見積もり、便数から必要な機数を出す", ["直近 2 年と長期 5 年の伸びを組み合わせる", "需要の余地とエンジンの余力から、増やせる便数を出す"], "予測の結合：Timmermann 2006／機材計画：Omega（B）", "det", False),
         ("必要エンジン数と増便の余地", ["整備計画の目標になる", "新機材の受領遅れは退役ペースに影響"], "", "det", False),
         ("便数に見合う機材計画", ["便の計画に合った必要エンジン数", "増やせる便と、増やせない月"])),
        ("② エンジン整備計画", "整備計画部門｜年 1 回・必要に応じて", ROWA_,
         ("統合した前提と制約", ["シナリオの確率・補正値・伸び（技術から）", "工場の枠・納期・価格（MRO から）、予備"], "", "det", False),
         ("最適化 → シミュレーションで検証 → 購入計画", ["整備計画を最適化し（シナリオ 40 本）、800 通りの将来で検証", "どの前提でも欠航率 5% 以下になる案だけ残す"], "確率計画：EJOR 2024／後悔最小：Savage 1951／頑健な意思決定：Lempert 2003", "mc", True),
         ("入場計画とその不確実性", ["いつ・何件・どの工場に出すか、費用の幅", "月次の見張りが警告したら再計算"], "", "mc", False),
         ("年度計画と購入計画", ["予算内で、不確実性の幅つき", "どの前提でも欠航率 5% 以下。購入は最小限"])),
        ("③ MRO と調達", "工場・部品・契約｜四半期・月次", ROWB_,
         ("入場計画と見積依頼、市場", ["何件・いつ・どの作業範囲か", "中古エンジンと部品の市場"], "", "det", False),
         ("工場の枠と容量、契約条件、部品の納期", ["約束件数に応じた容量の増強、固定価格や追加作業の折半", "部品（LLP キット）の納期回答"], "容量計画：Management Science 1991／在庫：METRIC", "det", False),
         ("枠・納期・価格（制約）、進捗の記録", ["整備計画へ：使える枠と価格の上限", "データへ：工場の進捗と納期回答"], "", "det", False),
         ("確保した枠と契約", ["約束件数と価格の上限", "納期回答の遅れが見える"])),
        ("④ 技術", "状態監視・残り寿命・前提の更新｜便ごと〜月次", ROWA_,
         ("整えたデータ", ["排気温度・部品の残り寿命、入場・遅れ・故障", "納期の回答記録、便の実績"], "", "mc", True),
         ("残り寿命の推定、変化の検知、4 つの手法で前提を更新", ["残り寿命は複数モデルの組み合わせ。納期回答の変化を検知", "前提は 4 手法（平均・直近重視・状況別・混合）で学ぶ", "① 単純平均 ② 成績で重み付け ③ ばらつきを見直しの合図に"], "残り寿命のアンサンブル：Sci. Rep. 2025／予測結合／動的モデル平均／変化点検知", "mc", True),
         ("現在の状態と統合した前提", ["エンジンごとの残り時間と部品、計画との差", "シナリオの確率・補正値・伸びを整備計画へ"], "", "mc", True),
         ("現在の状態と見直しの合図", ["いつ会議で見直すか", "4 つの手法の成績と、採用した統合方法"])),
        ("⑤ データ", "センサー・記録｜便ごと・日次", ROWB_,
         ("センサーと記録", ["機上センサー（排気温度・振動・油圧）", "工場の進捗、部品の納期回答、運航の記録"], "", "det", False),
         ("集めて整え、異常の一次検知", ["欠けた値を補い、単位と時刻を揃える", "しきい値と傾きで異常の候補を拾う"], "データ基盤：取り込み → 索引 → 検索（Aether Platform）", "det", False),
         ("便ごとの時系列と実績データ", ["エンジン・部品ごとに揃った時系列", "会議前に整えた実績（Secretary.io）"], "", "det", False),
         ("信頼できるデータ", ["欠けが少なく、遅れない", "（判断材料の土台）"])),
    ]
    return rows


def strategy_matrix(overlays: bool = True, compact: bool = True) -> str:
    """One level more abstract: rows are the four layers of the first figure, columns are the
    flow (what enters, what is run, what comes out), and the far right is the result the
    decision-maker should receive. Observation rises, decisions descend."""
    W, Hh = 1400, 1190
    o = [f'<rect width="{W}" height="{Hh}" fill="{BG}"/>',
         f'<defs><marker id="ma" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker>'
         f'<marker id="mr" markerWidth="12" markerHeight="12" refX="11" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L12,6 L0,12 z" fill="{LOOP}"/></marker>'
         f'<marker id="mg" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 z" fill="{PORT}"/></marker></defs>']
    def T(x, y, t, size=12, fill=INK, w="", anchor="start"):
        o.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" {w}>{t}</text>')
    def cell(x, y, w, h, title, lines, lit="", kind="det", strong=False):
        f, st = COL[kind]
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{f}" stroke="{LOOP if strong else st}" stroke-width="{2.6 if strong else 1.5}"/>')
        T(x + 10, y + 19, title, 12.5, INK, 'font-weight="700"')
        for i, l in enumerate(lines[:1] if compact else lines): T(x + 10, y + 37 + i * 15, l, 10.5)
        if lit and not compact: T(x + 10, y + h - 8, lit, 9.5, MUTE)
    nref = [0]
    def poly(pts, red=False, w=2.4, dash="", teal=False):
        col_, mk = (LOOP, "mr") if red else (PORT, "mg") if teal else (LINE, "ma")
        cls = "flow red" if red else "flow teal" if teal else ("flow dashed" if dash else "flow")
        o.append(f'<polyline class="{cls}" fill="none" points="{pts}" stroke="{col_}" stroke-width="{w}" stroke-linejoin="round" {f"stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""} marker-end="url(#{mk})"/>')
        if red:   # a dot that travels along the recommended path (ThingsBoard-style flow)
            nref[0] += 1; d = "M " + " L ".join(p_.replace(",", " ") for p_ in pts.split())
            o.append(f'<path id="rp{nref[0]}" d="{d}" fill="none" stroke="none"/><circle class="dot" r="5" fill="#fff" stroke="{LOOP}" stroke-width="2.5"><animateMotion dur="{max(1.2, len(pts.split()) * 0.9)}s" repeatCount="indefinite"><mpath href="#rp{nref[0]}"/></animateMotion></circle>')
    T(20, 30, "分析の全体像：5 つの部門 × 入力・処理・出力。右端が「得られる成果」", 20, INK, 'font-weight="700"')
    T(20, 52, "行＝層、列＝入力 → 処理 → 出力。線の色：深紅（太）＝推奨する流れ、青緑＝下の層の結果が上の層へ渡る、灰の点線＝上の層の決定が下の層へ渡る。処理の箱の下の灰色＝根拠となる文献。", 11, MUTE)
    LX, T0 = 170, 100; CW = [240, 380, 230]; GX = 22; RH = 150; GY = 40
    X0 = LX; X1 = X0 + CW[0] + GX; X2 = X1 + CW[1] + GX; XR = X2 + CW[2] + 26; RW = W - XR - 20
    heads = [("入力", "その層が受け取るもの"), ("処理", "どう扱うか（計算か人か）"), ("出力", "上の層と右へ渡すもの")]
    for x, w, (h, sub) in zip((X0, X1, X2), CW, heads):
        o.append(f'<rect x="{x}" y="{T0 - 44}" width="{w}" height="36" rx="8" fill="{HEAD}"/>'); T(x + w / 2, T0 - 28, h, 13, "#fff", 'font-weight="700"', "middle"); T(x + w / 2, T0 - 14, sub, 9.5, "#cbd5e1", "", "middle")
    NR = 5
    o.append(f'<rect x="{XR}" y="{T0 - 44}" width="{RW}" height="{NR * RH + (NR - 1) * GY + 44}" rx="10" fill="rgba(190,18,60,0.05)" stroke="{LOOP}" stroke-width="2.5"/>')
    o.append(f'<rect x="{XR}" y="{T0 - 44}" width="{RW}" height="36" rx="8" fill="{LOOP}"/>'); T(XR + RW / 2, T0 - 28, "得られる成果", 13, "#fff", 'font-weight="700"', "middle"); T(XR + RW / 2, T0 - 14, "意思決定者が受け取るもの", 9.5, "#fecdd3", "", "middle")
    rows = overview_rows()
    for r, (lab, cad, fill, cin, crun, cout, res) in enumerate(rows):
        y = T0 + r * (RH + GY)
        o.append(f'<g class="row" data-row="{r}" data-y0="{y - 24}" data-y1="{y + RH + 24}">')
        o.append(f'<rect x="20" y="{y}" width="{XR - 20 - 12}" height="{RH}" rx="10" fill="{fill}" stroke="#e2e8f0"/>')
        T(30, y + 22, lab, 13, INK, 'font-weight="700"'); 
        for i, part in enumerate(cad.split("｜")): T(30, y + 40 + i * 14, part, 10, MUTE)
        if r == 3:
            o.append(f'<rect x="{X0 - 6}" y="{y + 4}" width="{X2 + CW[2] - X0 + 12}" height="{RH - 8}" rx="9" fill="none" stroke="{LOOP}" stroke-width="2.5" stroke-dasharray="10 5"/>')
            o.append(f'<rect x="{X1 + 40}" y="{y - 10}" width="150" height="19" rx="5" fill="{LOOP}"/>'); T(X1 + 48, y + 3, "新しく加える部分", 11, "#fff", 'font-weight="700"')
        cell(X0, y + 12, CW[0], RH - 24, *cin)
        cell(X1, y + 12, CW[1], RH - 24, *crun)
        cell(X2, y + 12, CW[2], RH - 24, *cout)
        strong = r in (1, 3)
        cell(XR + 10, y + 12, RW - 20, RH - 24, res[0], res[1], "", "judge", strong)
        if compact: T(X2 + CW[2] - 8, y + RH - 6, "クリックで拡大と詳細 ›", 10, MUTE, "", "end")
        o.append('</g>')
        red = r in (1, 3)
        poly(f"{X0 + CW[0] + 2},{y + RH / 2} {X1 - 2},{y + RH / 2}", red, 4.5 if red else 2.4)
        poly(f"{X1 + CW[1] + 2},{y + RH / 2} {X2 - 2},{y + RH / 2}", red, 4.5 if red else 2.4)
        poly(f"{X2 + CW[2] + 2},{y + RH / 2} {XR + 8},{y + RH / 2}", red, 4.5 if red else 2.4)
    # vertical: observation rises (out of the lower row -> in of the upper row), decisions descend (dashed)
    for r in range(1, NR):
        yt = T0 + (r - 1) * (RH + GY) + RH - 12; yb = T0 + r * (RH + GY) + 12; ym = (yt + yb) / 2
        poly(f"{X2 + CW[2] - 50},{yb} {X2 + CW[2] - 50},{ym} {X0 + CW[0] - 50},{ym} {X0 + CW[0] - 50},{yt}", False, 3, "", teal=True)
        poly(f"{X0 + 36},{yt} {X0 + 36},{yb}", False, 2.2, "7 5")
        T(X0 + CW[0] - 44, ym - 5, "上へ：" + {1: "計画と不確実性", 2: "枠・納期・価格（制約）", 3: "残り寿命（作業範囲の見積に）", 4: "整えたデータ"}[r], 10, PORT, 'font-weight="700"')
        T(X0 + 42, ym + 4, "下へ：" + {1: "必要エンジン数", 2: "入場計画（何件・いつ）", 3: "作業の記録・何を監視するか", 4: "何を測るか（警報のしきい値）"}[r], 10, MUTE)
    # the recommended path: updated assumptions go from 技術 (row 4) straight to 整備計画 (row 2), past MRO
    yt2 = T0 + 1 * (RH + GY) + RH - 12; yb2 = T0 + 3 * (RH + GY) + 12; xg = X2 + CW[2] + 12; ym2 = T0 + 1 * (RH + GY) + RH + GY / 2 + 12
    poly(f"{X2 + CW[2] - 110},{yb2} {X2 + CW[2] - 110},{yb2 - 16} {xg},{yb2 - 16} {xg},{ym2} {X0 + CW[0] - 110},{ym2} {X0 + CW[0] - 110},{yt2}", True, 4.5)
    T(X1 + 80, ym2 - 6, "上へ：統合した前提（技術 → 整備計画、MRO を越えて）", 10, LOOP, 'font-weight="700"')
    # the decision under the result column
    yd = T0 + NR * RH + (NR - 1) * GY + 12
    o.append(f'<rect x="{XR + 10}" y="{yd}" width="{RW - 20}" height="34" rx="8" fill="{COL["judge"][0]}" stroke="{COL["judge"][1]}" stroke-width="1.5"/>'); T(XR + RW / 2, yd + 22, "→ 意思決定：計画の承認・購入・便数・投資", 12, INK, 'font-weight="700"', "middle")
    poly(f"{XR + RW / 2},{T0 + NR * RH + (NR - 1) * GY - 8} {XR + RW / 2},{yd - 2}", True, 4.5)
    # feedback: next year's strategy back to the learning layer (dashed)
    yf = T0 + 3 * (RH + GY) + RH + 6
    poly(f"{XR + 60},{T0 + 3 * (RH + GY) + RH - 12} {XR + 60},{yf} {X2 + CW[2] - 60},{yf} {X2 + CW[2] - 60},{T0 + 3 * (RH + GY) + RH - 12}", False, 2.2, "7 5")
    T(XR + 54, yf + 14, "年 1 回：成績を見て来年の手法と重みを決める", 10, MUTE, "", "end")
    if overlays:
        FL = "#0e7490"
        def chip(x, y, t, col, fill="#fff", size=10):
            bw = tw(t, size) + 12
            o.append(f'<rect x="{x}" y="{y}" width="{bw}" height="17" rx="8" fill="{fill}" stroke="{col}" stroke-width="1.4"/>'); T(x + bw / 2, y + 12, t, size, col, 'font-weight="700"', "middle"); return bw
        # 1. what the flight plan (航空計画) derives — numbered teal badges in the cells they land in
        o.append('<g id="ov-flight">')
        FLIGHT = OV_FLIGHT
        cols_x = [X0, X1, X2]
        for k, (tag, what, r, c) in enumerate(FLIGHT):
            y = T0 + r * (RH + GY) + 12; x = cols_x[c] + CW[c] - 46 - (k % 2) * 40
            o.append(f'<circle cx="{x}" cy="{y + 14}" r="12" fill="{FL}"/>'); T(x, y + 18, tag, 9.5, "#fff", 'font-weight="700"', "middle")
        ys = Hh - 118
        o.append(f'<rect x="20" y="{ys}" width="{W - 40}" height="44" rx="8" fill="rgba(14,116,144,0.07)" stroke="{FL}" stroke-width="1.4"/>')
        T(30, ys + 17, "航空計画（便の計画）から導かれるもの：便数が必要エンジン数を決め、下の層へ渡る", 11, FL, 'font-weight="700"')
        T(30, ys + 34, "　".join(f"{t} {w}" for t, w, _, _ in FLIGHT), 10, INK)
        o.append('</g>')
        # 2. PDCA (rows ①②) and OODA (rows ③④) stage chips, one per cell
        o.append('<g id="ov-stage">')
        STAGES = OV_STAGES
        for r in range(NR):
            y = T0 + r * (RH + GY) + 12 + 4; col_ = PDCA if r < 3 else OODA
            for c, x in enumerate([X0, X1, X2, XR + 10]):
                chip(x + 6, y - 14, STAGES[r][c], col_, "#fff", 9.5)
        o.append(f'<rect x="4" y="{T0}" width="10" height="{3 * RH + 2 * GY}" rx="3" fill="{PDCA}"/><rect x="4" y="{T0 + 3 * (RH + GY)}" width="10" height="{2 * RH + GY}" rx="3" fill="{OODA}"/>')
        T(-(T0 + 1.5 * RH + GY), 12, "PDCA（年次〜四半期）", 10, "#fff", 'font-weight="700" transform="rotate(-90)"', "middle")
        T(-(T0 + 3 * (RH + GY) + RH + GY / 2), 12, "OODA（月次〜便ごと）", 10, "#fff", 'font-weight="700" transform="rotate(-90)"', "middle")
        o.append('</g>')
        # 3. output-based: a KPI with a target under each result box
        o.append('<g id="ov-output">')
        KPI = OV_KPI
        for r in range(NR):
            y = T0 + r * (RH + GY) + 12 + RH - 24 - 40; x = XR + 16
            T(x, y - 4, "成果指標（目標）", 9.5, "#7c2d12", 'font-weight="700"')
            for k_, t in enumerate(KPI[r]):
                x += chip(x, y, t, "#7c2d12", "#fff7ed", 9.5) + 6
        o.append('</g>')
        # 4. what kind of intelligence does the work in each box
        o.append('<g id="ov-ai">')
        AI = OV_AI
        for (r, c), (t, col_) in AI.items():
            x = [X0, X1, X2, XR + 10][c]; w = [CW[0], CW[1], CW[2], RW - 20][c]; y = T0 + r * (RH + GY) + 12 + RH - 24
            bw = tw(t, 9.5) + 12
            o.append(f'<rect x="{x + w - bw - 6}" y="{y - 9}" width="{bw}" height="17" rx="4" fill="{col_}"/>'); T(x + w - 6 - bw / 2, y + 3, t, 9.5, "#fff", 'font-weight="700"', "middle")
        o.append('</g>')
    y0 = Hh - 36
    T(20, y0, "推奨する流れ（太い深紅）：データを整える → 技術が 4 つの手法で前提を学び、統合する（④）→ 整備計画が最適化とシミュレーションで、どの前提でも欠航 5% 以下の計画を作る（②）→ 年度計画と購入計画 → 意思決定。数値はすべて合成データの目安。", 11.5, INK, 'font-weight="700"')
    T(20, y0 + 18, "行は部門の単位：航空計画（運航・機材）、エンジン整備計画、MRO と調達、技術、データ。基本計画（年次、PDCA）は行 ①②③、詳細計画（月次〜便ごと、OODA）は行 ④⑤。行 ④ の「4 つの手法で前提を更新」が新しく加える部分。", 11, MUTE)
    body = "".join(o)
    def fix(m):
        tag = m.group(0); st = []
        for k in ("fill", "font-size", "font-weight"):
            mm = re.search(rf' {k}="([^"]*)"', tag)
            if mm: st.append(f"{k}:{mm.group(1)}{'px' if k == 'font-size' else ''}"); tag = tag.replace(mm.group(0), "")
        return tag[:-1] + f' style="{";".join(st)};font-family:IBM Plex Sans JP,Noto Sans JP,sans-serif">' if st else tag
    body = re.sub(r"<text[^>]*>", fix, body)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" role="img" aria-label="あるべき分析ストラテジー（層 × 流れ）" font-family="IBM Plex Sans JP, sans-serif">' + body + "</svg>"


def extra_svgs() -> dict[str, str]:
    return {"strategy_stack": strategy_stack(), "strategy_matrix": strategy_matrix()}


def svgs() -> dict[str, str]:
    return {"plan_basic": plan_basic(), "plan_detail": plan_detail()}


def overview_hero() -> str:
    """The title, drawn: one line from the flight plan to the decision, five boxes."""
    W, Hh = 1400, 245
    steps = [("航空需要", "市場と各社の\n乗客の伸び", "#d1fae5", "#047857"), ("航空計画", "便数から\n必要エンジン数", "#d1fae5", "#047857"), ("現場のデータ", "センサーと実績で\n前提を更新", "#d1fae5", "#047857"),
             ("整備計画", "最適化と\nシミュレーション", "#e0e7ff", "#4338ca"), ("MRO と調達", "工場の枠・部品・\n契約で裏づけ", "#e0e7ff", "#4338ca"),
             ("意思決定", "年度計画・購入計画・\n見直しの合図", "#fef3c7", "#b45309")]
    n = len(steps); bw, bh = 196, 110; gap = (W - 40 - n * bw) / (n - 1); y = 14
    o = [f'<rect width="{W}" height="{Hh}" fill="{BG}"/>',
         f'<defs><marker id="hh" markerWidth="12" markerHeight="12" refX="11" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L12,6 L0,12 z" fill="{LOOP}"/></marker></defs>',
         f'<line class="flow red" x1="{20 + bw}" y1="{y + bh / 2}" x2="{20 + (n - 1) * (bw + gap)}" y2="{y + bh / 2}" stroke="{LOOP}" stroke-width="5" marker-end="url(#hh)"/>',
         f'<circle class="dot" r="6" fill="#fff" stroke="{LOOP}" stroke-width="3"><animateMotion dur="4s" repeatCount="indefinite" path="M {20 + bw} {y + bh / 2} L {20 + (n - 1) * (bw + gap) - 8} {y + bh / 2}"/></circle>']
    for i, (t, sub, f, st) in enumerate(steps):
        x = 20 + i * (bw + gap)
        o.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="12" fill="{f}" stroke="{st}" stroke-width="2.5"/>')
        o.append(f'<circle cx="{x + 22}" cy="{y + 24}" r="12" fill="{st}"/><text x="{x + 22}" y="{y + 28}" font-size="12" font-weight="700" fill="#fff" text-anchor="middle">{i + 1}</text>')
        o.append(f'<text x="{x + 40}" y="{y + 29}" font-size="16" font-weight="700" fill="{INK}">{t}</text>')
        for k, l in enumerate(sub.split("\n")): o.append(f'<text x="{x + 16}" y="{y + 58 + k * 20}" font-size="13" fill="{INK}">{l}</text>')

    items = [("box", "#d1fae5", "#047857", "緑＝式とデータの扱い（決定論）"), ("box", "#e0e7ff", "#4338ca", "藍＝確率の計算（最適化・シミュレーション・統計）"), ("box", "#fef3c7", "#b45309", "黄＝人の判断（承認・契約・意思決定）"),
             ("line", LOOP, 4, "深紅＝推奨する流れ・新しく加える部分"), ("line", PORT, 3, "青緑＝下から上へ渡る結果"), ("dash", LINE, 2.2, "灰の点線＝上から下へ渡る決定")]
    lx = 20; ly = y + bh + 78
    for kind, c1, c2, lab in items:
        if kind == "box": o.append(f'<rect x="{lx}" y="{ly - 11}" width="16" height="14" rx="3" fill="{c1}" stroke="{c2}" stroke-width="1.5"/>')
        else:
            da = 'stroke-dasharray="7 5"' if kind == "dash" else ""
            o.append(f'<line x1="{lx}" y1="{ly - 4}" x2="{lx + 22}" y2="{ly - 4}" stroke="{c1}" stroke-width="{c2}" {da}/>')
        o.append(f'<text x="{lx + 28}" y="{ly}" font-size="12" fill="{INK}">{lab}</text>'); lx += 28 + tw(lab, 12) + 26
        if kind == "box" and lab.startswith("黄"): lx = 20; ly += 20
    o.append(f'<text x="{W / 2}" y="{y + bh + 40}" font-size="13" fill="{MUTE}" text-anchor="middle">需要が便数を決め、便数が必要エンジン数を決める。現場のデータが前提を毎月更新し、計算が計画を作り、人が決める。</text>')
    o.append(f'<text x="{W / 2}" y="{y + bh + 60}" font-size="13" fill="{MUTE}" text-anchor="middle">下の図は、この流れを部門ごとの「入力 → 処理 → 出力 → 成果」に分けたもの（① 航空需要と ② 航空計画は行 ①、③ は行 ⑤④、④ は行 ②、⑤ は行 ③、⑥ は右端）。</text>')
    body = "".join(o)
    body = re.sub(r"<text[^>]*>", lambda m: m.group(0)[:-1] + ' style="font-family:IBM Plex Sans JP,Noto Sans JP,sans-serif">', body)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" role="img" aria-label="航空計画から意思決定まで" font-family="IBM Plex Sans JP, sans-serif">' + body + "</svg>"


def outputs_cycle() -> str:
    """Yearly band on top, the 12-month axis in the middle, the monthly band below, and the
    integrated report at the bottom."""
    W, Hh = 1400, 368
    o = [f'<rect width="{W}" height="{Hh}" fill="{BG}"/>', f'<defs><marker id="oc" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>']
    L, R = 40, 40; x0, x1 = L + 20, W - R - 20
    def box(x, y, w, h, t, sub, f, st, size=13):
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{f}" stroke="{st}" stroke-width="2"/><text x="{x + w / 2}" y="{y + 21}" font-size="{size}" font-weight="700" fill="{INK}" text-anchor="middle">{t}</text>')
        if sub: o.append(f'<text x="{x + w / 2}" y="{y + 38}" font-size="10.5" fill="{MUTE}" text-anchor="middle">{sub}</text>')
    # yearly band (top)
    o.append(f'<rect x="{L}" y="14" width="{W - L - R}" height="92" rx="10" fill="rgba(71,85,105,0.06)" stroke="{PDCA}" stroke-dasharray="8 5"/><text x="{L + 12}" y="32" font-size="12" font-weight="700" fill="{PDCA}">年に 1 回（10 月の版）</text>')
    bw = 250; gap = 60; xs = L + 20
    box(xs, 44, bw, 50, "① 年間見直し", "過去の検証・補正・来年の手法", "#e0e7ff", "#4338ca")
    box(xs + bw + gap, 44, bw, 50, "② 計画（版）", "基準計画と購入計画", "#e0e7ff", "#4338ca")
    box(xs + 2 * (bw + gap), 44, bw, 50, "③ 年次レポート", "年度計画・退役までの列・購入計画", "#fef3c7", "#b45309")
    for k in (0, 1): o.append(f'<line x1="{xs + bw + k * (bw + gap)}" y1="69" x2="{xs + bw + gap + k * (bw + gap) - 2}" y2="69" stroke="{LINE}" stroke-width="2" marker-end="url(#oc)"/>')
    # axis (middle)
    ya = 150
    o.append(f'<line x1="{x0}" y1="{ya}" x2="{x1}" y2="{ya}" stroke="{LINE}" stroke-width="3" marker-end="url(#oc)"/>')
    for m in range(13):
        x = x0 + (x1 - x0) * m / 12
        o.append(f'<line x1="{x}" y1="{ya - 6}" x2="{x}" y2="{ya + 6}" stroke="{LINE}" stroke-width="2"/>')
        if m < 12: o.append(f'<text x="{x + (x1 - x0) / 24}" y="{ya + 20}" font-size="10.5" fill="{MUTE}" text-anchor="middle">{(m + 9) % 12 + 1} 月</text>')
    o.append(f'<polyline fill="none" points="{xs + bw + gap + bw / 2},94 {xs + bw + gap + bw / 2},118 {x0 + 8},118 {x0 + 8},{ya - 8}" stroke="{LINE}" stroke-width="2" marker-end="url(#oc)"/>')
    o.append(f'<text x="{x0 + 16}" y="{ya - 24}" font-size="10.5" fill="{MUTE}">② を 10 月に凍結して 1 年回す</text>')
    o.append(f'<polyline fill="none" points="{x1 - 4},{ya - 8} {x1 - 4},124 {xs + 3 * bw + 2 * gap + 30},124 {xs + 3 * bw + 2 * gap + 30},69 {xs + 3 * bw + 2 * gap + 8},69" stroke="{LINE}" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#oc)"/><text x="{x1 - 12}" y="{ya - 36}" font-size="10.5" fill="{MUTE}" text-anchor="end">9 月末 → 翌年の ① 年間見直しへ（点線）</text>')
    # monthly band (below)
    yb = 184
    o.append(f'<rect x="{L}" y="{yb}" width="{W - L - R}" height="112" rx="10" fill="rgba(15,118,110,0.06)" stroke="{OODA}" stroke-dasharray="8 5"/><text x="{L + 12}" y="{yb + 18}" font-size="12" font-weight="700" fill="{OODA}">毎月（月次会議）</text>')
    for m in range(12):
        x = x0 + (x1 - x0) * m / 12; w = (x1 - x0) / 12 - 6; strong = m in (0, 4, 8)
        o.append(f'<line x1="{x + 3 + w / 2}" y1="{ya + 26}" x2="{x + 3 + w / 2}" y2="{yb + 24}" stroke="{LINE}" stroke-width="1.2"/>')
        o.append(f'<rect x="{x + 3}" y="{yb + 26}" width="{w}" height="20" rx="5" fill="#e0e7ff" stroke="#4338ca" stroke-width="1.2"/><text x="{x + 3 + w / 2}" y="{yb + 40}" font-size="9.5" fill="{INK}" text-anchor="middle">④ 見直し</text>')
        da = "" if strong else 'stroke-dasharray="4 3"'
        o.append(f'<rect x="{x + 3}" y="{yb + 50}" width="{w}" height="20" rx="5" fill="{"#e0e7ff" if strong else "#f8fafc"}" stroke="{"#4338ca" if strong else "#cbd5e1"}" stroke-width="1.2" {da}/><text x="{x + 3 + w / 2}" y="{yb + 64}" font-size="9.5" fill="{INK if strong else MUTE}" text-anchor="middle">⑤ 計画修正</text>')
        o.append(f'<rect x="{x + 3}" y="{yb + 74}" width="{w}" height="20" rx="5" fill="#fef3c7" stroke="#b45309" stroke-width="1.2"/><text x="{x + 3 + w / 2}" y="{yb + 88}" font-size="9.5" fill="{INK}" text-anchor="middle">⑥ 月次レポート</text>')
    o.append(f'<text x="{W / 2}" y="{yb + 108}" font-size="10.5" fill="{MUTE}" text-anchor="middle">⑤ は必要な月だけ（実線の月が例）。大きな修正は次の版（②）に戻す</text>')
    # integrated report (bottom)
    yr = 310
    o.append(f'<rect x="{L}" y="{yr}" width="{W - L - R}" height="50" rx="10" fill="#fee2e2" stroke="{LOOP}" stroke-width="2"/>')
    o.append(f'<text x="{L + 14}" y="{yr + 21}" font-size="13" font-weight="700" fill="{INK}">統合レポート（A4）に綴じる</text>')
    o.append(f'<text x="{L + 230}" y="{yr + 21}" font-size="11" fill="{INK}">本文 1〜8 章 ＝ ③ ＋ ② ＋ ①（年に 1 回）　　6 章 ＝ ④ ＋ ⑤ ＋ ⑥（毎月、最新分を差し替え）　　付録 ＝ 思考の枠組み・文献・出典・画面との対応</text>')
    o.append(f'<text x="{L + 14}" y="{yr + 40}" font-size="10.5" fill="{MUTE}">上の帯（年次）と下の帯（月次）の成果物を全部ここに綴じる。判断材料は各画面（対話版レポート）に置く。</text>')
    o.append(f'<line x1="{W / 2}" y1="{yb + 112}" x2="{W / 2}" y2="{yr - 2}" stroke="{LINE}" stroke-width="2" marker-end="url(#oc)"/>')
    body = "".join(o)
    body = re.sub(r"<text[^>]*>", lambda m: m.group(0)[:-1] + ' style="font-family:IBM Plex Sans JP,Noto Sans JP,sans-serif">', body)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" role="img" aria-label="成果物と統合レポート" font-family="IBM Plex Sans JP, sans-serif">' + body + "</svg>"


def overview_details() -> list[dict]:
    """Per-row detail for the concept page: full text, literature, KPIs, flight-plan items, links."""
    out = []
    for r, (lab, cad, _, cin, crun, cout, res) in enumerate(overview_rows()):
        out.append({"label": lab, "cadence": cad.replace("｜", "／"), "stage": OV_STAGES[r],
                    "input": {"title": cin[0], "lines": cin[1]}, "process": {"title": crun[0], "lines": crun[1], "lit": crun[2]},
                    "output": {"title": cout[0], "lines": cout[1]}, "result": {"title": res[0], "lines": res[1]},
                    "kpi": OV_KPI[r], "flight": [f"{t} {w}" for t, w, rr, _ in OV_FLIGHT if rr == r],
                    "works": [t for (rr, _), (t, _) in OV_AI.items() if rr == r], "links": OV_LINKS[r]})
    return out


def concept_page() -> str:
    """The landing page: five screens, one idea each, few words. The detailed grid lives on
    its own page (concept_grid_page)."""
    hero = overview_hero()
    cyc = outputs_cycle()
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>エンジン整備計画の全体像</title>
<style>body{{margin:0;background:#fff;font-family:"IBM Plex Sans JP","Noto Sans JP",sans-serif;color:{INK}}}
.s{{min-height:88vh;display:flex;flex-direction:column;justify-content:center;padding:48px 24px;border-bottom:1px solid #e2e8f0}} .s:nth-child(even){{background:{BG}}}
.in{{max-width:1240px;margin:0 auto;width:100%}} .k{{font-size:13px;letter-spacing:.16em;color:{PORT};font-weight:700;margin:0 0 10px}}
h1{{font-size:40px;line-height:1.25;margin:0 0 16px;letter-spacing:-.01em}} h2{{font-size:32px;line-height:1.3;margin:0 0 12px}}
.big{{font-size:20px;line-height:1.7;margin:0 0 20px;max-width:900px}} .sub{{font-size:15px;line-height:1.7;color:#475569;max-width:900px;margin:0}}
svg{{width:100%;height:auto;display:block}} .fig{{margin:18px 0 10px}}
.three{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px;margin-top:18px}} .three div{{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:22px 24px}}
.three b{{display:block;font-size:20px;margin-bottom:8px}} .three span{{font-size:15px;line-height:1.7;color:#334155}}
.six{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-top:18px}} .six a{{display:block;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:20px 22px;text-decoration:none;color:inherit}} .six a:hover{{border-color:{PORT}}}
.six b{{display:block;font-size:18px;margin-bottom:6px}} .six span{{font-size:14px;line-height:1.65;color:#334155}} .six em{{display:block;font-style:normal;margin-top:8px;font-size:12.5px;color:{PORT};font-weight:700}}
.cta{{display:inline-block;margin-top:14px;padding:12px 22px;background:{HEAD};color:#fff;border-radius:10px;text-decoration:none;font-size:15px;font-weight:700}} .cta.alt{{background:#fff;color:{HEAD};border:1.5px solid {HEAD};margin-left:10px}}
.anim .flow{{stroke-dasharray:22 12;animation:dash 1.1s linear infinite}} .anim .dot{{display:inline}} .dot{{display:none}} @keyframes dash{{to{{stroke-dashoffset:-34}}}} @media (prefers-reduced-motion: reduce){{.anim .flow{{animation:none}} .anim .dot{{display:none}}}}
.foot{{font-size:12px;color:{MUTE};padding:20px 24px 40px;text-align:center}} @media (max-width:900px){{.three,.six{{grid-template-columns:1fr}} h1{{font-size:30px}} h2{{font-size:26px}}}}</style></head><body>

<section class="s"><div class="in"><p class="k">1 ／ 5　なにをする仕組みか</p>
<h1>エンジン整備計画を、航空需要から意思決定まで一本でつなぐ</h1>
<p class="big">需要が便数を決め、便数が必要なエンジン数を決める。現場のデータで前提を毎月更新し、計算が計画を作り、人が決める。</p>
<div class="fig anim">{hero}</div></div></section>

<section class="s"><div class="in"><p class="k">2 ／ 5　なにが新しいか</p>
<h2>前提を一つの方法で決めない</h2>
<p class="big">同じ実績から 4 つの学習手法で前提を作り、統合してから計画を解く。前提が外れても壊れにくい計画になる。</p>
<div class="three">
<div><b>平均</b><span>全期間を等しく見る。標準。</span></div>
<div><b>直近重視・状況別</b><span>最近を重く見る手法と、状況が変わったら切り替える手法。</span></div>
<div><b>統合</b><span>4 つを単純平均して 1 組の前提に。ばらつきが大きい月は見直しの合図。年に 1 回、成績で来年の手法を決める。</span></div>
</div></div></section>

<section class="s"><div class="in"><p class="k">3 ／ 5　なにが出てくるか</p>
<h2>年に 1 回の 3 つと、毎月の 3 つ</h2>
<p class="big">上の帯が年に 1 回の版づくり、下の帯が毎月の補正。全部を統合レポート（A4）に綴じる。</p>
<div class="fig">{cyc}</div>
<p class="sub">① 年間見直し：過去の検証で予測の癖を補正し、来年の手法を決める　② 計画：最適化して 800 通りの将来で検証し凍結　③ 年次レポート：経営が承認<br>④ 月次見直し：実績を当ててシナリオの確率を更新　⑤ 計画修正：必要な月だけ（3 か月先の欠航率 5% 超など）　⑥ 月次レポート：経営向けの 1 枚</p></div></section>

<section class="s"><div class="in"><p class="k">4 ／ 5　どこで見るか</p>
<h2>用意してあるページ</h2>
<p class="big">入口はダッシュボード。数字の根拠は詳細レポート。配るのは統合レポート。</p>
<div class="six">
<a href="index.html"><b>ダッシュボード</b><span>年次と月次を暦に置き、KPI と不足の見張り、全ページへのリンク。</span><em>入口</em></a>
<a href="report.html"><b>詳細レポート</b><span>30 余りの画面。各図に「どう読むか・次にすること」の案内。</span><em>計画の中身と判断材料</em></a>
<a href="report_a4.html"><b>統合レポート（A4）</b><span>本文 1〜8 章＋付録。印刷して配る 1 冊。</span><em>①〜⑥ を綴じたもの</em></a>
<a href="annual.html"><b>年間計画レポート</b><span>年度ごとの入場・整備費・予算、10 年先の見通し。</span><em>③ 年次レポート</em></a>
<a href="monthly.html"><b>月次レポート</b><span>今月の判断期限、乗り換えの推奨、着地の更新。</span><em>⑥ 月次レポート</em></a>
<a href="track.html"><b>計画の追跡</b><span>実績と計画の差、シナリオの確率、乗り換えの価値。</span><em>④ 見直し・⑤ 修正</em></a>
</div></div></section>

<section class="s"><div class="in"><p class="k">5 ／ 5　仕組みの中身</p>
<h2>5 つの部門が、入力 → 処理 → 出力でつながる</h2>
<p class="big">航空計画・エンジン整備計画・MRO と調達・技術・データ。上の部門の決定が下へ渡り、下の部門の結果が上へ上がる。</p>
<a class="cta" href="strategy_grid.html">全体像の図を開く（行をクリックで詳細）</a><a class="cta alt" href="plan_basic.html">基本計画（年次）の図</a><a class="cta alt" href="plan_detail.html">詳細計画（月次）の図</a>
<p class="sub" style="margin-top:18px">参考：<a href="story.html">ストーリー</a>／<a href="appendix.html">付録（思考の枠組み・文献）</a>／<a href="design_strategy.html">概念設計</a>／<a href="requirements.html">要件と対応の記録</a></p></div></section>
<p class="foot">数値はすべて合成データの目安。実データは需要（e-Stat 航空輸送統計速報、各社月次資料）と型式の年表のみ。すべて run_all.sh 一発で入力データから作り直せる。</p>
</body></html>'''


def concept_grid_page() -> str:
    """A landing page: headline and the one-line story, three points, the six outputs over a
    year, the tools behind them, then the full grid (rows zoom into a detail panel), and the
    reference tables folded away at the end."""
    import json as _json
    svg = strategy_matrix(True, True)
    TABS = [("none", "基本の図", "行＝5 つの部門、列＝入力 → 処理 → 出力、右端＝得られる成果。太い深紅が推奨する流れ。行をクリックすると拡大し、詳細が右に出ます。"),
            ("ov-flight", "航空計画から導かれるもの", "便数が必要エンジン数を決める。便 1〜6 の札は、航空計画から導いた値を使う箱。"),
            ("ov-stage", "PDCA と OODA", "上 3 行（航空計画・整備計画・MRO）が PDCA、下 2 行（技術・データ）が OODA。列がそのまま段階。"),
            ("ov-output", "成果指標", "右端の各成果に目標を付ける。欠航率 5% 以下、予算との差 ±5% 以内、予測の的中率 80% 以上など（目安）。"),
            ("ov-ai", "何が働くか", "AI 支援ソルバー：計画を解くのは数理最適化とシミュレーション、前提を学ぶのは統計、残り寿命は機械学習、候補づくり・説明・振り分けは AI、決めるのは人。")]
    tabs = "".join(f'<button type="button" data-g="{g}" class="{"on" if g == "none" else ""}">{t}</button>' for g, t, _ in TABS)
    caps = "".join(f'<p class="cap" data-for="{g}" {"" if g == "none" else "hidden"}>{c}</p>' for g, _, c in TABS)
    details = _json.dumps(overview_details(), ensure_ascii=False)
    def _link(sc):
        parts = []
        for x in sc.split("／"):
            f = x.split("（")[0]; parts.append(f'<a href="{f}">{x}</a>' if f.endswith(".html") else x)
        return "／".join(parts)
    ORDER = ["annual_review", "plan", "annual_report", "monthly_review", "plan_revision", "monthly_report"]; NUM = "①②③④⑤⑥"
    by = {k: (k, n, w, who, what, src, sc, sec) for k, n, w, who, what, src, sc, sec in OUTPUTS}
    out_rows = "".join((lambda k, n, w, who, what, src, sc, sec, i: f"<tr><td><b>{NUM[i]} {n}</b></td><td>{w}</td><td>{who}</td><td>{what}</td><td>{_link(sc)}</td><td>{sec}</td></tr>")(*by[key], i) for i, key in enumerate(ORDER))
    cycle_svg = outputs_cycle()
    TOOLS = [("index.html", "ダッシュボード", "入口。年次の版と月次会議を暦に置き、KPI と不足の見張り、話題ごとの論点、すべてのページへのリンク。", "①〜⑥ の入口"),
             ("report.html", "詳細レポート（対話版）", "会社ごと・役割ごとに 30 余りの画面。各図に「何の図か・どう読むか・言えること・次にすること」の案内。", "計画の中身と判断材料"),
             ("report_a4.html", "統合レポート（A4・PDF）", "本文 1〜8 章＋付録。年次分と月次分を綴じた、印刷して配る 1 冊。", "①〜⑥ を綴じたもの"),
             ("annual.html", "年間計画レポート", "年度ごとの入場・整備費・予算と 10 年先の見通しを 1 画面に。", "③ 年次レポート"),
             ("monthly.html", "月次レポート", "今月の判断期限、乗り換えの推奨、着地の更新を 1 画面に。", "⑥ 月次レポート"),
             ("track.html", "計画の追跡", "実績と計画の差、シナリオの確率、乗り換えの価値と判断期限。", "④ 見直し・⑤ 修正")]
    tool_cards = "".join(f'<a class="card" href="{f}"><div class="ct">{t}</div><div class="cd">{d}</div><div class="cf">{tag}</div></a>' for f, t, d, tag in TOOLS)
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>エンジン整備計画の全体像</title>
<style>body{{margin:0;background:{BG};font-family:"IBM Plex Sans JP","Noto Sans JP",sans-serif;color:{INK}}}
.wrap{{max-width:1400px;margin:0 auto;padding:0 20px}} section{{padding:28px 0 18px;border-top:1px solid #e2e8f0}} section:first-of-type{{border-top:0}}
.kicker{{font-size:12px;letter-spacing:.14em;color:{PORT};font-weight:700;margin:0 0 6px}} h1{{font-size:30px;line-height:1.3;margin:0 0 10px}} h2{{font-size:21px;margin:0 0 6px}} .lead{{font-size:15px;line-height:1.75;margin:0 0 14px;max-width:1000px}}
.points{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:6px 0 4px}} .pt{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px}} .pt b{{display:block;font-size:14.5px;margin-bottom:4px}} .pt span{{font-size:13px;line-height:1.65;color:#334155}}
.hero svg,.cycle svg,.grid svg{{width:100%;height:auto;display:block}} .hero{{margin:10px 0 0}}
.explain{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 28px;font-size:13px;line-height:1.7;margin:10px 0 0}} .explain h3{{font-size:13.5px;margin:6px 0 2px;color:{HEAD}}} .explain p{{margin:0}}
.cards{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}} .card{{display:block;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;text-decoration:none;color:inherit}} .card:hover{{border-color:{PORT};box-shadow:0 2px 10px rgba(0,0,0,.06)}}
.ct{{font-size:15px;font-weight:700;margin-bottom:4px}} .cd{{font-size:12.5px;line-height:1.6;color:#334155}} .cf{{margin-top:8px;font-size:11.5px;color:{PORT};font-weight:700}}
.bar{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}} .bar button{{font:inherit;font-size:12.5px;padding:5px 11px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;cursor:pointer}} .bar button.on{{background:{HEAD};color:#fff;border-color:{HEAD}}}
.bar label{{margin-left:auto;font-size:12.5px;display:flex;gap:6px;align-items:center}} .cap{{margin:0 0 8px;padding:8px 12px;font-size:12.5px;background:#fff;border:1px solid #e2e8f0;border-radius:8px}}
.stage{{display:grid;grid-template-columns:1fr;gap:0}} .stage.open{{grid-template-columns:minmax(0,1fr) 420px}} .stage.open > div{{overflow-x:auto;padding:8px 0}} .stage.open svg{{height:300px;width:auto;max-width:none}}
.hide{{display:none}} g.row{{cursor:pointer}} g.row:hover rect:first-child{{stroke:{HEAD};stroke-width:2}}
.anim .flow{{stroke-dasharray:14 10;animation:dash 1.1s linear infinite}} .anim .flow.red{{stroke-dasharray:18 10;animation-duration:.6s;filter:drop-shadow(0 0 3px rgba(190,18,60,.6))}} .hero .flow{{stroke-dasharray:22 12}}
.anim .flow.dashed{{stroke-dasharray:7 5;animation-duration:1.6s}} .dot{{display:none}} .anim .dot{{display:inline}}
@keyframes dash{{to{{stroke-dashoffset:-24}}}} @media (prefers-reduced-motion: reduce){{.anim .flow{{animation:none}} .anim .dot{{display:none}}}}
#panel{{display:none;border-left:1px solid #e2e8f0;background:#fff;padding:16px 18px;font-size:13px;line-height:1.6;position:sticky;top:0;align-self:start;max-height:100vh;overflow:auto}} .stage.open #panel{{display:block}}
#panel h2{{font-size:16px;margin:0 0 2px}} #panel .cad{{color:{MUTE};font-size:12px;margin-bottom:10px}} #panel h3{{font-size:12.5px;margin:12px 0 4px;color:{HEAD};border-bottom:1px solid #e2e8f0;padding-bottom:2px}}
#panel ul{{margin:0;padding-left:16px}} #panel .lit{{color:{MUTE};font-size:11.5px}} #panel .chips span{{display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;border:1px solid #cbd5e1;border-radius:8px;font-size:11.5px}}
#panel a{{color:{PORT}}} #panel .close{{float:right;font:inherit;border:1px solid #cbd5e1;background:#fff;border-radius:6px;padding:2px 8px;cursor:pointer}}
.zoombar{{display:none;padding:6px 0;font-size:12.5px;color:{MUTE}}} .stage.open .zoombar{{display:block}} .zoombar button{{font:inherit;border:1px solid #cbd5e1;background:#fff;border-radius:6px;padding:2px 8px;cursor:pointer;margin-left:8px}}
details{{margin:8px 0}} summary{{cursor:pointer;font-weight:700;font-size:14px}} .outs{{border-collapse:collapse;width:100%;font-size:12.5px;margin:8px 0 10px}} .outs th,.outs td{{border:1px solid #e2e8f0;padding:5px 8px;text-align:left;vertical-align:top}} .outs th{{background:#f1f5f9}} .outs a{{color:{PORT}}}
.note{{font-size:12px;color:{MUTE};padding:14px 0 28px}} @media (max-width:900px){{.points,.cards,.explain{{grid-template-columns:1fr}} .stage.open{{grid-template-columns:1fr}}}}</style></head><body><div class="wrap">

<section><p class="kicker">737-800 / CFM56-7B　エンジン整備計画　合成データによる見本</p>
<h1>エンジン整備計画を、航空需要から意思決定まで一本でつなぐ</h1>
<p class="lead">航空需要から便の計画を立て、便の計画から必要なエンジン数を決め、現場のデータで前提を更新し、最適化とシミュレーションで計画を作り、意思決定者に「年度計画・購入計画・見直しの合図」を渡す。</p>
<div class="hero anim">{overview_hero()}</div>
<div class="points">
<div class="pt"><b>目標は上から下へ</b><span>需要が便数を決め、便数が必要エンジン数を決める。エンジン計画はそれに合わせる。</span></div>
<div class="pt"><b>前提は 4 つの手法で学び、統合する</b><span>一つの方法で決めず、平均・直近重視・状況別・混合の 4 手法で並行して学ぶ。前提が外れても壊れにくい計画になる。ここが新しい。</span></div>
<div class="pt"><b>計算が作り、人が決める</b><span>数理最適化とシミュレーションが計画を解き、AI が候補づくり・説明・振り分けを支援し、経営が承認する（AI 支援ソルバー）。</span></div>
</div></section>

<section><p class="kicker">成果物</p><h2>1 年で出るもの：年に 1 回の 3 つと、毎月の 3 つ</h2>
<p class="lead">上の帯が年に 1 回の版づくり、下の帯が毎月の補正。全部を統合レポート（A4）に綴じる。</p>
<div class="cycle">{cycle_svg}</div>
<div class="explain">
<div><h3>① 年間見直し（10 月、年 1 回）</h3><p>過去 8 版を当時の情報で解き直して予測の癖を補正値にし、4 手法の成績を採点して来年の手法を決める。需要の伸びも置き直す。</p>
<h3>② 計画（版）</h3><p>その前提で整備計画を最適化し（シナリオ 40 本）、800 通りの将来で検証して凍結。入場月・作業範囲・工場と、購入する手。</p>
<h3>③ 年次レポート</h3><p>② の経営向け要約。年度ごとの整備費と予算、欠航率、退役までの入場列、購入計画。ここで承認される。</p></div>
<div><h3>④ 月次見直し（毎月）</h3><p>実績を基準計画に当て、シナリオの確率を更新し、見直しの合図（ばらつき・変化点・需要の引き金）を出す。</p>
<h3>⑤ 計画修正（必要な月だけ）</h3><p>3 か月先の欠航率が 5% を超えそう、または乗り換えの価値が 2 か月続いたとき。乗り換え先・短期リース・動く基数の差分。大きな修正は次の版に戻す。</p>
<h3>⑥ 月次レポート</h3><p>今月の判断期限、乗り換えの推奨、3 か月先の見張り、年度の着地の更新。経営向けの 1 枚。</p></div>
</div></section>

<section><p class="kicker">道具</p><h2>これを支える 6 つのページ</h2>
<p class="lead">入口はダッシュボード。判断材料は詳細レポートに置き、印刷して配るのは統合レポート。すべて <code>run_all.sh</code> 一発で入力データから作り直せる。</p>
<div class="cards">{tool_cards}</div></section>

<section><p class="kicker">仕組み</p><h2>全体像：5 つの部門 × 入力・処理・出力、右端が得られる成果</h2>
<p class="lead">行は部門（航空計画・エンジン整備計画・MRO と調達・技術・データ）。行をクリックすると拡大し、右に詳細（全文・根拠の文献・成果指標・関連画面）が出る。</p>
<div class="bar"><b style="font-size:12.5px;margin-right:4px">見方：</b>{tabs}<label><input type="checkbox" id="anim" checked> 動き</label></div>
{caps}
<div class="zoombar">拡大中：<b id="zoomlabel"></b><button type="button" id="zoomout">全体に戻る</button><button type="button" id="prev">▲ 上の行</button><button type="button" id="next">▼ 下の行</button></div>
<div class="stage" id="stage"><div class="grid">{svg}</div><aside id="panel"></aside></div></section>

<section><p class="kicker">参考</p><h2>表と文書</h2>
<details><summary>成果物の一覧表（いつ・誰が・中身・画面・章）</summary><table class="outs"><thead><tr><th>成果物</th><th>いつ</th><th>誰が</th><th>中身</th><th>判断材料の画面</th><th>統合レポートの章</th></tr></thead><tbody>{out_rows}</tbody></table></details>
<details><summary>図と文書</summary><ul style="font-size:13px;line-height:1.9"><li>図：<a href="plan_basic.html">基本計画（年次、PDCA）</a>／<a href="plan_detail.html">詳細計画（月次、OODA）</a>／<a href="strategy_stack.html">分析ストラテジーの流れ</a></li>
<li>文書：<a href="story.html">ストーリー（需要から検証まで）</a>／<a href="appendix.html">付録（思考の枠組み・文献・シミュレーションの範囲）</a>／<a href="design_strategy.html">概念設計（分析ストラテジー）</a>／<a href="requirements.html">要件と対応の記録</a>／<a href="readme.html">README</a>／<a href="process.html">進め方</a>／<a href="practice.html">実務との距離</a></li>
<li>任意で足せる画面：条件を動かして打ち手の変化を見る画面（what-if）、承認／保留／差し戻しを共有する判断ルーム。今の一括生成には含めていない。</li></ul></details>
<p class="note">数値はすべて合成データの目安。実データは需要（e-Stat 航空輸送統計速報、各社月次資料）と型式の年表のみ。AI 層は API キーがあれば見直しの文章を生成し、なければ規則層に落ちる。</p></section>
</div>
<script>
const DET={details}; const G=["ov-flight","ov-stage","ov-output","ov-ai"];
const show=(g)=>{{G.forEach(x=>document.getElementById(x).classList.toggle("hide",x!==g)); document.querySelectorAll(".bar button").forEach(b=>b.classList.toggle("on",b.dataset.g===g)); document.querySelectorAll(".cap").forEach(c=>c.hidden=c.dataset.for!==g);}};
document.querySelectorAll(".bar button").forEach(b=>b.addEventListener("click",()=>show(b.dataset.g))); show("none");
const svgEl=document.querySelector(".grid svg"); const VB=svgEl.getAttribute("viewBox"); const W=+VB.split(" ")[2];
const setAnim=()=>{{const on=document.getElementById("anim").checked; svgEl.classList.toggle("anim",on); document.querySelector(".hero").classList.toggle("anim",on);}}; document.getElementById("anim").addEventListener("change",setAnim); setAnim();
const esc=(s)=>String(s).replace(/[&<>]/g,(c)=>({{"&":"&amp;","<":"&lt;",">":"&gt;"}}[c]));
let cur=-1;
function zoom(r){{ const g=document.querySelector(`g.row[data-row="${{r}}"]`); if(!g) return; cur=r; const y0=+g.dataset.y0, y1=+g.dataset.y1;
  svgEl.setAttribute("viewBox",`0 ${{y0}} ${{W}} ${{y1-y0}}`); svgEl.setAttribute("preserveAspectRatio","xMinYMin meet"); document.getElementById("stage").classList.add("open"); document.getElementById("zoomlabel").textContent=DET[r].label;
  const d=DET[r]; const li=(a)=>a.map((x)=>`<li>${{esc(x)}}</li>`).join("");
  document.getElementById("panel").innerHTML=`<button type="button" class="close" id="close">閉じる</button><h2>${{esc(d.label)}}</h2><div class="cad">${{esc(d.cadence)}}　｜　段階：${{d.stage.filter(x=>x!=="—").map(esc).join(" → ")}}</div>
   <h3>入力：${{esc(d.input.title)}}</h3><ul>${{li(d.input.lines)}}</ul>
   <h3>処理：${{esc(d.process.title)}}</h3><ul>${{li(d.process.lines)}}</ul>${{d.process.lit?`<div class="lit">根拠：${{esc(d.process.lit)}}</div>`:""}}
   <h3>出力：${{esc(d.output.title)}}</h3><ul>${{li(d.output.lines)}}</ul>
   <h3>得られる成果：${{esc(d.result.title)}}</h3><ul>${{li(d.result.lines)}}</ul>
   <h3>成果指標（目標）</h3><div class="chips">${{d.kpi.map(k=>`<span>${{esc(k)}}</span>`).join("")}}</div>
   ${{d.flight.length?`<h3>航空計画から導かれるもの</h3><ul>${{li(d.flight)}}</ul>`:""}}
   <h3>何が働くか</h3><div class="chips">${{d.works.map(k=>`<span>${{esc(k)}}</span>`).join("")}}</div>
   <h3>詳しく見る（詳細レポート）</h3><ul>${{d.links.map(([k,l])=>`<li><a href="report.html#co=0&v=${{k}}">${{esc(l)}}</a></li>`).join("")}}<li><a href="plan_basic.html">図：基本計画（年次）</a> ／ <a href="plan_detail.html">図：詳細計画（月次）</a></li></ul>`;
  document.getElementById("close").onclick=reset; }}
function reset(){{ cur=-1; svgEl.setAttribute("viewBox",VB); document.getElementById("stage").classList.remove("open"); }}
document.querySelectorAll("g.row").forEach(g=>g.addEventListener("click",()=>zoom(+g.dataset.row)));
document.getElementById("zoomout").onclick=reset; document.getElementById("prev").onclick=()=>zoom(Math.max(0,cur-1)); document.getElementById("next").onclick=()=>zoom(Math.min(DET.length-1,cur+1));
</script></body></html>'''


def page(svg: str, title: str) -> str:
    return f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>{title}</title><style>body{{margin:0;background:{BG}}}svg{{display:block;max-width:100%;height:auto}}</style></head><body>{svg}</body></html>'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=Path("out"))
    a = ap.parse_args(argv)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / "strategy_concept.html").write_text(concept_page(), encoding="utf-8")
    (a.out_dir / "strategy_grid.html").write_text(concept_grid_page(), encoding="utf-8")
    for k, s in {**svgs(), **extra_svgs()}.items():
        (a.out_dir / f"{k}.html").write_text(page(s, {"plan_basic": "基本計画（年次〜半期）", "plan_detail": "詳細計画（月次〜当日）", "strategy_stack": "あるべき分析ストラテジー（流れ）", "strategy_matrix": "あるべき分析ストラテジー（層 × 流れ）"}[k]), encoding="utf-8")
        print(f"{k} -> {a.out_dir / f'{k}.html'} ({len(s) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
