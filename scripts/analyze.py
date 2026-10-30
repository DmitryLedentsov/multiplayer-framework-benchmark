#!/usr/bin/env python3
from __future__ import annotations
import csv,json,math,random,statistics,sys
from collections import defaultdict
from pathlib import Path
THRESHOLDS={"stepP99Ms":10.0,"actionP99Ms":30.0,"maxRejectionRate":0.001,"minTickFraction":0.98,"maxBacklogGrowthActionsPerSecond":1.0}
def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def median_ci(values,seed,rounds=4000):
    if not values:return (0.0,0.0)
    if len(values)==1:return (values[0],values[0])
    rng=random.Random(seed); m=[]; n=len(values)
    for _ in range(rounds):m.append(statistics.median([values[rng.randrange(n)] for __ in range(n)]))
    m.sort();return m[int(.025*(rounds-1))],m[int(.975*(rounds-1))]
def backlog_slope(path,last_n=30):
    p=Path(path)
    if not p.exists():return 0.0
    rows=list(csv.DictReader(p.open(encoding='utf-8')))[-last_n:]
    if len(rows)<2:return 0.0
    xs=[float(r['elapsed_s']) for r in rows];ys=[float(r['backlog']) for r in rows];xb=statistics.mean(xs);yb=statistics.mean(ys);d=sum((x-xb)**2 for x in xs)
    return 0.0 if d==0 else sum((x-xb)*(y-yb) for x,y in zip(xs,ys))/d
def load_runs(root):
    out=[]
    for sp in sorted((root/'runs').glob('*/summary.json')):
        d=read_json(sp)
        if d.get('status')!='completed':continue
        c=d['config'];m=d['metrics'];slope=backlog_slope(sp.parent/'samples.csv');rr=m['rejectedActions']/m['offeredActions'] if m['offeredActions'] else 0.;exp=c['sessions']*c['tickRate'];tf=m['stepsPerSecond']/exp if exp else 1.;sus=m['stepP99Ms']<10 and m['actionP99Ms']<30 and rr<=.001 and tf>=.98 and slope<=1
        out.append({'runtime':d['runtime'],'sessions':c['sessions'],'repetition':int(sp.parent.name.rsplit('-r',1)[-1]),'actionP99Ms':m['actionP99Ms'],'stepP99Ms':m['stepP99Ms'],'cpuPercent':m['processCpuPercent'],'generatorCpuPercent':float(d.get('generatorCpuPercent',-1.0)),'actionsPerSecond':m['actionsPerSecond'],'rejectionRate':rr,'tickFraction':tf,'backlogSlope':slope,'sustained':sus})
    return out
def group_runs(runs,seed):
    g=defaultdict(list)
    for r in runs:g[(r['runtime'],r['sessions'])].append(r)
    out=[]
    for idx,((runtime,sessions),rows) in enumerate(sorted(g.items())):
        vals=lambda k:[float(r[k]) for r in rows];a=vals('actionP99Ms');s=vals('stepP99Ms');cpu=vals('cpuPercent');gen=vals('generatorCpuPercent');t=vals('actionsPerSecond')
        out.append({'runtime':runtime,'sessions':sessions,'n':len(rows),'actionP99Median':statistics.median(a),'actionP99Min':min(a),'actionP99Max':max(a),'actionP99Ci95':median_ci(a,seed+idx*11+1),'stepP99Median':statistics.median(s),'stepP99Min':min(s),'stepP99Max':max(s),'stepP99Ci95':median_ci(s,seed+idx*11+2),'cpuMedian':statistics.median(cpu),'cpuMin':min(cpu),'cpuMax':max(cpu),'cpuCi95':median_ci(cpu,seed+idx*11+3),'generatorCpuMedian':statistics.median(gen),'actionsPerSecondMedian':statistics.median(t),'actionsPerSecondMin':min(t),'actionsPerSecondMax':max(t),'actionsPerSecondCi95':median_ci(t,seed+idx*11+4),'rejectionRateMedian':statistics.median(vals('rejectionRate')),'tickFractionMedian':statistics.median(vals('tickFraction')),'backlogSlopeMedian':statistics.median(vals('backlogSlope')),'sustainedRuns':sum(r['sustained'] for r in rows),'sustained':sum(r['sustained'] for r in rows)>=math.ceil(len(rows)/2)})
    return out
def write_csv(path,groups):
    fields=['runtime','sessions','n','actionP99Median','actionP99Min','actionP99Max','stepP99Median','stepP99Min','stepP99Max','cpuMedian','cpuMin','cpuMax','generatorCpuMedian','actionsPerSecondMedian','actionsPerSecondMin','actionsPerSecondMax','rejectionRateMedian','tickFractionMedian','backlogSlopeMedian','sustainedRuns','sustained']
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();[w.writerow({k:g[k] for k in fields}) for g in groups]
def permutation_p(values,seed,rounds=10000):
    if len(values)<4:return None
    split=len(values)//2;a,b=values[:split],values[split:];obs=abs(statistics.median(a)-statistics.median(b));p=values[:];rng=random.Random(seed);ext=0
    for _ in range(rounds):rng.shuffle(p);ext+=abs(statistics.median(p[:split])-statistics.median(p[split:]))>=obs
    return (ext+1)/(rounds+1)
def aa_analysis(runs,seed):
    if len({(r['runtime'],r['sessions']) for r in runs})!=1 or len(runs)<5:return None
    o=sorted(runs,key=lambda x:x['repetition']);return {'method':'split repetitions into two halves; two-sided permutation test of median difference','stepP99PermutationP':permutation_p([r['stepP99Ms'] for r in o],seed),'actionP99PermutationP':permutation_p([r['actionP99Ms'] for r in o],seed+1),'cpuPermutationP':permutation_p([r['cpuPercent'] for r in o],seed+2)}
def main():
    if len(sys.argv)!=2:return 2
    root=Path(sys.argv[1]);manifest=read_json(root/'manifest.json');seed=int(manifest.get('request',{}).get('order_seed',20261105));runs=load_runs(root);groups=group_runs(runs,seed);analysis={'schemaVersion':1,'sustainThresholds':THRESHOLDS,'unitOfAnalysis':'one independently restarted JVM run','aggregation':'median with min-max and deterministic bootstrap 95% CI','runs':runs,'groups':groups,'aa':aa_analysis(runs,seed)};(root/'analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding='utf-8');write_csv(root/'analysis.csv',groups);return 0
if __name__=='__main__':raise SystemExit(main())
