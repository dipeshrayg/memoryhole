// Shared category/severity vocabulary + display metadata for every page.
// Keep in sync with pipeline/memoryhole/config.py CATEGORIES.

export const CATEGORIES = {
  world: { label: 'World', color: '#2563eb' },
  politics: { label: 'Politics', color: '#7c3aed' },
  business: { label: 'Business', color: '#0e7490' },
  finance: { label: 'Finance', color: '#b45309' },
  science: { label: 'Science', color: '#0d9488' },
  technology: { label: 'Technology', color: '#4f46e5' },
  sport: { label: 'Sport', color: '#16a34a' },
  health: { label: 'Health', color: '#db2777' },
  culture: { label: 'Culture', color: '#9333ea' },
  government: { label: 'Government', color: '#64748b' },
};

export const SEVERITIES = {
  NARRATIVE: { label: 'Narrative', rank: 3, hint: 'Claims added or removed, meaning shifted' },
  FACTUAL: { label: 'Factual', rank: 2, hint: 'Numbers, names, or dates changed' },
  MINOR: { label: 'Minor', rank: 1, hint: 'Reworded, same meaning' },
  COSMETIC: { label: 'Cosmetic', rank: 0, hint: 'Typos and formatting only' },
};

export const categoryLabel = (cat) => (CATEGORIES[cat] || CATEGORIES.world).label;
export const categoryColor = (cat) => (CATEGORIES[cat] || CATEGORIES.world).color;
