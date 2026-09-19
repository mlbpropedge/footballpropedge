(() => {
  const fmt = range => Array.isArray(range) && range.length === 2
    ? `${Number(range[0]).toFixed(1)}–${Number(range[1]).toFixed(1)} yds`
    : null;

  const style = document.createElement("style");
  style.textContent = `.prediction-range{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:-2px 0 10px;padding:8px 10px;border:1px solid #20344b;border-radius:10px;background:#0b1622}.prediction-range span{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#8196ac}.prediction-range strong{font-size:13px;color:#dce8f5;white-space:nowrap}`;
  document.head.appendChild(style);

  async function addRanges() {
    try {
      const r = await fetch(`data/predictions.json?range=${Date.now()}`, {cache: "no-store"});
      if (!r.ok) return;
      const data = await r.json();
      const players = new Map((data.players || []).map(x => [x.player, x]));
      document.querySelectorAll(".prediction-card").forEach(card => {
        if (card.querySelector(".prediction-range")) return;
        const name = card.querySelector("h3")?.textContent?.trim();
        const row = players.get(name);
        if (!row) return;
        const isRush = card.classList.contains("rush");
        const isRec = card.classList.contains("receive");
        if (!isRush && !isRec) return;
        const text = fmt(isRush ? row.rushing_range_80 : row.receiving_range_80);
        if (!text) return;
        const projection = card.querySelector(".projection");
        if (!projection) return;
        const el = document.createElement("div");
        el.className = "prediction-range";
        el.innerHTML = `<span>80% model range</span><strong>${text}</strong>`;
        projection.insertAdjacentElement("afterend", el);
      });
    } catch (e) {
      console.warn("Prediction ranges unavailable", e);
    }
  }

  const observer = new MutationObserver(addRanges);
  observer.observe(document.documentElement, {subtree:true, childList:true});
  window.addEventListener("load", addRanges);
  addRanges();
})();
