// Client-side filtering over the statically-rendered .edit-card list.
// No framework: the full dataset is already in the DOM (data-* attributes),
// this just toggles [hidden] and reorders siblings. Filter state round-trips
// through the URL query string so results are shareable/bookmarkable.
(() => {
  const feed = document.querySelector('[data-feed]');
  if (!feed) return;
  const cards = [...feed.querySelectorAll('.edit-card')];
  const countEl = document.querySelector('[data-filter-count]');
  const emptyEl = document.querySelector('[data-empty-state]');
  const searchEl = document.querySelector('[data-filter-search]');
  const sortEl = document.querySelector('[data-filter-sort]');
  const chipGroups = [...document.querySelectorAll('[data-filter-chips]')];
  const selects = [...document.querySelectorAll('[data-filter-select]')];
  const RANK = { NARRATIVE: 3, FACTUAL: 2, MINOR: 1, COSMETIC: 0 };

  const params = new URLSearchParams(location.search);
  const state = { q: params.get('q') || '' };
  for (const g of chipGroups) state[g.dataset.filterChips] = params.get(g.dataset.filterChips) || 'all';
  for (const s of selects) state[s.dataset.filterSelect] = params.get(s.dataset.filterSelect) || 'all';
  state.sort = params.get('sort') || 'newest';

  function syncControls() {
    if (searchEl) searchEl.value = state.q;
    if (sortEl) sortEl.value = state.sort;
    for (const g of chipGroups) {
      const key = g.dataset.filterChips;
      for (const chip of g.querySelectorAll('.chip')) {
        chip.classList.toggle('active', chip.dataset.value === state[key]);
      }
    }
    for (const s of selects) s.value = state[s.dataset.filterSelect];
  }

  function syncUrl() {
    const p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    if (state.sort !== 'newest') p.set('sort', state.sort);
    for (const g of chipGroups) {
      const key = g.dataset.filterChips;
      if (state[key] !== 'all') p.set(key, state[key]);
    }
    for (const s of selects) {
      const key = s.dataset.filterSelect;
      if (state[key] !== 'all') p.set(key, state[key]);
    }
    const qs = p.toString();
    history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
  }

  function apply() {
    const q = state.q.trim().toLowerCase();
    let visible = 0;
    for (const c of cards) {
      const matches = chipGroups.every((g) => {
        const key = g.dataset.filterChips;
        return state[key] === 'all' || c.dataset[key] === state[key];
      }) && selects.every((s) => {
        const key = s.dataset.filterSelect;
        return state[key] === 'all' || c.dataset[key] === state[key];
      }) && (!q || c.dataset.search.includes(q));
      c.hidden = !matches;
      if (matches) visible++;
    }
    if (countEl) countEl.textContent = `${visible} result${visible === 1 ? '' : 's'}`;
    if (emptyEl) emptyEl.hidden = visible !== 0;
    syncUrl();
  }

  function sortCards() {
    const sorted = [...cards].sort((a, b) => {
      if (state.sort === 'significant') {
        const d = RANK[b.dataset.severity] - RANK[a.dataset.severity];
        return d !== 0 ? d : b.dataset.score - a.dataset.score;
      }
      return b.dataset.detected.localeCompare(a.dataset.detected);
    });
    for (const c of sorted) feed.appendChild(c);
  }

  for (const g of chipGroups) {
    g.addEventListener('click', (e) => {
      const chip = e.target.closest('.chip');
      if (!chip) return;
      state[g.dataset.filterChips] = chip.dataset.value;
      syncControls();
      apply();
    });
  }
  for (const s of selects) {
    s.addEventListener('change', () => { state[s.dataset.filterSelect] = s.value; apply(); });
  }
  searchEl?.addEventListener('input', () => { state.q = searchEl.value; apply(); });
  sortEl?.addEventListener('change', () => { state.sort = sortEl.value; sortCards(); apply(); });

  syncControls();
  sortCards();
  apply();
})();
