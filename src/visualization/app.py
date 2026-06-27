"""
Flask 可视化服务 - D3.js知识图谱
"""
import os, sys
import logging
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)

from flask import Flask, jsonify, Response
from config import FLASK_HOST, FLASK_PORT, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

app = Flask(__name__)

_NOISY_PATH_PREFIXES = (
    "GET /hybridaction/",
    "POST /hybridaction/",
)


class IgnoreNoisyRequestFilter(logging.Filter):
    """过滤浏览器/插件注入的无关请求日志"""

    def filter(self, record):
        message = record.getMessage()
        return not any(prefix in message for prefix in _NOISY_PATH_PREFIXES)


def configure_werkzeug_logging():
    logger = logging.getLogger("werkzeug")
    if getattr(logger, "_tololo_noise_filter_installed", False):
        return
    logger.addFilter(IgnoreNoisyRequestFilter())
    logger._tololo_noise_filter_installed = True


def get_graph():
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        nodes = {}
        links = []
        with driver.session() as s:
            node_rows = s.run(
                "MATCH (n) "
                "WHERE n.name IS NOT NULL "
                "RETURN toString(id(n)) AS id, n.name AS name, labels(n) AS labels"
            )
            for row in node_rows:
                node_id = row["id"]
                node_name = row["name"]
                labels = row["labels"] or []
                if not node_id or not node_name:
                    continue
                nodes[node_id] = {
                    "id": node_id,
                    "nm": node_name,
                    "g": labels[0] if labels else "Entity",
                }

            link_rows = s.run(
                "MATCH (a)-[r]->(b) "
                "WHERE a.name IS NOT NULL AND b.name IS NOT NULL "
                "RETURN toString(id(a)) AS source, toString(id(b)) AS target, type(r) AS rel"
            )
            for row in link_rows:
                src = row["source"]
                tgt = row["target"]
                if src in nodes and tgt in nodes:
                    links.append({
                        "source": src,
                        "target": tgt,
                        "r": row["rel"] or "",
                    })
        driver.close()
        return {
            'n': list(nodes.values()),
            'l': links,
            'meta': {
                'node_count': len(nodes),
                'rel_count': len(links),
            },
        }
    except Exception as e:
        return {'n': [], 'l': [], 'err': str(e)}


@app.route('/api/graph')
def api():
    return jsonify(get_graph())


@app.route('/hybridaction/<path:_subpath>', methods=['GET', 'POST'])
def ignore_hybridaction(_subpath):
    return Response(status=204)


@app.route('/')
def index():
    return HTML


