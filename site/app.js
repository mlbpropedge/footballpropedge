let payload={players:[]}, metrics={}, performance={}, sortKey="rushing_yards";
const $=id=>document.getElementById(id);

async function load(){
  const stamp=Date.now();
  const [p,m,perf]=await Promise.all([
    fetch("data/predictions.json?x="+stamp).then(r=>r.json()),
    fetch("data/model_metrics.json?x="+stamp).then(r=>r.json()),
    fetch("data/performance.json?x="+stamp).then(r=>r.json()).catch(()=>({graded_predictions:0,weeks:[]}))
  ]);
  payload=p; metrics=m; performance=perf; setup(); render();
}

function setup(){
  $("week").textContent=`${payload.season} • Week ${payload.week}`;
  $("count").textContent=payload.players.length;
  $("updated").textContent="Updated "+new Date(payload.generated_at).toLocaleString();
  [...new Set(payload.players.map(x=>x.team))].sort().forEach(t=>
    $("team").insertAdjacentHTML("beforeend",`<option>${t}</option>`)
  );
  ["search","position","team","metric"].forEach(id=>
    $(id).addEventListener(id==="search"?"input":"change",()=>{
      if(id==="metric") sortKey=$("metric").value;
      render();
    })
  );
  renderMetrics();
  renderPerformance();
}

function render(){
  const q=$("search").value.toLowerCase(), pos=$("position").value, team=$("team").value;
  let rows=payload.players.filter(x=>
    (!q||`${x.player} ${x.team} ${x.opponent}`.toLowerCase().includes(q)) &&
    (!pos||x.position===pos) &&
    (!team||x.team===team)
  );
  rows.sort((a,b)=>b[sortKey]-a[sortKey]);
  $("rows").innerHTML=rows.map(x=>`<tr>
    <td><span class="player">${x.player}</span><br><span class="muted">${x.recent_carries} carries • ${x.recent_targets} targets L3</span></td>
    <td>${x.position}</td><td>${x.team}</td><td>${x.opponent}</td>
    <td class="metric">${x.rushing_yards.toFixed(1)}</td>
    <td class="metric">${x.receiving_yards.toFixed(1)}</td>
    <td><span class="td">${x.td_probability.toFixed(1)}%</span></td>
  </tr>`).join("")||`<tr><td colspan="7" class="muted">No players match these filters.</td></tr>`;
  $("count").textContent=rows.length;
}

function renderMetrics(){
  const labels={rushing:"Rushing",receiving:"Receiving",touchdown:"Touchdown"};
  $("metrics").innerHTML=Object.entries(metrics).map(([k,v])=>`<div class="metric-box">
    <b>${labels[k]}</b>
    <span>${v.model||"—"}<br>
    ${v.cv_mae!=null?`Walk-forward MAE: ${v.cv_mae} yds`:v.cv_brier!=null?`Walk-forward Brier: ${v.cv_brier}`:"Validation pending"}
    ${v.overfit_ratio!=null?`<br>Train/CV ratio: ${v.overfit_ratio}`:""}
    ${v.overfit_flag?" • overfit flag":""}</span>
  </div>`).join("");
}

function renderPerformance(){
  const graded=performance.graded_predictions||0;
  if(!graded){
    $("performance").innerHTML=`<div class="metric-box"><b>Tracking begins now</b><span>Week ${payload.week} projections are archived. Results will populate automatically after games are completed.</span></div>`;
    return;
  }
  $("performance").innerHTML=`
    <div class="metric-box"><b>Rushing</b><span>MAE: ${performance.rushing_mae ?? "—"} yds</span></div>
    <div class="metric-box"><b>Receiving</b><span>MAE: ${performance.receiving_mae ?? "—"} yds</span></div>
    <div class="metric-box"><b>Touchdown</b><span>Brier: ${performance.td_brier ?? "—"}<br>${graded} graded rows</span></div>`;
}

load().catch(e=>{
  $("rows").innerHTML=`<tr><td colspan="7">Prediction data is not available yet. ${e.message}</td></tr>`;
});