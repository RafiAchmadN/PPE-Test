// Satu sumber kebenaran untuk label/warna jenis pelanggaran APD — dipakai di
// ViolationsTable (badge) dan ViolationTypeChart (bar) supaya identitas warna
// per jenis konsisten di seluruh dashboard.
export const TYPE_LABELS = {
  'no-helmet': 'No Helmet',
  'no-vest': 'No Vest',
  'no-boots': 'No Boots',
  'no-goggles': 'No Goggles',
  'no-gloves': 'No Gloves',
};

export const TYPE_BADGE = {
  'no-helmet': 'badge-error badge-soft',
  'no-vest': 'badge-warning badge-soft',
  'no-boots': 'badge-primary badge-soft',
  'no-goggles': 'badge-secondary badge-soft',
  'no-gloves': 'badge-accent badge-soft',
};

export const TYPE_BAR_COLOR = {
  'no-helmet': 'bg-error',
  'no-vest': 'bg-warning',
  'no-boots': 'bg-primary',
  'no-goggles': 'bg-secondary',
  'no-gloves': 'bg-accent',
};

export function resolveType(jenis) {
  const j = jenis || '';
  return (
    Object.keys(TYPE_LABELS).find((k) => j.includes(k.replace('-', '_')) || j === k) || 'no-vest'
  );
}
