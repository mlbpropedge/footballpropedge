let payload={players:[]}, metrics={}, sortKey="rushing_yards";
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

  const chips=isRush
    ? [`${x.recent_carries ?? 0} carries L3`,`${x.recent_rush_yards ?? 0} rush yds L3`]
    : isRec
      ? [`${x.recent_targets ?? 0} targets L3`,`${x.recent_rec_yards ?? 0} rec yds L3`]
      : [`${rush.toFixed(1)} rush yds`,`${rec.toFixed(1)} rec yds`];

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
    .sort((a,b)=>Number(b.rushing_yards||0)-Number(a.rushing_yards||0))
    .slice(0,6);

  const wr=[...payload.players]
    .filter(x=>["WR","TE"].includes(x.position))
    .sort((a,b)=>Number(b.receiving_yards||0)-Number(a.receiving_yards||0))
    .slice(0,6);

  const td=[...payload.players]
    .sort((a,b)=>Number(b.td_probability||0)-Number(a.td_probability||0))
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

function renderMetrics(){
  const labels={rushing:"Rushing",receiving:"Receiving",touchdown:"Touchdown"};
  const html=Object.entries(metrics).map(([k,v])=>`
    <div class="metric-box">
      <b>${labels[k]||k}</b>
      <span>${v.model||"—"}<br>
      ${v.cv_mae!=null?`CV MAE: ${v.cv_mae} yds`:v.cv_brier!=null?`Brier: ${v.cv_brier}`:"Validation pending"}
      ${v.overfit_flag?" • overfit flag":""}</span>
    </div>`
  ).join("");
  setHTML("metrics",html);
}

load().catch(e=>{
  console.error("Football Prop Edge render error:",e);
  setHTML("rows",`<tr><td colspan="7">Prediction data is temporarily unavailable. ${e.message}</td></tr>`);
  setText("updated","Data load error");
});