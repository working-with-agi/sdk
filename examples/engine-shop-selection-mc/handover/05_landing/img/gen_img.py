import math, random
S="/tmp/claude-0/-home-user/a52bb465-9187-5eca-9ca8-d957904d8eca/scratchpad/landing/img"
W,H=880,520; INK="#f6f4ee"; MUTE="#8f8b80"; BG="#1c1b1a"; A="#7fa3d1"; G="#8fc9a0"; O="#e0a96d"; R="#d97b6c"
random.seed(7)
def wrap(body,name):
    open(f"{S}/{name}.html","w").write(f'<!doctype html><html><head><meta charset="utf-8"><style>body{{margin:0;background:{BG}}}</style></head><body><svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Noto Sans JP, sans-serif">{body}</svg></body></html>')
# 1 航空計画: seasonal flights per day (bars) with required engines line
o=[f'<rect width="{W}" height="{H}" fill="{BG}"/>']
months=["10","11","12","1","2","3","4","5","6","7","8","9"]; idx=[0.93,0.93,1.10,0.92,1.00,0.92,1.01,1.17,1.03,1.09,1.03,0.97]
for i,(m,v) in enumerate(zip(months,idx)):
    x=90+i*62; h=v*240; o.append(f'<rect x="{x}" y="{400-h}" width="40" height="{h}" rx="4" fill="{A}" opacity="0.9"/>'); o.append(f'<text x="{x+20}" y="430" font-size="14" fill="{MUTE}" text-anchor="middle">{m}月</text>')
pts=" ".join(f"{90+i*62+20},{400-v*240-40}" for i,v in enumerate(idx)); o.append(f'<polyline points="{pts}" fill="none" stroke="{O}" stroke-width="4" stroke-linejoin="round"/>')
o.append(f'<text x="60" y="60" font-size="22" fill="{INK}" font-weight="700">便数（季節の波）</text><text x="60" y="88" font-size="15" fill="{O}">必要エンジン数 ＝ 飛ぶ機数 × 2 − 整備で止まる機</text>')
wrap("".join(o),"flight")
# 2 整備計画: gantt of engines with shop windows
o=[f'<rect width="{W}" height="{H}" fill="{BG}"/>',f'<text x="60" y="60" font-size="22" fill="{INK}" font-weight="700">入場計画（エンジンごと）</text><text x="60" y="88" font-size="15" fill="{MUTE}">薄い帯＝下ろしてよい期間、濃い棒＝工場に入ってから戻るまで</text>']
for r in range(9):
    y=120+r*40; s=random.randint(0,14); w=random.randint(6,10); d=random.randint(2,4)
    o.append(f'<text x="60" y="{y+16}" font-size="13" fill="{MUTE}">J-{101+r*7}</text>')
    o.append(f'<rect x="{150+s*45}" y="{y}" width="{w*45}" height="22" rx="4" fill="{A}" opacity="0.25"/>')
    o.append(f'<rect x="{150+(s+2)*45}" y="{y}" width="{d*45}" height="22" rx="4" fill="{[A,G,O][r%3]}"/>')
    o.append(f'<path d="M {150+(s+2)*45-70} {y+11} l 7 -7 l 7 7 l -7 7 z" fill="{R}"/>')
for i in range(0,25,3): o.append(f'<line x1="{150+i*30}" y1="110" x2="{150+i*30}" y2="480" stroke="{MUTE}" stroke-opacity="0.25"/>')
wrap("".join(o),"plan")
# 3 MRO: shop capacity vs load bars by month
o=[f'<rect width="{W}" height="{H}" fill="{BG}"/>',f'<text x="60" y="60" font-size="22" fill="{INK}" font-weight="700">工場の枠と入場の数</text><text x="60" y="88" font-size="15" fill="{MUTE}">枠（点線）を超えた月は、次の月へ押し出される</text>']
cap=[10,10,10,10,10,12,12,12,12,12,12,12]; load=[9,10,10,8,7,11,9,12,13,11,8,9]
for i,(c,l) in enumerate(zip(cap,load)):
    x=90+i*62; o.append(f'<rect x="{x}" y="{400-l*24}" width="40" height="{l*24}" rx="4" fill="{R if l>c else A}"/>'); o.append(f'<line x1="{x-6}" y1="{400-c*24}" x2="{x+46}" y2="{400-c*24}" stroke="{INK}" stroke-width="3" stroke-dasharray="6 4"/>'); o.append(f'<text x="{x+20}" y="430" font-size="14" fill="{MUTE}" text-anchor="middle">{months[i]}月</text>')