def run():
    configure_werkzeug_logging()
    print(f"[可视化] http://{FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False)


HTML = r'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>托洛洛Agent - 知识图谱</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1e1e1e;overflow:hidden;font-family:Microsoft YaHei,sans-serif}
#h{position:fixed;top:0;left:0;right:0;background:rgba(30,30,30,.95);padding:10px 20px;border-bottom:1px solid #333;display:flex;align-items:center;z-index:10;height:48px}
#h h1{color:#4fc3f7;font-size:16px;margin:0}
#h .i{color:#aaa;font-size:12px;margin-left:20px}
#h .i span{color:#4fc3f7;margin:0 3px}
#toggle-btn{position:fixed;top:56px;left:10px;z-index:20;background:rgba(30,30,30,.95);color:#4fc3f7;border:1px solid #4fc3f7;border-radius:4px;padding:6px 12px;cursor:pointer;font-size:13px}
#toggle-btn:hover{background:#4fc3f7;color:#1e1e1e}
svg{display:block;width:100vw;height:100vh}
#ctrl{position:fixed;top:56px;left:10px;z-index:15;background:rgba(30,30,30,.97);border:1px solid #444;border-radius:6px;padding:14px 16px;width:280px;color:#ccc;font-size:13px;display:none;max-height:calc(100vh - 70px);overflow-y:auto}
#ctrl h3{color:#4fc3f7;font-size:14px;margin-bottom:10px;border-bottom:1px solid #333;padding-bottom:6px}
#ctrl .grp{margin-bottom:12px}
#ctrl .grp label{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;font-size:12px}
#ctrl .grp .v{color:#4fc3f7}
#ctrl input[type=range]{width:100%;accent-color:#4fc3f7;height:4px;cursor:pointer}
#ctrl input[type=text]{width:100%;padding:7px 8px;border-radius:4px;border:1px solid #444;background:#101214;color:#ddd;outline:none}
#ctrl input[type=text]:focus{border-color:#4fc3f7}
#ctrl .check-row{display:flex;align-items:center;gap:8px;font-size:12px;margin-top:6px}
#ctrl .clr-row{display:flex;align-items:center;gap:8px;margin:4px 0}
#ctrl .clr-row input[type=color]{width:32px;height:24px;border:none;background:transparent;cursor:pointer}
#ctrl .clr-row span{font-size:12px}
#ctrl .actions{display:flex;gap:8px;margin-top:8px}
#ctrl button{flex:1;background:#4fc3f7;color:#1e1e1e;border:none;border-radius:4px;padding:7px 8px;cursor:pointer;font-size:13px;font-weight:bold}
#ctrl button.alt{background:#2b3137;color:#cfd8dc;border:1px solid #455a64}
#ctrl button:hover{opacity:.92}
#labels{max-height:180px;overflow-y:auto;border:1px solid #333;border-radius:4px;padding:8px;background:#16181b}
#labels .label-row{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px;padding:2px 0}
#labels .label-row span{color:#9fb3bf}
#leg{position:fixed;bottom:20px;right:20px;background:rgba(30,30,30,.95);padding:12px;border-radius:6px;border:1px solid #333;z-index:10;color:#ccc;font-size:12px;max-height:70vh;overflow-y:auto}
#leg .r{margin:4px 0;display:flex;align-items:center}
#leg .d{width:12px;height:12px;border-radius:50%;margin-right:8px;flex-shrink:0}
#tip{position:fixed;background:rgba(0,0,0,.9);color:#fff;padding:8px 12px;border-radius:4px;font-size:13px;display:none;z-index:100;max-width:360px;border:1px solid #4fc3f7;pointer-events:none;line-height:1.45}
#load{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);color:#4fc3f7;font-size:18px;z-index:5}
</style></head>
<body>
<div id=h>
  <h1>托洛洛Agent - 知识图谱</h1>
  <div class=i>显示节点: <span id=nc>-</span>/<span id=nct>-</span> | 显示关系: <span id=rc>-</span>/<span id=rct>-</span></div>
</div>
<button id=toggle-btn>⚙ 控制面板</button>
<div id=tip></div><div id=leg></div><div id=load>加载中...</div>
<svg id=G></svg>
<div id=ctrl>
  <h3>⚙ 显示控制</h3>
  <div class=grp>
    <label>搜索节点</label>
    <input type=text id=searchBox placeholder="按名称过滤">
  </div>
  <div class=grp>
    <label>最小连接数 <span class=v id=vminDeg>0</span></label>
    <input type=range id=minDegree min=0 max=20 value=0>
  </div>
  <div class=grp>
    <label>节点上限 <span class=v id=vNodeLimit>全部</span></label>
    <input type=range id=nodeLimit min=1 max=1 value=1>
  </div>
  <div class=grp>
    <label>关系上限 <span class=v id=vRelLimit>全部</span></label>
    <input type=range id=relLimit min=1 max=1 value=1>
  </div>
  <div class="grp check-row">
    <input type=checkbox id=showIsolated checked>
    <label for=showIsolated style="margin:0">显示孤立节点</label>
  </div>
  <div class=grp>
    <label>标签筛选</label>
    <div id=labels></div>
  </div>
  <div class=grp>
    <label>连线距离 <span class=v id=vd>120</span></label>
    <input type=range id=linkD min=30 max=400 value=120>
  </div>
  <div class=grp>
    <label>节点斥力 <span class=v id=vc>400</span></label>
    <input type=range id=charge min=50 max=1500 value=400>
  </div>
  <div class=grp>
    <label>碰撞半径 <span class=v id=vcol>35</span></label>
    <input type=range id=collide min=5 max=80 value=35>
  </div>
  <div class=grp>
    <label>字体大小 <span class=v id=vfs>12</span></label>
    <input type=range id=fontS min=6 max=28 value=12>
  </div>
  <div class=grp>
    <label>节点大小 <span class=v id=vnr>5</span></label>
    <input type=range id=nodeR min=2 max=12 value=5>
  </div>
  <div class=grp>
    <label>标签偏移 <span class=v id=vdx>15</span></label>
    <input type=range id=labelDX min=5 max=40 value=15>
  </div>
  <div class=grp style=margin-bottom:8px>
    <div class=clr-row><input type=color id=bgClr value=#1e1e1e><span>背景色</span></div>
    <div class=clr-row><input type=color id=lineClr value=#7f8c8d><span>连线色</span></div>
    <div class=clr-row><input type=color id=textClr value=#dddddd><span>文字色</span></div>
    <div class=clr-row><input type=color id=strokeClr value=#ffffff><span>描边色</span></div>
  </div>
  <div class=actions>
    <button id=apply-btn>应用筛选</button>
    <button id=reset-btn class=alt>重置筛选</button>
  </div>
</div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
var W=innerWidth,H=innerHeight,S=d3.select('#G'),g,sim,nd,lk;
var sourceData=null,graphData=null,lastTransform=d3.zoomIdentity,labelCounts={},maxDegree=0;

var zoom=d3.zoom().scaleExtent([0.1,8]).on('zoom',function(e){
  lastTransform=e.transform;
  if(g)g.attr('transform',e.transform);
});

function initZoom(){
  S.call(zoom);
}

var C={Planet:'#4fc3f7',Star:'#ffd54f',Satellite:'#81c784',CelestialBody:'#64b5f6',Mission:'#ff8a65',Asteroid:'#a1887f',Comet:'#fff176',DwarfPlanet:'#ce93d8',Entity:'#78909c',Concept:'#ef9a9a',PlanetType:'#80cbc4',OrbitParameter:'#b39ddb',EnvironmentalFeature:'#ffcc80'};

function getOpts(){
  return {
    search: document.getElementById('searchBox').value.trim().toLowerCase(),
    minDegree: +document.getElementById('minDegree').value,
    nodeLimit: +document.getElementById('nodeLimit').value,
    relLimit: +document.getElementById('relLimit').value,
    showIsolated: document.getElementById('showIsolated').checked,
    linkD: +document.getElementById('linkD').value,
    charge: +document.getElementById('charge').value,
    collide: +document.getElementById('collide').value,
    fontS: +document.getElementById('fontS').value,
    nodeR: +document.getElementById('nodeR').value,
    labelDX: +document.getElementById('labelDX').value,
    bgClr: document.getElementById('bgClr').value,
    lineClr: document.getElementById('lineClr').value,
    textClr: document.getElementById('textClr').value,
    strokeClr: document.getElementById('strokeClr').value
  };
}

function updateLabels(){
  document.getElementById('vd').textContent=document.getElementById('linkD').value;
  document.getElementById('vc').textContent=document.getElementById('charge').value;
  document.getElementById('vcol').textContent=document.getElementById('collide').value;
  document.getElementById('vfs').textContent=document.getElementById('fontS').value;
  document.getElementById('vnr').textContent=document.getElementById('nodeR').value;
  document.getElementById('vdx').textContent=document.getElementById('labelDX').value;
  document.getElementById('vminDeg').textContent=document.getElementById('minDegree').value;
  document.getElementById('vNodeLimit').textContent=formatLimitLabel('nodeLimit', sourceData ? sourceData.n.length : 0);
  document.getElementById('vRelLimit').textContent=formatLimitLabel('relLimit', sourceData ? sourceData.l.length : 0);
}

function formatLimitLabel(id,total){
  var value=+document.getElementById(id).value;
  return value>=total ? '全部' : String(value);
}

function applyColors(opts){
  document.body.style.background=opts.bgClr;
  if(lk)lk.attr('stroke',opts.lineClr).attr('stroke-opacity',0.22);
  if(nd){
    nd.selectAll('text').style('fill',opts.textClr);
    nd.selectAll('circle').attr('stroke',opts.strokeClr);
  }
}

function prepareSourceData(d){
  sourceData={n:d.n||[],l:d.l||[]};
  var deg={};
  labelCounts={};
  sourceData.n.forEach(function(n){
    deg[n.id]=0;
    labelCounts[n.g]=(labelCounts[n.g]||0)+1;
  });
  sourceData.l.forEach(function(l){
    if(deg[l.source]!==undefined)deg[l.source]++;
    if(deg[l.target]!==undefined)deg[l.target]++;
  });
  maxDegree=0;
  sourceData.n.forEach(function(n){
    n.dg=deg[n.id]||0;
    if(n.dg>maxDegree)maxDegree=n.dg;
  });
}

function setupControls(){
  buildLabelFilters();

  var nodeLimit=document.getElementById('nodeLimit');
  nodeLimit.min=1;
  nodeLimit.max=Math.max(1,sourceData.n.length);
  nodeLimit.value=Math.max(1,sourceData.n.length);

  var relLimit=document.getElementById('relLimit');
  relLimit.min=1;
  relLimit.max=Math.max(1,sourceData.l.length);
  relLimit.value=Math.max(1,sourceData.l.length);

  var minDegree=document.getElementById('minDegree');
  minDegree.max=Math.max(1,Math.min(50,maxDegree));
  minDegree.value=0;

  updateLabels();
}

function buildLabelFilters(){
  var labels=Object.keys(labelCounts).sort(function(a,b){return (labelCounts[b]||0)-(labelCounts[a]||0) || a.localeCompare(b)});
  var box=document.getElementById('labels');
  box.innerHTML='';
  labels.forEach(function(label){
    var row=document.createElement('div');
    row.className='label-row';

    var left=document.createElement('label');
    left.style.display='flex';
    left.style.alignItems='center';
    left.style.gap='8px';
    left.style.margin='0';

    var cb=document.createElement('input');
    cb.type='checkbox';
    cb.checked=true;
    cb.value=label;
    cb.className='label-filter';

    var dot=document.createElement('span');
    dot.style.width='10px';
    dot.style.height='10px';
    dot.style.borderRadius='50%';
    dot.style.display='inline-block';
    dot.style.background=C[label]||'#90a4ae';

    var txt=document.createElement('span');
    txt.textContent=label;

    left.appendChild(cb);
    left.appendChild(dot);
    left.appendChild(txt);

    var count=document.createElement('span');
    count.textContent=labelCounts[label];

    row.appendChild(left);
    row.appendChild(count);
    box.appendChild(row);
  });
}

function getSelectedLabels(){
  var selected={};
  document.querySelectorAll('.label-filter').forEach(function(el){
    if(el.checked)selected[el.value]=true;
  });
  return selected;
}

function updateHeader(nodeShown,relShown){
  var totalNodes=sourceData ? sourceData.n.length : 0;
  var totalRels=sourceData ? sourceData.l.length : 0;
  document.getElementById('nc').textContent=nodeShown;
  document.getElementById('rc').textContent=relShown;
  document.getElementById('nct').textContent=totalNodes;
  document.getElementById('rct').textContent=totalRels;
}

function updateLegend(nodes){
  var leg=document.getElementById('leg');
  leg.innerHTML='';
  var counts={};
  nodes.forEach(function(n){counts[n.g]=(counts[n.g]||0)+1});
  Object.keys(counts).sort(function(a,b){return counts[b]-counts[a] || a.localeCompare(b)}).forEach(function(label){
    var r=document.createElement('div');r.className='r';
    var d=document.createElement('span');d.className='d';d.style.background=C[label]||'#90a4ae';
    r.appendChild(d);
    r.appendChild(document.createTextNode(label+' ('+counts[label]+')'));
    leg.appendChild(r);
  });
}

function buildFilteredGraph(){
  if(!sourceData)return;

  var opts=getOpts();
  var selectedLabels=getSelectedLabels();

  var filteredNodes=sourceData.n.filter(function(n){
    if(!selectedLabels[n.g])return false;
    if(n.dg<opts.minDegree)return false;
    if(opts.search && n.nm.toLowerCase().indexOf(opts.search)===-1)return false;
    return true;
  });

  filteredNodes.sort(function(a,b){
    return (b.dg-a.dg) || a.nm.localeCompare(b.nm);
  });

  if(opts.nodeLimit<filteredNodes.length){
    filteredNodes=filteredNodes.slice(0,opts.nodeLimit);
  }

  var allowed={};
  filteredNodes.forEach(function(n){allowed[n.id]=true});

  var filteredLinks=sourceData.l.filter(function(l){
    return allowed[l.source] && allowed[l.target];
  });

  filteredLinks.sort(function(a,b){
    var aw=(sourceNodeDegree(a.source)+sourceNodeDegree(a.target));
    var bw=(sourceNodeDegree(b.source)+sourceNodeDegree(b.target));
    return bw-aw;
  });

  if(opts.relLimit<filteredLinks.length){
    filteredLinks=filteredLinks.slice(0,opts.relLimit);
  }

  if(!opts.showIsolated){
    var linked={};
    filteredLinks.forEach(function(l){linked[l.source]=true;linked[l.target]=true});
    filteredNodes=filteredNodes.filter(function(n){return linked[n.id]});
  }

  var graphNodes=filteredNodes.map(function(n){
    return {id:n.id,nm:n.nm,g:n.g,lc:n.dg};
  });
  var graphLinks=filteredLinks.map(function(l){
    return {source:l.source,target:l.target,r:l.r};
  });

  graphData={n:graphNodes,l:graphLinks};
  updateHeader(graphNodes.length,graphLinks.length);
  updateLegend(graphNodes);
  renderGraph(graphData);
}

function sourceNodeDegree(nodeId){
  for(var i=0;i<sourceData.n.length;i++){
    if(sourceData.n[i].id===nodeId)return sourceData.n[i].dg||0;
  }
  return 0;
}

function renderGraph(d){
  var opts=getOpts();
  updateLabels();

  if(sim)sim.stop();
  S.selectAll('g').remove();
  g=S.append('g');

  var spread=Math.max(300,opts.linkD*4);
  d.n.forEach(function(n){
    n.x=W/2+(Math.random()-0.5)*spread;
    n.y=H/2+(Math.random()-0.5)*spread;
  });

  sim=d3.forceSimulation(d.n)
    .force('link',d3.forceLink(d.l).id(function(n){return n.id}).distance(opts.linkD).strength(0.08))
    .force('charge',d3.forceManyBody().strength(-opts.charge))
    .force('center',d3.forceCenter(W/2,H/2))
    .force('collision',d3.forceCollide(opts.collide))
    .alphaDecay(0.01).velocityDecay(0.38);

  lk=g.append('g').selectAll('line').data(d.l).join('line')
    .attr('stroke',opts.lineClr).attr('stroke-opacity',0.22).attr('stroke-width',1);

  nd=g.append('g').selectAll('g').data(d.n).join('g')
    .call(d3.drag()
      .on('start',function(e,n){if(!e.active)sim.alphaTarget(0.25).restart();n.fx=n.x;n.fy=n.y})
      .on('drag',function(e,n){n.fx=e.x;n.fy=e.y})
      .on('end',function(e,n){if(!e.active)sim.alphaTarget(0);n.fx=null;n.fy=null}));

  var baseR=opts.nodeR;
  nd.append('circle')
    .attr('r',function(n){return Math.max(baseR,Math.min(baseR*3.5,baseR+n.lc*0.35))})
    .attr('fill',function(n){return C[n.g]||'#90a4ae'})
    .attr('stroke',opts.strokeClr).attr('stroke-width',1.5);

  nd.append('text')
    .text(function(n){return n.nm.length>10?n.nm.slice(0,10)+'..':n.nm})
    .attr('dx',opts.labelDX).attr('dy',5)
    .style('font-size',opts.fontS+'px').style('fill',opts.textClr)
    .style('pointer-events','none');

  nd.on('mouseover',function(e,n){
    var t=document.getElementById('tip');
    t.style.display='block';
    t.innerHTML='<b>'+n.nm+'</b><br>类型: '+n.g+'<br>连接数: '+n.lc;
  }).on('mousemove',function(e){
    var t=document.getElementById('tip');
    t.style.left=(e.clientX+15)+'px';
    t.style.top=(e.clientY-10)+'px';
  }).on('mouseout',function(){
    document.getElementById('tip').style.display='none';
  });

  sim.on('tick',function(){
    lk.attr('x1',function(d){return d.source.x})
      .attr('y1',function(d){return d.source.y})
      .attr('x2',function(d){return d.target.x})
      .attr('y2',function(d){return d.target.y});
    nd.attr('transform',function(d){return 'translate('+d.x+','+d.y+')'});
  });

  S.call(zoom.transform,lastTransform);
  applyColors(opts);
}

function resetFilters(){
  if(!sourceData)return;
  document.getElementById('searchBox').value='';
  document.getElementById('minDegree').value=0;
  document.getElementById('nodeLimit').value=Math.max(1,sourceData.n.length);
  document.getElementById('relLimit').value=Math.max(1,sourceData.l.length);
  document.getElementById('showIsolated').checked=true;
  document.querySelectorAll('.label-filter').forEach(function(el){el.checked=true});
  updateLabels();
  buildFilteredGraph();
}

fetch('/api/graph').then(function(r){return r.json()}).then(function(d){
  document.getElementById('load').style.display='none';
  if(d.err){
    document.getElementById('load').style.display='block';
    document.getElementById('load').textContent='加载失败: '+d.err;
    return;
  }
  prepareSourceData(d);
  setupControls();
  updateHeader(sourceData.n.length,sourceData.l.length);
  buildFilteredGraph();
  initZoom();
}).catch(function(e){
  document.getElementById('load').textContent='加载失败: '+e;
});

document.getElementById('toggle-btn').addEventListener('click',function(){
  var p=document.getElementById('ctrl');
  p.style.display=p.style.display==='none'||p.style.display===''?'block':'none';
});

document.querySelectorAll('#ctrl input[type=range]').forEach(function(el){
  el.addEventListener('input',updateLabels);
});

document.getElementById('apply-btn').addEventListener('click',function(){
  buildFilteredGraph();
});

document.getElementById('reset-btn').addEventListener('click',function(){
  resetFilters();
});

['bgClr','lineClr','textClr','strokeClr'].forEach(function(id){
  document.getElementById(id).addEventListener('input',function(){
    if(graphData)applyColors(getOpts());
  });
});

window.addEventListener('resize',function(){
  W=innerWidth;H=innerHeight;
  S.attr('width',W).attr('height',H);
  if(graphData)renderGraph(graphData);
});
</script>
</body>
</html>'''

if __name__ == '__main__':
    run()
