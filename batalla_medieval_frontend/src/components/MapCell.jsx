import { memo } from 'react';

const relationColors = {
  own: 'shadow-[0_0_12px_2px_rgba(59,130,246,0.45)]',
  alliance: 'shadow-[0_0_12px_2px_rgba(52,211,153,0.45)]',
  enemy: 'shadow-[0_0_12px_2px_rgba(248,113,113,0.45)]',
  neutral: 'shadow-[0_0_10px_1px_rgba(120,113,108,0.35)]',
};

const MapCell = memo(
  ({ x, y, city, size, selected, onClick }) => {
    const relation = city?.relation || 'neutral';
    const glow = relationColors[relation] || relationColors.neutral;

    return (
      <div
        role="button"
        tabIndex={0}
        onClick={() => onClick({ x, y, city })}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            onClick({ x, y, city });
          }
        }}
        className={`absolute rounded-lg transition transform-gpu duration-150 ease-out group ${
          selected ? 'ring-2 ring-amber-300 drop-shadow-[0_0_8px_rgba(251,191,36,0.5)]' : ''
        }`}
        style={{
          width: size,
          height: size,
          left: 0,
          top: 0,
          transform: `translate(${x * size}px, ${y * size}px)`,
        }}
      >
        <div
          className={`w-full h-full rounded-lg border border-amber-900/70 bg-gradient-to-br from-emerald-900/70 via-emerald-800/80 to-emerald-900/80 relative overflow-hidden group-hover:border-amber-200/70 group-hover:shadow-[0_0_0_2px_rgba(251,191,36,0.35)] ${glow}`}
        >
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.05),transparent_60%)]" />
          <div className="absolute top-1 left-1 text-[10px] font-semibold text-amber-100/70 drop-shadow">
            {x},{y}
          </div>
          {city && (
            <div className="absolute inset-0 flex items-center justify-center text-amber-100">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="w-7 h-7 drop-shadow-[0_2px_4px_rgba(0,0,0,0.35)]"
              >
                <path d="M4 19h16v3H4z" className="fill-amber-900/60" />
                <path
                  className="fill-amber-300"
                  d="M5 9V7l2-1 2 1v2l-1 .5V14h2V5l3-1 3 1v9h2V9.5L17 9V7l2-1 2 1v5l-2 1v3h-4v-3h-2v3H7v-3l-2-.9V9Z"
                />
                <path className="fill-amber-100/90" d="M11 4h2v2h-2zM9 9h2v2H9zm4 0h2v2h-2z" />
              </svg>
              <span
                className={`absolute bottom-1 right-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full border border-amber-900/60 backdrop-blur ${
                  relation === 'own'
                    ? 'bg-blue-500/70 text-white'
                    : relation === 'alliance'
                      ? 'bg-green-500/70 text-white'
                      : relation === 'enemy'
                        ? 'bg-red-500/70 text-white'
                        : 'bg-stone-600/80 text-amber-100'
                }`}
              >
                {city.ownerTag || relation.toUpperCase()}
              </span>
            </div>
          )}
        </div>
      </div>
    );
  },
  (prev, next) =>
    prev.x === next.x && prev.y === next.y && prev.size === next.size && prev.selected === next.selected && prev.city === next.city,
);

export default MapCell;