o.append(f'<text x="60" y="470" font-size="14" fill="{MUTE}">部品（LLP キット）の納期回答：8 か月 → 12 か月に延びた月から、赤が増える</text>')
wrap("".join(o),"mro")
# 4 技術: four learning curves converging + band
o=[f'<rect width="{W}" height="{H}" fill="{BG}"/>',f'<text x="60" y="60" font-size="22" fill="{INK}" font-weight="700">4 つの手法で学んだ前提と、そのばらつき</text><text x="60" y="88" font-size="15" fill="{MUTE}">線＝手法ごとの推定、帯＝ばらつき。帯が広い月は見直しの合図</text>']
base=[0.9,0.95,1.0,1.02,1.05,1.12,1.25,1.3,1.28,1.2,1.15,1.1]
cols=[A,G,O,INK]; offs=[0.0,0.04,-0.05,0.02]
xs=[110+i*62 for i in range(12)]
top=[]; bot=[]
for i,b in enumerate(base):
    vals=[b+off*(1+ (i>=5)*2) for off in offs]; top.append(max(vals)); bot.append(min(vals))
poly=" ".join(f"{x},{420-t*220}" for x,t in zip(xs,top))+" "+" ".join(f"{x},{420-b*220}" for x,b in zip(reversed(xs),reversed(bot)))
o.append(f'<polygon points="{poly}" fill="{R}" opacity="0.18"/>')
for k,(c,off) in enumerate(zip(cols,offs)):
    pts=" ".join(f"{x},{420-(b+off*(1+(i>=5)*2))*220}" for i,(x,b) in enumerate(zip(xs,base)))
    o.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="3"/>')
for i,x in enumerate(xs): o.append(f'<text x="{x}" y="450" font-size="14" fill="{MUTE}" text-anchor="middle">{months[i]}月</text>')
o.append(f'<rect x="{xs[6]-25}" y="{420-1.45*220}" width="{xs[9]-xs[6]+50}" height="{1.45*220-0.95*220}" fill="none" stroke="{R}" stroke-width="2" stroke-dasharray="8 5"/><text x="{xs[7]+31}" y="{420-0.95*220+22}" font-size="15" fill="{R}" text-anchor="middle" font-weight="700">見直しの合図</text>')
wrap("".join(o),"tech")
# 5 データ: sensor time series with anomaly
o=[f'<rect width="{W}" height="{H}" fill="{BG}"/>',f'<text x="60" y="60" font-size="22" fill="{INK}" font-weight="700">便ごとの排気温度（整えた時系列）</text><text x="60" y="88" font-size="15" fill="{MUTE}">欠けを補い、時刻を揃え、しきい値と傾きで異常の候補を拾う</text>']
pts=[]; 
for i in range(120):
    x=70+i*6.3; v=0.5+0.02*math.sin(i/5)+random.gauss(0,0.012)+(0.0015*i if i>70 else 0)
    pts.append((x,400-v*380))
o.append(f'<polyline points="{" ".join(f"{x:.0f},{y:.0f}" for x,y in pts)}" fill="none" stroke="{G}" stroke-width="2.5"/>')
o.append(f'<line x1="70" y1="{400-0.62*380}" x2="830" y2="{400-0.62*380}" stroke="{R}" stroke-width="2" stroke-dasharray="6 4"/><text x="830" y="{400-0.62*380-8}" font-size="13" fill="{R}" text-anchor="end">しきい値</text>')
for x,y in pts[100:115:3]: o.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="6" fill="none" stroke="{R}" stroke-width="2"/>')
o.append(f'<text x="60" y="460" font-size="14" fill="{MUTE}">機上センサー・部品の使用回数・工場の進捗・納期回答・運航の記録</text>')
wrap("".join(o),"data")
print("ok")
