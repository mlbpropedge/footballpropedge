const detail=document.getElementById("playerDetail");

function initials(name=""){
  const parts=String(name).replace(/[^A-Za-z' .-]/g," ").trim().split(/\s+/).filter(Boolean);
  return parts.length>1?(parts[0][0]+parts.at(-1)[0]).toUpperCase():(parts[0]?.[0]||"?").toUpperCase();
}
function fmtRange(range){
  return Array.isArray(range)&&range.length===2?`${Number(range[0]).toFixed(1)}–${Number(range[1]).toFixed(1)} yds`:"Pending";
}
function rankText(rank,total){
  return Number(rank)>0?`#${rank} of ${total||32}`:"Pending";
}
function bars(games,key){
  const max=Math.max(1,...games.map(g=>Number(g[key]||0)));
  return games.map(g=>`<div class="trend-row"><span>W${g.week}</span><div class="trend-track"><i style="width:${Math.max(4,Number(g[key]||0)/max*100)}%"></i></div><strong>${Number(g[key]||0).toFixed(1)}</strong></div>`).join("");
}
function metric(label,value,sub,accent){
  return `<div class="player-metric ${accent}"><span>${label}</span><strong>${value}</strong><small>${sub}</small></div>`;
}

async function loadPlayer(){
  const id=new URLSearchParams(location.search).get("id");
  const response=await fetch(`data/predictions.json?player=${Date.now()}`,{cache:"no-store"});
  if(!response.ok) throw new Error("Prediction data is unavailable.");
  const payload=await response.json();
  const player=(payload.players||[]).find(x=>String(x.player_id)===String(id));
  if(!player){
    detail.innerHTML=`<section class="player-empty"><h1>Player not found</h1><p>This player may no longer be on the current slate.</p><a class="primary-btn" href="index.html#all">Return to the full board</a></section>`;
    return;
  }
  document.title=`${player.player} • Football Prop Edge`;
  const context=player.season_context||{};
  const games=Array.isArray(context.recent_games)?context.recent_games:[];
  const rushReliability=Number(player.rush_reliability_score||0);
  const recReliability=Number(player.receiving_reliability_score||0);

  detail.innerHTML=`
    <section class="player-hero">
      <div class="player-identity"><span class="avatar player-avatar">${initials(player.player)}</span><div><p class="eyebrow">WEEK ${player.week} PLAYER BREAKDOWN</p><h1>${player.player}</h1><p>${player.position} • ${player.team} vs ${player.opponent}</p></div></div>
      <div class="player-status"><span>2026 data only</span><strong>${context.games_played??0} games tracked</strong></div>
    </section>
    <section class="player-metrics-grid">
      ${metric("Rushing",Number(player.rushing_yards||0).toFixed(1),"projected yards","rush-metric")}
      ${metric("Receiving",Number(player.receiving_yards||0).toFixed(1),"projected yards","rec-metric")}
      ${metric("Touchdown",Number(player.td_probability||0).toFixed(1)+"%","model probability","td-metric")}
    </section>
    <section class="detail-grid">
      <article class="detail-panel"><div class="panel-head"><div><p class="eyebrow">MODEL RANGE</p><h2>Projection detail</h2></div></div>
        <div class="detail-list">
          <div><span>Rushing 80% range</span><strong>${fmtRange(player.rushing_range_80)}</strong></div>
          <div><span>Receiving 80% range</span><strong>${fmtRange(player.receiving_range_80)}</strong></div>
          <div><span>Rushing reliability</span><strong>${rushReliability.toFixed(0)}/100</strong></div>
          <div><span>Receiving reliability</span><strong>${recReliability.toFixed(0)}/100</strong></div>
          <div><span>Rushing Edge Score</span><strong>${Number(player.rush_edge_score||0).toFixed(1)}</strong></div>
          <div><span>Receiving Edge Score</span><strong>${Number(player.receiving_edge_score||0).toFixed(1)}</strong></div>
        </div>
      </article>
      <article class="detail-panel"><div class="panel-head"><div><p class="eyebrow">MATCHUP</p><h2>Opponent defense</h2></div></div>
        <div class="defense-rank-grid">
          <div><span>vs ${player.position} rushing</span><strong>${rankText(player.opp_rush_def_rank,player.opp_def_rank_total)}</strong><small>No. 1 is toughest</small></div>
          <div><span>vs ${player.position} receiving</span><strong>${rankText(player.opp_rec_def_rank,player.opp_def_rank_total)}</strong><small>No. 1 is toughest</small></div>
        </div>
        <div class="matchup-bars"><div><span>Rush matchup</span><b><i style="width:${Number(player.rush_matchup_score||0)}%"></i></b><strong>${Number(player.rush_matchup_score||0).toFixed(0)}/100</strong></div><div><span>Rec matchup</span><b><i style="width:${Number(player.receiving_matchup_score||0)}%"></i></b><strong>${Number(player.receiving_matchup_score||0).toFixed(0)}/100</strong></div></div>
      </article>
    </section>
    <section class="detail-panel trends-panel"><div class="panel-head"><div><p class="eyebrow">2026 GAME TRENDS</p><h2>Completed games this season</h2></div><span>Earlier seasons excluded</span></div>
      ${games.length?`<div class="trend-columns"><div><h3>Rushing yards</h3>${bars(games,"rushing_yards")}</div><div><h3>Receiving yards</h3>${bars(games,"receiving_yards")}</div></div><div class="season-averages"><span>2026 rush avg <b>${Number(context.season_rushing_avg||0).toFixed(1)}</b></span><span>2026 rec avg <b>${Number(context.season_receiving_avg||0).toFixed(1)}</b></span><span>Carries/game <b>${Number(context.season_carries_avg||0).toFixed(1)}</b></span><span>Targets/game <b>${Number(context.season_targets_avg||0).toFixed(1)}</b></span></div>`:`<div class="results-empty"><strong>No completed 2026 games yet.</strong><p>Trend charts will appear once current-season results are available.</p></div>`}
    </section>
    <details class="explain-panel"><summary>How should I read these numbers?</summary><p>Ranges show where 80% of comparable leakage-safe historical errors landed. Reliability rewards tighter historical ranges and steadier workload. Edge Score is a ranking tool—not a probability or guarantee. Defense ranks are position-specific, with No. 1 representing the toughest matchup.</p></details>
  `;
}
loadPlayer().catch(error=>{detail.innerHTML=`<section class="player-empty"><h1>Could not load this player</h1><p>${error.message}</p><a class="primary-btn" href="index.html">Return home</a></section>`;});
