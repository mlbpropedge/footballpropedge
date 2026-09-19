const $=id=>document.getElementById(id);
function card(x,i,type){
 const isRush=type==="rush", isRec=type==="receive";
 const value=isRush?`${x.rushing_yards.toFixed(1)}<small> projected rush yds</small>`:isRec?`${x.receiving_yards.toFixed(1)}<small> projected rec yds</small>`:`${x.td_probability.toFixed(1)}%<small> TD probability</small>`;
 const chips=isRush?[ `${x.recent_carries} carries L3`,`${x.recent_rush_yards} rush yds L3`]:isRec?[`${x.recent_targets} targets L3`,`${x.recent_rec_yards} rec yds L3`]:[`${x.rushing_yards.toFixed(1)} rush yds`,`${x.receiving_yards.toFixed(1)} rec yds`];
 return `<article class="prediction-card ${type}"><div class="rank">#${i+1}</div><h3>${x.player}</h3><div class="meta">${x.position} • ${x.team} vs ${x.opponent}</div><div class="projection">${value}</div><div class="chip-row">${chips.map(c=>`<span class="chip">${c}</span>`).join("")}</div></article>`;
}
async function load(){
 const p=await fetch("data/predictions.json?x="+Date.now()).then(r=>r.json());
 $("updated").textContent="Updated "+new Date(p.generated_at).toLocaleString();
 $("weekBig").textContent=p.week;
 const rb=p.players.filter(x=>x.position==="RB").sort((a,b)=>b.rushing_yards-a.rushing_yards).slice(0,6);
 const wr=p.players.filter(x=>["WR","TE"].includes(x.position)).sort((a,b)=>b.receiving_yards-a.receiving_yards).slice(0,6);
 const td=[...p.players].sort((a,b)=>b.td_probability-a.td_probability).slice(0,6);
 $("rbCards").innerHTML=rb.map((x,i)=>card(x,i,"rush")).join("");
 $("wrCards").innerHTML=wr.map((x,i)=>card(x,i,"receive")).join("");
 $("tdCards").innerHTML=td.map((x,i)=>card(x,i,"touchdown")).join("");
}
load();