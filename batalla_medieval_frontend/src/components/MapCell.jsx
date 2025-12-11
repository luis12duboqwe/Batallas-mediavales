import { memo } from 'react';

const relationColors = {
  own: 'border-blue-400 shadow-[0_0_0_2px_rgba(59,130,246,0.4)]',
  alliance: 'border-green-400 shadow-[0_0_0_2px_rgba(74,222,128,0.35)]',
  enemy: 'border-red-500 shadow-[0_0_0_2px_rgba(239,68,68,0.35)]',
  neutral: 'border-gray-500 shadow-[0_0_0_2px_rgba(156,163,175,0.25)]',
};

const MapCell = memo(({ x, y, city, size, selected, onClick }) => {
  const relation = city?.relation || 'neutral';
  const borderClass = relationColors[relation] || relationColors.neutral;

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
      className={`absolute rounded transition transform-gpu duration-150 ease-out group ${selected ? 'ring-2 ring-yellow-400 z-10' : ''}`}
      style={{
        width: size,
        height: size,
        left: 0,
        top: 0,
        transform: `translate(${x * size}px, ${y * size}px)`,
      }}
    >
      <div
        className={`w-full h-full rounded bg-gray-900/70 border ${borderClass} relative overflow-hidden group-hover:border-yellow-400 group-hover:shadow-[0_0_0_2px_rgba(250,204,21,0.45)]`}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-gray-900/40 to-gray-800/20" />
        <div className="absolute top-1 left-1 text-[10px] text-gray-500">
          {x},{y}
        </div>
        {city && (
          <div className="absolute inset-0 flex items-center justify-center text-yellow-200">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="w-6 h-6 drop-shadow"
            >
              <path d="M12 2 3 7v15h18V7l-9-5Zm0 2.236 6 3.333V20H6V7.569l6-3.333ZM10 10v6h4v-6h-4Z" />
            </svg>
            <span
              className={`absolute bottom-1 right-1 text-[10px] font-semibold px-1 rounded ${
                relation === 'own'
                  ? 'bg-blue-500/60 text-white'
                  : relation === 'alliance'
                    ? 'bg-green-500/70 text-white'
                    : relation === 'enemy'
                      ? 'bg-red-500/70 text-white'
                      : 'bg-gray-600/70 text-gray-200'
              }`}
            >
              {city.ownerTag || relation.toUpperCase()}
            </span>
          </div>
        )}
      </div>
    </div>
  );
});

export default MapCell;
