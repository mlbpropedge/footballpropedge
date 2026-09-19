let payload={players:[]}, metrics={}, performance={}, sortKey="rushing_yards";
const $=id=>document.getElementById(id);
const setText=(id,value)=>{const el=$(id); if(el) el.textContent=value;};
const setHTML=(id,value)=>{const el=$(id); if(el) el.innerHTML=value;};
const valueOf=id=>{const el=$(id); return el ? el.value : "";};

function initials(name=""){
  const cleaned=String(name).replace(/[^A-Za-z' .-]/g," ").trim();
  const parts=cleaned.split(/\s+/).filter(Boolean);
  if(parts.length===0) return "??";
  const first=(parts[0][0]||"").toUpperCase();
  const last=(parts[parts.length-1][0]||"").toUpperCase();
  return parts.length===1 ? first : first+last;
}

function avatar(x,type,extra=""){
  return `<span class="avatar ${type} ${extra}" aria-hidden="true">${initials(x.player)}</span>`;
}

function bestCard(x,i,type){
  const rush=Number(x.rushing_yards||0);
  const rec=Number(x.receiving_yards||0);
  const td=Number(x.td_probability||0);
  const isRush=type==="rush", isRec=type==="receive";
  const value=isRush
    ? `${rush.toFixed(1)}<small> projected rush yds</small>`
    : isRec
      ? `${rec.toFixed(1)}<small> projected rec yds</small>`
      : `${td.toFixed(1)}%<small> TD probability</small>`;

  const edge=isRush
    ? Number(x.rush_edge_score||0)
    : isRec
      ? Number(x.receiving_edge_score||0)
      : Number(x.td_edge_score||0);
  const matchup=isRush
    ? Number(x.rush_matchup_score||0)
    : isRec
      ? Number(x.receiving_matchup_score||0)
      : Number(x.td_matchup_score||0);
  const reliability=isRush
    ? Number(x.rush_reliability_score||0)
    : isRec
      ? Number(x.receiving_reliability_score||0)
      : null;

  const chips=isRush
    ? [`${x.recent_carries ?? 0} carries L3`,`Reliability ${reliability.toFixed(0)}/100`,`Matchup ${matchup.toFixed(0)}/100`]
    : isRec
      ? [`${x.recent_targets ?? 0} targets L3`,`Reliability ${reliability.toFixed(0)}/100`,`Matchup ${matchup.toFixed(0)}/100`]
      : [`${rush.toFixed(1)} rush yds`,`Matchup ${matchup.toFixed(0)}/100`];

  return `<article class="prediction-card ${type}">
    <div class="card-top">
      <div class="player-line">
        ${avatar(x,type)}
        <div class="player-copy">
          <h3>${x.player}</h3>
          <div class="meta">${x.position} • ${x.team} vs ${x.opponent}</div>
        </div>
      </div>
      <div class="rank">#${i+1}</div>
    </div>
    <div class="projection">${value}</div>
    <div class="edge-row"><span class="edge-label">Edge Score</span><strong class="edge-score">${edge.toFixed(1)}</strong></div>
    <div class="chip-row">${chips.map(c=>`<span class="chip">${c}</span>`).join("")}</div>
  </article>`;
}

async function fetchJSON(url){
  const r=await fetch(url+"?v=5&x="+Date.now(),{cache:"no-store"});
  if(!r.ok) throw new Error(`${url} returned HTTP ${r.status}`);
  return r.json();
}

async function load(){
  const [p,m]=await Promise.all([
    fetchJSON("data/predictions.json"),
    fetchJSON("data/model_metrics.json")
  ]);
  payload=p || {players:[]};
  payload.players=Array.isArray(payload.players)?payload.players:[];
  metrics=m || {};
  setup();
  renderBest();
  render();
}

function setup(){
  setText("week",`${payload.season} • ${payload.week}`);
  setText("navWeek",payload.week);
  setText("count",payload.players.length);
  setText("updated","Updated "+new Date(payload.generated_at).toLocaleString());

  const teamSelect=$("team");
  if(teamSelect){
    [...new Set(payload.players.map(x=>x.team).filter(Boolean))].sort().forEach(t=>
      teamSelect.insertAdjacentHTML("beforeend",`<option>${t}</option>`)
    );
  }

  ["search","position","team","metric"].forEach(id=>{
    const el=$(id);
    if(!el) return;
    el.addEventListener(id==="search"?"input":"change",()=>{
      if(id==="metric") sortKey=valueOf("metric") || "rushing_yards";
      render();
    });
  });

  renderMetrics();
}

function renderBest(){
  const rb=[...payload.players]
    .filter(x=>x.position==="RB")
    .sort((a,b)=>Number(b.rush_rank_score??b.rush_edge_score??0)-Number(a.rush_rank_score??a.rush_edge_score??0))
    .slice(0,6);

  const wr=[...payload.players]
    .filter(x=>["WR","TE"].includes(x.position))
    .sort((a,b)=>Number(b.receiving_rank_score??b.receiving_edge_score??0)-Number(a.receiving_rank_score??a.receiving_edge_score??0))
    .slice(0,6);

  const td=[...payload.players]
    .sort((a,b)=>Number(b.td_edge_score||0)-Number(a.td_edge_score||0))
    .slice(0,6);

  setHTML("rbCards",rb.map((x,i)=>bestCard(x,i,"rush")).join(""));
  setHTML("wrCards",wr.map((x,i)=>bestCard(x,i,"receive")).join(""));
  setHTML("tdCards",td.map((x,i)=>bestCard(x,i,"touchdown")).join(""));
}

function render(){
  const q=valueOf("search").toLowerCase();
  const pos=valueOf("position");
  const team=valueOf("team");

  let rows=payload.players.filter(x=>
    (!q||`${x.player} ${x.team}`.toLowerCase().includes(q)) &&
    (!pos||x.position===pos) &&
    (!team||x.team===team)
  );

  rows.sort((a,b)=>Number(b[sortKey]||0)-Number(a[sortKey]||0));

  const html=rows.map(x=>{
    const rush=Number(x.rushing_yards||0);
    const rec=Number(x.receiving_yards||0);
    const td=Number(x.td_probability||0);
    return `<tr>
      <td>
        <div class="table-player">
          ${avatar(x,"table-avatar","table-avatar")}
          <div>
            <div class="player">${x.player}</div>
            <div class="muted">${x.recent_carries ?? 0} carries • ${x.recent_targets ?? 0} targets L3</div>
          </div>
        </div>
      </td>
      <td>${x.position}</td>
      <td>${x.team}</td>
      <td>${x.opponent}</td>
      <td class="metric">${rush.toFixed(1)}</td>
      <td class="metric">${rec.toFixed(1)}</td>
      <td><span class="td">${td.toFixed(1)}%</span></td>
    </tr>`;
  }).join("") || `<tr><td colspan="7" class="muted">No players match these filters.</td></tr>`;

  setHTML("rows",html);
  setText("count",rows.length);
}

function renderResults(){
  const weeks=Array.isArray(performance.weekly_results)?performance.weekly_results:[];
  const summary=`
    <div class="result-stat"><span>Graded weeks</span><strong>${performance.graded_weeks ?? 0}</strong><small>${performance.graded_predictions ?? 0} player grades</small></div>
    <div class="result-stat rush-result"><span>Rushing MAE</span><strong>${performance.rushing_mae==null?"—":performance.rushing_mae+" yds"}</strong><small>lower is better</small></div>
    <div class="result-stat rec-result"><span>Receiving MAE</span><strong>${performance.receiving_mae==null?"—":performance.receiving_mae+" yds"}</strong><small>lower is better</small></div>
    <div class="result-stat td-result"><span>TD Brier</span><strong>${performance.td_brier==null?"—":performance.td_brier}</strong><small>probability calibration</small></div>
  `;
  setHTML("resultsSummary",summary);

  if(!weeks.length){
    setHTML("weeklyResults",`<div class="results-empty">
      <strong>Tracking starts with the current published week.</strong>
      <p>${performance.note || "Results will populate automatically after the first archived week is complete."}</p>
    </div>`);
    return;
  }

  setHTML("weeklyResults",weeks.slice(0,4).map(w=>{
    const sample=(w.sample_predictions||[]).map(x=>`
      <div class="graded-row">
        <div class="graded-player">
          <span class="avatar table-avatar">${initials(x.player)}</span>
          <div><b>${x.player}</b><small>${x.position} • ${x.team}</small></div>
        </div>
        <div><span>Rush</span><b>${x.projected_rushing_yards} → ${x.actual_rushing_yards}</b></div>
        <div><span>Rec</span><b>${x.projected_receiving_yards} → ${x.actual_receiving_yards}</b></div>
        <div><span>TD</span><b>${x.td_probability}% → ${x.actual_td?"Yes":"No"}</b></div>
      </div>`).join("");

    return `<article class="week-result-card">
      <div class="week-result-head">
        <div><span class="week-label">WEEK ${w.week}</span><h3>${w.graded_players} graded players</h3></div>
        <div class="week-metrics">
          <span>Rush MAE <b>${w.rushing_mae ?? "—"}</b></span>
          <span>Rec MAE <b>${w.receiving_mae ?? "—"}</b></span>
          <span>TD Brier <b>${w.td_brier ?? "—"}</b></span>
        </div>
      </div>
      <div class="graded-list">${sample}</div>
    </article>`;
  }).join(""));
}

function renderMetrics(){
  const labels={rushing:"Rushing",receiving:"Receiving",touchdown:"Touchdown"};
  const html=Object.entries(metrics).map(([k,v])=>`
    <div class="metric-box">
      <b>${labels[k]||k}</b>
      <span>${v.model||"—"}<br>
      ${v.cv_mae!=null?`CV MAE: ${v.cv_mae} yds`:v.cv_brier!=null?`Calibrated Brier: ${v.cv_brier}`:"Validation pending"}
      ${k==="touchdown"&&v.calibration?.available?(v.calibration.applied?`<br>Calibration improvement: ${Number(v.calibration.improvement_pct||0).toFixed(1)}%`:`<br>Calibration tested; raw probabilities retained`):""}
      ${v.overfit_flag?" • overfit flag":""}</span>
    </div>`
  ).join("");
  setHTML("metrics",html);

  const benchmarkNames={last_3:"Last 3 average",last_5:"Last 5 average",season_average:"Season average",workload:"Workload baseline"};
  const benchHtml=["rushing","receiving"].map(k=>{
    const v=metrics[k]||{};
    const b=v.benchmark||{};
    if(b.model_mae==null) return "";
    const best=benchmarkNames[b.best_baseline]||b.best_baseline||"—";
    const delta=Number(b.model_improvement_yards||0);
    const pct=Number(b.model_improvement_pct||0);
    const result=b.beats_best_baseline
      ? "<span class=\"benchmark-win\">ML better by "+Math.abs(delta).toFixed(2)+" yds ("+Math.abs(pct).toFixed(1)+"%)</span>"
      : "<span class=\"benchmark-loss\">Baseline better by "+Math.abs(delta).toFixed(2)+" yds ("+Math.abs(pct).toFixed(1)+"%)</span>";
    return "<article class=\"benchmark-card\">"+
      "<div class=\"benchmark-title\">"+(k==="rushing"?"Rushing":"Receiving")+"</div>"+
      "<div class=\"benchmark-values\">"+
        "<div><span>ML MAE</span><strong>"+Number(b.model_mae).toFixed(2)+"</strong></div>"+
        "<div><span>Best baseline</span><strong>"+(b.best_baseline_mae==null?"—":Number(b.best_baseline_mae).toFixed(2))+"</strong></div>"+
      "</div>"+
      "<div class=\"benchmark-foot\"><span>"+best+"</span>"+result+"</div>"+
    "</article>";
  }).join("");
  setHTML("benchmarks",benchHtml || "<div class=\"muted\">Benchmark data will appear after the next successful model run.</div>");
}

load().catch(e=>{
  console.error("Football Prop Edge render error:",e);
  setHTML("rows",`<tr><td colspan="7">Prediction data is temporarily unavailable. ${e.message}</td></tr>`);
  setText("updated","Data load error");
});