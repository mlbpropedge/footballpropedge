let payload={players:[]}, metrics={}, performance={}, sortKey="rushing_yards", visibleRows=36;
const $=id=>document.getElementById(id);
const setText=(id,value)=>{const el=$(id); if(el) el.textContent=value;};
const setHTML=(id,value)=>{const el=$(id); if(el) el.innerHTML=value;};
const valueOf=id=>{const el=$(id); return el ? el.value : "";};
const escapeHTML=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]);
const todayET=()=>new Intl.DateTimeFormat("en-CA",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
const isPastGame=x=>Boolean(x.game_started)||(x.game_start?new Date(x.game_start)<=new Date():Boolean(x.game_date && x.game_date<todayET()));
const gameLabel=x=>x.game_start?new Date(x.game_start).toLocaleString("en-US",{weekday:"short",month:"short",day:"numeric",hour:"numeric",minute:"2-digit",timeZone:"America/New_York"})+" ET"+(isPastGame(x)?" • started":""):x.game_date?new Date(x.game_date+"T12:00:00Z").toLocaleDateString("en-US",{month:"short",day:"numeric",timeZone:"UTC"})+(isPastGame(x)?" • date passed":""):"Game date pending";
const selectablePlayers=()=>payload.players.filter(x=>!isPastGame(x));
// Top lists skip players unlikely to suit up: Doubtful, or missed 2+ straight games.
const topListEligible=x=>x.injury_status!=="Doubtful"&&Number(x.games_missed||0)<2;
const fmtSigned=n=>(n>0?"+":"")+Number(n).toFixed(1);

function statusBadges(x){
  const out=[];
  if(x.injury_status){
    const tone=x.injury_status==="Doubtful"?"danger":"warn";
    out.push(`<span class="badge ${tone}" title="Official injury report designation">${escapeHTML(x.injury_status)}${x.injury_detail?" · "+escapeHTML(x.injury_detail):""}</span>`);
  }else if(Number(x.games_missed||0)>0){
    const n=Number(x.games_missed);
    out.push(`<span class="badge muted" title="Last played in Week ${escapeHTML(x.last_played_week)}">Missed last ${n} game${n===1?"":"s"}</span>`);
  }
  return out;
}

function changeBadges(x,fields){
  if(x.new_to_slate) return [`<span class="badge info" title="Not on the previous update of this slate">New this update</span>`];
  const change=x.change||{};
  return fields.filter(f=>change[f]!=null).map(f=>{
    const d=Number(change[f]);
    const unit=f==="td_probability"?" pts":" yds";
    const label=f==="rushing_yards"?"rush":f==="receiving_yards"?"rec":"TD";
    return `<span class="badge ${d>0?"up":"down"}" title="Change since the previous update">${d>0?"▲":"▼"} ${label} ${fmtSigned(d)}${unit}</span>`;
  });
}

function badgeRow(x,fields){
  const badges=[...statusBadges(x),...changeBadges(x,fields)];
  return badges.length?`<div class="badge-row">${badges.join("")}</div>`:"";
}

const snapText=x=>x.snap_share_3==null?null:`${Number(x.snap_share_3).toFixed(0)}% snaps L3`;

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

function playerUrl(x){
  return `player.html?id=${encodeURIComponent(x.player_id||"")}`;
}

function defenseRank(x,type){
  const rank=Number(type==="rush"?x.opp_rush_def_rank:x.opp_rec_def_rank);
  const total=Number(x.opp_def_rank_total||32);
  return rank>0 ? `#${rank} of ${total}` : "Pending";
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
  const context=x.season_context||{};
  const seasonAvg=isRush
    ? Number(context.season_rushing_avg||0)
    : isRec
      ? Number(context.season_receiving_avg||0)
      : null;
  const rankType=isRush?"rush":"receive";
  const chips=(isRush
    ? [`${x.recent_carries ?? 0} carries L3`,snapText(x),`Reliability ${reliability.toFixed(0)}/100`,`Matchup ${matchup.toFixed(0)}/100`]
    : isRec
      ? [`${x.recent_targets ?? 0} targets L3`,snapText(x),`Reliability ${reliability.toFixed(0)}/100`,`Matchup ${matchup.toFixed(0)}/100`]
      : [`${rush.toFixed(1)} rush yds`,snapText(x),`Matchup ${matchup.toFixed(0)}/100`]).filter(Boolean);
  const changeField=isRush?"rushing_yards":isRec?"receiving_yards":"td_probability";

  const details=isRush||isRec
    ? `<div class="quick-grid">
        <div><span>2026 average</span><strong>${seasonAvg.toFixed(1)} yds</strong></div>
        <div><span>Opponent defense</span><strong>${defenseRank(x,rankType)}</strong></div>
        <div><span>Games tracked</span><strong>${context.games_played??0}</strong></div>
      </div>`
    : `<div class="quick-grid">
        <div><span>Rush projection</span><strong>${rush.toFixed(1)} yds</strong></div>
        <div><span>Rec projection</span><strong>${rec.toFixed(1)} yds</strong></div>
        <div><span>2026 games</span><strong>${context.games_played??0}</strong></div>
      </div>`;

  const range=isRush?x.rushing_range_80:isRec?x.receiving_range_80:null;
  const rangeHTML=Array.isArray(range)&&range.length===2?`<div class="prediction-range"><span>80% model range</span><strong>${Number(range[0]).toFixed(1)}–${Number(range[1]).toFixed(1)} yds</strong></div>`:"";
  return `<article class="prediction-card ${type}" data-player-id="${escapeHTML(x.player_id)}">
    <div class="card-top">
      <div class="player-line">
        ${avatar(x,type)}
        <div class="player-copy">
          <h3><a class="player-name-link" href="${playerUrl(x)}">${escapeHTML(x.player)}</a></h3>
          <div class="meta">${escapeHTML(x.position)} • ${escapeHTML(x.team)} vs ${escapeHTML(x.opponent)}</div>
        </div>
      </div>
      <div class="rank">#${i+1}</div>
    </div>
    ${badgeRow(x,[changeField])}
    <div class="projection">${value}</div>
    ${rangeHTML}
    <div class="game-date">${gameLabel(x)}</div>
    <div class="edge-row" title="Ranking score; not a probability"><span class="edge-label">Edge Score</span><strong class="edge-score">${edge.toFixed(1)}</strong></div>
    <div class="chip-row">${chips.map(c=>`<span class="chip">${escapeHTML(c)}</span>`).join("")}</div>
    <button class="expand-btn" type="button" aria-expanded="false"><span>Quick look</span><b>＋</b></button>
    <div class="card-details" hidden>${details}<a class="detail-link" href="${playerUrl(x)}">View full player breakdown →</a></div>
  </article>`;
}

async function fetchJSON(url){
  const r=await fetch(url+"?v=5&x="+Date.now(),{cache:"no-store"});
  if(!r.ok) throw new Error(`${url} returned HTTP ${r.status}`);
  return r.json();
}

async function load(){
  const [p,m,r]=await Promise.all([
    fetchJSON("data/predictions.json"),
    fetchJSON("data/model_metrics.json").catch(()=>({})),
    fetchJSON("data/performance.json").catch(()=>({}))
  ]);
  payload=p || {players:[]};
  payload.players=Array.isArray(payload.players)?payload.players:[];
  payload.ruled_out=Array.isArray(payload.ruled_out)?payload.ruled_out:[];
  metrics=m || {};
  performance=r || {};
  setup();
  renderBest();
  render();
  renderRuledOut();
  renderResults();
}

function renderRuledOut(){
  const list=payload.ruled_out.filter(x=>!x.game_start||new Date(x.game_start)>new Date());
  const box=$("ruledOut");
  if(!box) return;
  box.hidden=!list.length;
  if(!list.length) return;
  setText("ruledOutCount",list.length);
  setHTML("ruledOutList",list.map(x=>`<div class="ruled-row">
      <div><strong>${escapeHTML(x.player)}</strong><small>${escapeHTML(x.position)} • ${escapeHTML(x.team)} vs ${escapeHTML(x.opponent)}</small></div>
      <span class="badge danger">${escapeHTML(x.status||"Out")}${x.detail?" · "+escapeHTML(x.detail):""}</span>
    </div>`).join(""));
}

function renderAvailabilityNote(){
  const a=payload.availability;
  if(!a) return;
  const parts=[];
  if(a.injury_report_week==null) parts.push("This week’s official injury report isn’t out yet, so availability may still change.");
  else parts.push(`Checked against the Week ${escapeHTML(a.injury_report_week)} injury report.`);
  if(payload.previous_generated_at) parts.push(`▲▼ tags show moves of 5+ since the update on ${new Date(payload.previous_generated_at).toLocaleString("en-US",{weekday:"short",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"})}.`);
  setHTML("availabilityNote",parts.join(" "));
}

function setup(){
  setText("week",`${payload.season} • ${payload.week}`);
  setText("navWeek",payload.week);
  setText("count",payload.players.length);
  const outCount=payload.ruled_out.length;
  setText("countNote",outCount?`active projections • ${outCount} ruled out`:"active projections");
  setText("updated","Updated "+new Date(payload.generated_at).toLocaleString());
  renderAvailabilityNote();
  const ageHours=(Date.now()-new Date(payload.generated_at).getTime())/3600000;
  const freshness=$("freshness");
  if(freshness && ageHours>36){
    freshness.hidden=false;
    freshness.textContent=`Last model run was ${Math.floor(ageHours/24)} day(s) ago. Check current player availability and game status before using these estimates.`;
  }
  const upcoming=$("upcomingOnly");
  if(upcoming){
    upcoming.disabled=!payload.players.some(x=>x.game_date);
    upcoming.parentElement.title=upcoming.disabled?"Game dates will be available after the next model refresh.":"Hide games from earlier dates";
    upcoming.addEventListener("change",()=>{visibleRows=36;render();});
  }
  const more=$("loadMore");
  more?.addEventListener("click",()=>{visibleRows+=36;render();});

  const teamSelect=$("team");
  if(teamSelect){
    [...new Set(payload.players.map(x=>x.team).filter(Boolean))].sort().forEach(t=>
      teamSelect.insertAdjacentHTML("beforeend",`<option>${escapeHTML(t)}</option>`)
    );
  }

  ["search","position","team","metric"].forEach(id=>{
    const el=$(id);
    if(!el) return;
    el.addEventListener(id==="search"?"input":"change",()=>{
      if(id==="metric") sortKey=valueOf("metric") || "rushing_yards";
      visibleRows=36;render();
    });
  });

  const filterToggle=$("filterToggle");
  if(filterToggle){
    filterToggle.addEventListener("click",()=>{
      const open=$("boardControls")?.classList.toggle("open");
      filterToggle.setAttribute("aria-expanded",String(Boolean(open)));
      const icon=filterToggle.querySelector("span");
      if(icon) icon.textContent=open?"−":"＋";
    });
  }

  document.addEventListener("click",event=>{
    const allBtn=event.target.closest(".show-all-graded");
    if(allBtn){showAllGraded(allBtn);return;}
    const button=event.target.closest(".expand-btn");
    if(button){
      const details=button.nextElementSibling;
      const open=button.getAttribute("aria-expanded")==="true";
      button.setAttribute("aria-expanded",String(!open));
      button.querySelector("b").textContent=open?"＋":"−";
      if(details) details.hidden=open;
      return;
    }
  });

  renderMetrics();
}

function renderBest(){
  const available=selectablePlayers().filter(topListEligible);
  const rb=[...available]
    .filter(x=>x.position==="RB")
    .sort((a,b)=>Number(b.rushing_yards||0)-Number(a.rushing_yards||0))
    .slice(0,6);

  const wr=[...available]
    .filter(x=>["WR","TE"].includes(x.position))
    .sort((a,b)=>Number(b.receiving_yards||0)-Number(a.receiving_yards||0))
    .slice(0,6);

  const td=[...available]
    .sort((a,b)=>Number(b.td_probability||0)-Number(a.td_probability||0))
    .slice(0,6);

  const empty='<div class="results-empty">This week’s games have passed. The next slate will appear after the model refresh.</div>';
  setHTML("rbCards",rb.map((x,i)=>bestCard(x,i,"rush")).join("")||empty);
  setHTML("wrCards",wr.map((x,i)=>bestCard(x,i,"receive")).join("")||empty);
  setHTML("tdCards",td.map((x,i)=>bestCard(x,i,"touchdown")).join("")||empty);
}

function render(){
  const q=valueOf("search").toLowerCase();
  const pos=valueOf("position");
  const team=valueOf("team");

  let rows=payload.players.filter(x=>
    (!q||`${x.player} ${x.team} ${x.opponent}`.toLowerCase().includes(q)) &&
    (!pos||x.position===pos) &&
    (!team||x.team===team) &&
    (!$("upcomingOnly")?.checked||!isPastGame(x))
  );

  rows.sort((a,b)=>Number(b[sortKey]||0)-Number(a[sortKey]||0));

  const html=rows.slice(0,visibleRows).map(x=>{
    const rush=Number(x.rushing_yards||0);
    const rec=Number(x.receiving_yards||0);
    const td=Number(x.td_probability||0);
    const past=isPastGame(x);
    return `<a class="board-row${past?" is-past":""}" href="${playerUrl(x)}" aria-label="View ${escapeHTML(x.player)} details">
      <div class="board-player">
        ${avatar(x,"table-avatar","table-avatar")}
        <div><strong>${escapeHTML(x.player)}</strong><span>${escapeHTML(x.position)} • ${escapeHTML(x.team)} vs ${escapeHTML(x.opponent)}<small class="board-game-date">${gameLabel(x)}</small></span>${badgeRow(x,["rushing_yards","receiving_yards","td_probability"])}</div>
      </div>
      <div class="board-stat"><span>Rush</span><strong>${rush.toFixed(1)}</strong><small>yards</small></div>
      <div class="board-stat"><span>Receiving</span><strong>${rec.toFixed(1)}</strong><small>yards</small></div>
      <div class="board-stat"><span>TD chance</span><strong>${td.toFixed(1)}%</strong><small>probability</small></div>
      <div class="board-usage"><span>${x.recent_carries ?? 0} carries</span><span>${x.recent_targets ?? 0} targets</span>${x.snap_share_3==null?"":`<span>${Number(x.snap_share_3).toFixed(0)}% snaps</span>`}<small>last 3 average</small></div>
      <div class="board-open">View <b>→</b></div>
    </a>`;
  }).join("") || `<div class="results-empty"><strong>No players match these filters.</strong><p>Try clearing one of the filters above.</p></div>`;

  setHTML("rows",html);
  setText("boardCount",`${Math.min(visibleRows,rows.length)} of ${rows.length} players shown`);
  const more=$("loadMore");
  if(more) more.hidden=rows.length<=visibleRows;
}

const pctText=v=>v==null?"—":`${Number(v).toFixed(0)}%`;
const rangeMark=v=>v==null?"":`<i class="range-mark ${v?"hit":"miss"}" title="${v?"Inside":"Outside"} the 80% range">${v?"✓":"✗"}</i>`;
let resultsDetail=null;

function gradedRow(x){
  return `<div class="graded-row">
    <div class="graded-player">
      <span class="avatar table-avatar">${initials(x.player)}</span>
      <div><b>${escapeHTML(x.player)}</b><small>${escapeHTML(x.position)} • ${escapeHTML(x.team)}${x.opponent?" vs "+escapeHTML(x.opponent):""}</small></div>
    </div>
    <div><span>Rush</span><b>${escapeHTML(x.projected_rushing_yards)} → ${escapeHTML(x.actual_rushing_yards)} ${rangeMark(x.rush_in_range)}</b></div>
    <div><span>Rec</span><b>${escapeHTML(x.projected_receiving_yards)} → ${escapeHTML(x.actual_receiving_yards)} ${rangeMark(x.rec_in_range)}</b></div>
    <div><span>TD</span><b>${escapeHTML(x.td_probability)}% → ${x.actual_td?"Yes":"No"}</b></div>
  </div>`;
}

async function showAllGraded(button){
  const week=Number(button.dataset.week);
  const list=button.closest(".week-result-card")?.querySelector(".graded-list");
  if(!list) return;
  button.disabled=true;
  button.textContent="Loading…";
  try{
    resultsDetail=resultsDetail||await fetchJSON("data/results_detail.json");
    const players=(resultsDetail.weeks||[]).find(w=>Number(w.week)===week)?.players||[];
    list.innerHTML=players.map(gradedRow).join("")||`<div class="results-empty">No graded players for this week.</div>`;
    button.remove();
  }catch(e){
    button.disabled=false;
    button.textContent="Couldn’t load — try again";
  }
}

function renderCalibration(){
  const buckets=Array.isArray(performance.td_calibration)?performance.td_calibration:[];
  if(!buckets.length){setHTML("tdCalibration","");return;}
  const rows=buckets.map(b=>`<div class="cal-row">
      <span class="cal-label">${escapeHTML(b.label)}<small>${b.samples} players</small></span>
      <div class="cal-bars">
        <div class="cal-bar predicted"><i style="width:${Math.min(100,Number(b.avg_predicted))}%"></i><b>${Number(b.avg_predicted).toFixed(0)}%</b></div>
        <div class="cal-bar actual"><i style="width:${Math.min(100,Number(b.actual_rate))}%"></i><b>${Number(b.actual_rate).toFixed(0)}%</b></div>
      </div>
    </div>`).join("");
  setHTML("tdCalibration",`<div class="calibration-card">
    <div class="calibration-head"><div><span class="week-label">TD CALIBRATION</span><h3>When we said X%, how often did they score?</h3></div>
    <div class="cal-legend"><span class="predicted">Predicted</span><span class="actual">Actually scored</span></div></div>
    ${rows}
    <p class="cal-foot">Bars that match mean the probabilities can be taken at face value. All graded weeks combined.</p>
  </div>`);
}

function renderResults(){
  const weeks=Array.isArray(performance.weekly_results)?performance.weekly_results:[];
  const p=performance;
  const tdCompare=p.td_brier!=null&&p.td_baseline_brier!=null
    ? (p.td_brier<p.td_baseline_brier?`beats simple baseline (${p.td_baseline_brier})`:`simple baseline: ${p.td_baseline_brier}`)
    : "lower is better";
  const rangeStat=(hit,mae,graded)=>hit!=null
    ? `<strong>${pctText(hit)}</strong><small>inside the 80% range • MAE ${mae ?? "—"} yds • ${graded ?? 0} graded</small>`
    : `<strong>${mae==null?"—":mae+" yds"}</strong><small>average miss (MAE)</small>`;
  const summary=`
    <div class="result-stat"><span>Graded weeks</span><strong>${p.graded_weeks ?? 0}</strong><small>${p.graded_predictions ?? 0} player grades</small></div>
    <div class="result-stat rush-result"><span>Rushing</span>${rangeStat(p.rushing_range_hit_rate,p.rushing_mae,p.rushing_graded)}</div>
    <div class="result-stat rec-result"><span>Receiving</span>${rangeStat(p.receiving_range_hit_rate,p.receiving_mae,p.receiving_graded)}</div>
    <div class="result-stat td-result"><span>TD Brier</span><strong>${p.td_brier ?? "—"}</strong><small>${escapeHTML(tdCompare)}</small></div>
  `;
  setHTML("resultsSummary",summary);
  renderCalibration();

  if(!weeks.length){
    setHTML("weeklyResults",`<div class="results-empty">
      <strong>Tracking starts with the current published week.</strong>
      <p>${escapeHTML(p.note || "Results will populate automatically after the first archived week is complete.")}</p>
    </div>`);
    return;
  }

  setHTML("weeklyResults",weeks.slice(0,6).map(w=>{
    const counts=w.rushing_graded!=null?` • ${w.rushing_graded} rush / ${w.receiving_graded} rec / ${w.td_graded} TD graded`:"";
    return `<article class="week-result-card">
      <div class="week-result-head">
        <div><span class="week-label">WEEK ${escapeHTML(w.week)}</span><h3>${escapeHTML(w.graded_players)} graded players</h3><small class="week-counts">${escapeHTML(counts.replace(/^ • /,""))}</small></div>
        <div class="week-metrics">
          <span>Rush MAE <b>${w.rushing_mae ?? "—"}</b></span>
          <span>Rec MAE <b>${w.receiving_mae ?? "—"}</b></span>
          ${w.rushing_range_hit_rate!=null?`<span>In range <b>${pctText(w.rushing_range_hit_rate)} / ${pctText(w.receiving_range_hit_rate)}</b></span>`:""}
          <span>TD Brier <b>${w.td_brier ?? "—"}</b></span>
        </div>
      </div>
      <div class="graded-list">${(w.sample_predictions||[]).map(gradedRow).join("")}</div>
      ${w.rushing_graded!=null&&Number(w.graded_players)>(w.sample_predictions||[]).length?`<button class="show-all-graded" type="button" data-week="${escapeHTML(w.week)}">Show all ${escapeHTML(w.graded_players)} graded players</button>`:""}
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
  const tdb=metrics.touchdown?.benchmark||{};
  const tdHtml=tdb.model_brier==null?"":`<article class="benchmark-card">
      <div class="benchmark-title">Touchdown</div>
      <div class="benchmark-values">
        <div><span>ML Brier</span><strong>${Number(tdb.model_brier).toFixed(4)}</strong></div>
        <div><span>Best baseline</span><strong>${tdb.best_baseline_brier==null?"—":Number(tdb.best_baseline_brier).toFixed(4)}</strong></div>
      </div>
      <div class="benchmark-foot"><span>${escapeHTML(tdb.baseline_labels?.[tdb.best_baseline]||tdb.best_baseline||"—")}</span>${tdb.beats_best_baseline
        ?`<span class="benchmark-win">ML better by ${Math.abs(Number(tdb.model_improvement_pct||0)).toFixed(1)}%</span>`
        :`<span class="benchmark-loss">Baseline better by ${Math.abs(Number(tdb.model_improvement_pct||0)).toFixed(1)}%</span>`}</div>
    </article>`;
  setHTML("benchmarks",(benchHtml+tdHtml) || "<div class=\"muted\">Benchmark data will appear after the next successful model run.</div>");
}

load().catch(e=>{
  console.error("Football Prop Edge render error:",e);
  const down=`<div class="results-empty"><strong>Predictions are temporarily unavailable.</strong><p>Please try again in a few minutes.</p></div>`;
  ["rows","rbCards","wrCards","tdCards"].forEach(id=>setHTML(id,down));
  setText("boardCount","");
  setText("updated","Couldn’t load the latest model run");
});
