let payload={players:[]}, metrics={}, sortKey="rushing_yards";
const $=id=>document.getElementById(id);

function initials(name){
  const cleaned=name.replace(/[^A-Za-z' .-]/g," ").trim();
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
  const isRush=type==="rush", isRec=type==="receive";
  const value=isRush
    ? `${x.rushing_yards.toFixed(1)}<small> projected rush yds</small>`
    : isRec
      ? `${x.receiving_yards.toFixed(1)}<small> projected rec yds</small>`
      : `${x.td_probability.toFixed(1)}%<small> TD probability</small>`;

  const chips=isRush
    ? [`${x.recent_carries} carries L3`,`${x.recent_rush_yards} rush yds L3`]
    : isRec
      ? [`${x.recent_targets} targets L3`,`${x.recent_rec_yards} rec yds L3`]
      : [`${x.rushing_yards.toFixed(1)} rush yds`,`${x.receiving_yards.toFixed(1)} rec yds`];

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

async function load(){
  const [p,m]=await Promise.all([
    fetch("data/predictions.json?x="+Date.now()).then(r=>r.json()),
    fetch("data/model_metrics.json?x="+Date.now()).then(r=>r.json())
  ]);
  payload=p;metrics=m;
  setup();
  renderBest();
  render();
}

function setup(){
  $("week").textContent=`${payload.season} • ${payload.week}`;
  $("navWeek").textContent=payload.week;
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
}

function renderBest(){
  const rb=[...payload.players]
    .filter(x=>x.position==="RB")
    .sort((a,b)=>b.rushing_yards-a.rushing_yards)
    .slice(0,6);

  const wr=[...payload.players]
    .filter(x=>["WR","TE"].includes(x.position))
    .sort((a,b)=>b.receiving_yards-a.receiving_yards)
    .slice(0,6);

  const td=[...payload.players]
    .sort((a,b)=>b.td_probability-a.td_probability)
    .slice(0,6);

  $("rbCards").innerHTML=rb.map((x,i)=>bestCard(x,i,"rush")).join("");
  $("wrCards").innerHTML=wr.map((x,i)=>bestCard(x,i,"receive")).join("");
  $("tdCards").innerHTML=td.map((x,i)=>bestCard(x,i,"touchdown")).join("");
}

function render(){
  const q=$("search").value.toLowerCase();
  const pos=$("position").value;
  const team=$("team").value;

  let rows=payload.players.filter(x=>
    (!q||`${x.player} ${x.team}`.toLowerCase().includes(q)) &&
    (!pos||x.position===pos) &&
    (!team||x.team===team)
  );

  rows.sort((a,b)=>b[sortKey]-a[sortKey]);

  $("rows").innerHTML=rows.map(x=>`<tr>
    <td>
      <div class="table-player">
        ${avatar(x,"table-avatar","table-avatar")}
        <div>
          <div class="player">${x.player}</div>
          <div class="muted">${x.recent_carries} carries • ${x.recent_targets} targets L3</div>
        </div>
      </div>
    </td>
    <td>${x.position}</td>
    <td>${x.team}</td>
    <td>${x.opponent}</td>
    <td class="metric">${x.rushing_yards.toFixed(1)}</td>
    <td class="metric">${x.receiving_yards.toFixed(1)}</td>
    <td><span class="td">${x.td_probability.toFixed(1)}%</span></td>
  </tr>`).join("") || `<tr><td colspan="7" class="muted">No players match these filters.</td></tr>`;

  $("count").textContent=rows.length;
}

function renderMetrics(){
  const labels={rushing:"Rushing",receiving:"Receiving",touchdown:"Touchdown"};
  $("metrics").innerHTML=Object.entries(metrics).map(([k,v])=>`
    <div class="metric-box">
      <b>${labels[k]}</b>
      <span>${v.model||"—"}<br>
      ${v.cv_mae!=null?`CV MAE: ${v.cv_mae} yds`:v.cv_brier!=null?`Brier: ${v.cv_brier}`:"Validation pending"}
      ${v.overfit_flag?" • overfit flag":""}</span>
    </div>`
  ).join("");
}

load().catch(e=>{
  $("rows").innerHTML=`<tr><td colspan="7">Prediction data is not available yet. ${e.message}</td></tr>`;
});