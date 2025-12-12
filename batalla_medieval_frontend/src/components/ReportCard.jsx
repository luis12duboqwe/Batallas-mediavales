import { useMemo, useState } from 'react';
import { formatDate, formatNumber } from '../utils/format';
import { TROOP_TYPES } from '../utils/gameMath';

const ArrowIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5 text-amber-300" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M5 12h14m0 0-4-4m4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const BattleIcon = () => (
  <span className="flex h-11 w-11 items-center justify-center rounded-full bg-amber-500/15 ring-1 ring-amber-400/50">
    <svg viewBox="0 0 24 24" className="h-6 w-6 text-amber-200" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path
        d="m8.5 5.5 3.75 3.75M8.5 5.5 6 3m2.5 2.5L3 11m9.25-1.75L16 13M12.25 9.25 19 3m-3 10 2.5 2.5M16 13l3.5 3.5m0 0L19 21m.5-4.5L23 21"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  </span>
);

const SpyIcon = () => (
  <span className="flex h-11 w-11 items-center justify-center rounded-full bg-sky-500/15 ring-1 ring-sky-400/50">
    <svg viewBox="0 0 24 24" className="h-6 w-6 text-sky-200" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path
        d="M2.75 12s2.75-5.25 9.25-5.25S21.25 12 21.25 12 18.5 17.25 12 17.25 2.75 12 2.75 12Z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="2.75" />
    </svg>
  </span>
);

const TradeIcon = () => (
  <span className="flex h-11 w-11 items-center justify-center rounded-full bg-green-500/15 ring-1 ring-green-400/50">
    <svg viewBox="0 0 24 24" className="h-6 w-6 text-green-200" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </span>
);

const ReturnIcon = () => (
  <span className="flex h-11 w-11 items-center justify-center rounded-full bg-blue-500/15 ring-1 ring-blue-400/50">
    <svg viewBox="0 0 24 24" className="h-6 w-6 text-blue-200" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </span>
);

const ReinforceIcon = () => (
  <span className="flex h-11 w-11 items-center justify-center rounded-full bg-purple-500/15 ring-1 ring-purple-400/50">
    <svg viewBox="0 0 24 24" className="h-6 w-6 text-purple-200" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </span>
);

const ResourceIcon = ({ type }) => {
  const icons = {
    wood: (
      <path
        d="M9 3.5 7 12l4 8 4-8-2-8.5M7 12h10"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
    clay: (
      <path
        d="M4 14.5 12 4l8 10.5-8 5.5-8-5.5Z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
    iron: (
      <path
        d="M4.5 9.5 12 4l7.5 5.5L12 20 4.5 9.5Zm0 0h15"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
  };

  return (
    <svg
      viewBox="0 0 24 24"
      className="h-5 w-5 text-amber-200"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
    >
      {icons[type] ?? icons.wood}
    </svg>
  );
};

const CrackedWallIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5 text-amber-200" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M4 4h16v16H4z" />
    <path d="M10 4v6l4 4v6" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M4 10h6m4 0h6M4 16h8m4 0h4" />
  </svg>
);

const ReportCard = ({ report }) => {
  const [expanded, setExpanded] = useState(false);

  const parsedContent = useMemo(() => {
    try {
      return JSON.parse(report.content);
    } catch (e) {
      return null; // Legacy HTML content
    }
  }, [report.content]);

  const isBattle = report.report_type === 'battle';
  const isSpy = report.report_type === 'spy';

  if (!parsedContent) {
    // Legacy HTML rendering
    return (
      <div className="card bg-black/40 border border-amber-900/30 p-4">
        <div className="flex justify-between items-center mb-2">
          <h3 className="font-bold text-amber-100">Reporte #{report.id}</h3>
          <span className="text-xs text-gray-400">{formatDate(report.created_at)}</span>
        </div>
        <div 
          className="prose prose-invert prose-sm max-w-none"
          dangerouslySetInnerHTML={{ __html: report.content }} 
        />
      </div>
    );
  }

  // New JSON rendering
  const { 
    attacker, defender, loot, wall_damage, loyalty_change, conquest, moral, luck, success, 
    resources, troops, buildings,
    sender, receiver, from // New fields
  } = parsedContent;

  const isTrade = report.report_type === 'trade';
  const isReturn = report.report_type === 'return';
  const isReinforce = report.report_type === 'reinforce';

  return (
    <div className={`card bg-black/40 border border-amber-900/30 overflow-hidden transition-all duration-300 ${expanded ? 'ring-1 ring-amber-500/50' : ''}`}>
      {/* Header Summary */}
      <div 
        className="p-4 cursor-pointer hover:bg-white/5 flex items-center gap-4"
        onClick={() => setExpanded(!expanded)}
      >
        {isBattle && <BattleIcon />}
        {isSpy && <SpyIcon />}
        {isTrade && <TradeIcon />}
        {isReturn && <ReturnIcon />}
        {isReinforce && <ReinforceIcon />}
        
        <div className="flex-1">
          <div className="flex justify-between items-center">
            <h3 className="font-bold text-amber-100 text-lg">
              {isBattle && `Batalla en ${defender.name}`}
              {isSpy && `Espionaje en ${defender.name}`}
              {isTrade && `Comercio`}
              {isReturn && `Tropas regresaron`}
              {isReinforce && `Refuerzos`}
            </h3>
            <span className="text-xs text-gray-400">{formatDate(report.created_at)}</span>
          </div>
          
          <div className="flex items-center gap-2 text-sm mt-1">
            {isBattle && (
              <>
                <span className="text-red-400 font-semibold">{attacker.name}</span>
                <span className="text-gray-500">vs</span>
                <span className="text-blue-400 font-semibold">{defender.name}</span>
              </>
            )}
            {isSpy && (
              <>
                <span className="text-red-400 font-semibold">{attacker.name}</span>
                <span className="text-gray-500">vs</span>
                <span className="text-blue-400 font-semibold">{defender.name}</span>
              </>
            )}
            {isTrade && (
              <>
                <span className="text-green-400 font-semibold">{sender?.name}</span>
                <span className="text-gray-500">→</span>
                <span className="text-green-400 font-semibold">{receiver?.name}</span>
              </>
            )}
            {isReturn && (
              <>
                <span className="text-gray-400">Desde:</span>
                <span className="text-blue-400 font-semibold">{from?.name}</span>
              </>
            )}
            {isReinforce && (
              <>
                <span className="text-purple-400 font-semibold">{sender?.name}</span>
                <span className="text-gray-500">→</span>
                <span className="text-purple-400 font-semibold">{receiver?.name}</span>
              </>
            )}
          </div>
        </div>

        <div className={`transform transition-transform ${expanded ? 'rotate-180' : ''}`}>
          <svg viewBox="0 0 24 24" className="h-6 w-6 text-gray-500" fill="none" stroke="currentColor">
            <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
          </svg>
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="p-4 border-t border-gray-800 bg-black/20 space-y-6">
          
          {/* Trade Details */}
          {isTrade && resources && (
            <div className="bg-green-900/10 border border-green-900/30 rounded p-3">
              <h4 className="font-bold text-green-400 mb-2">Recursos Transferidos</h4>
              <div className="flex gap-6 text-sm">
                <div className="flex items-center gap-2"><ResourceIcon type="wood" /> {formatNumber(resources.wood)}</div>
                <div className="flex items-center gap-2"><ResourceIcon type="clay" /> {formatNumber(resources.clay)}</div>
                <div className="flex items-center gap-2"><ResourceIcon type="iron" /> {formatNumber(resources.iron)}</div>
              </div>
            </div>
          )}

          {/* Return Details */}
          {isReturn && (
            <div className="bg-blue-900/10 border border-blue-900/30 rounded p-3">
              <h4 className="font-bold text-blue-400 mb-2">Tropas Retornadas</h4>
              <div className="space-y-1 text-sm">
                {troops && Object.entries(troops).map(([unit, count]) => (
                  <div key={unit} className="flex justify-between">
                    <span className="text-gray-300">{TROOP_TYPES[unit] || unit}</span>
                    <span className="text-gray-200">{count}</span>
                  </div>
                ))}
                {(!troops || Object.keys(troops).length === 0) && <p className="text-gray-500 italic">Sin tropas</p>}
              </div>
              {resources && Object.values(resources).some(v => v > 0) && (
                <div className="mt-4 pt-2 border-t border-blue-900/30">
                  <h5 className="font-bold text-blue-300 mb-2 text-xs uppercase">Recursos Traídos</h5>
                  <div className="flex gap-4 text-sm">
                    {resources.wood > 0 && <div className="flex items-center gap-1"><ResourceIcon type="wood" /> {formatNumber(resources.wood)}</div>}
                    {resources.clay > 0 && <div className="flex items-center gap-1"><ResourceIcon type="clay" /> {formatNumber(resources.clay)}</div>}
                    {resources.iron > 0 && <div className="flex items-center gap-1"><ResourceIcon type="iron" /> {formatNumber(resources.iron)}</div>}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Reinforce Details */}
          {isReinforce && troops && (
            <div className="bg-purple-900/10 border border-purple-900/30 rounded p-3">
              <h4 className="font-bold text-purple-400 mb-2">Tropas de Refuerzo</h4>
              <div className="space-y-1 text-sm">
                {Object.entries(troops).map(([unit, count]) => (
                  <div key={unit} className="flex justify-between">
                    <span className="text-gray-300">{TROOP_TYPES[unit] || unit}</span>
                    <span className="text-gray-200">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Battle Details */}
          {isBattle && (
            <>
              {/* Troops Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Attacker */}
                <div className="bg-red-900/10 border border-red-900/30 rounded p-3">
                  <h4 className="font-bold text-red-400 mb-2 border-b border-red-900/30 pb-1">Atacante</h4>
                  <div className="space-y-1 text-sm">
                    {Object.entries(attacker.initial).map(([unit, count]) => {
                      const loss = attacker.losses[unit] || 0;
                      if (count === 0) return null;
                      return (
                        <div key={unit} className="flex justify-between">
                          <span className="text-gray-300">{TROOP_TYPES[unit] || unit}</span>
                          <span className="text-gray-400">
                            {count} <span className="text-red-500">(-{loss})</span>
                          </span>
                        </div>
                      );
                    })}
                    {Object.keys(attacker.initial).length === 0 && <p className="text-gray-500 italic">Sin tropas</p>}
                  </div>
                </div>

                {/* Defender */}
                <div className="bg-blue-900/10 border border-blue-900/30 rounded p-3">
                  <h4 className="font-bold text-blue-400 mb-2 border-b border-blue-900/30 pb-1">Defensor</h4>
                  <div className="space-y-1 text-sm">
                    {Object.entries(defender.initial).map(([unit, count]) => {
                      const loss = defender.losses[unit] || 0;
                      if (count === 0) return null;
                      return (
                        <div key={unit} className="flex justify-between">
                          <span className="text-gray-300">{TROOP_TYPES[unit] || unit}</span>
                          <span className="text-gray-400">
                            {count} <span className="text-red-500">(-{loss})</span>
                          </span>
                        </div>
                      );
                    })}
                    {Object.keys(defender.initial).length === 0 && <p className="text-gray-500 italic">Sin tropas</p>}
                  </div>
                </div>
              </div>

              {/* Loot & Outcome */}
              <div className="bg-amber-900/10 border border-amber-900/30 rounded p-3">
                <h4 className="font-bold text-amber-400 mb-2">Resultado</h4>
                <div className="flex flex-wrap gap-4 text-sm">
                  {loot && (
                    <div className="flex gap-3 items-center bg-black/30 px-3 py-1 rounded">
                      <span className="text-gray-400">Botín:</span>
                      <div className="flex items-center gap-1"><ResourceIcon type="wood" /> {formatNumber(loot.wood)}</div>
                      <div className="flex items-center gap-1"><ResourceIcon type="clay" /> {formatNumber(loot.clay)}</div>
                      <div className="flex items-center gap-1"><ResourceIcon type="iron" /> {formatNumber(loot.iron)}</div>
                    </div>
                  )}
                  
                  {wall_damage && (
                    <div className="flex items-center gap-2 text-amber-200">
                      <CrackedWallIcon />
                      <span>Muralla: {wall_damage[0]} → {wall_damage[1]}</span>
                    </div>
                  )}

                  {loyalty_change > 0 && (
                    <div className="text-red-400 font-bold">
                      Lealtad reducida en {loyalty_change}
                    </div>
                  )}

                  {conquest && (
                    <div className="w-full text-center py-2 bg-amber-500/20 text-amber-200 font-bold rounded border border-amber-500/50 animate-pulse">
                      ¡CIUDAD CONQUISTADA!
                    </div>
                  )}
                </div>
                
                <div className="mt-3 pt-2 border-t border-gray-800 flex gap-4 text-xs text-gray-500">
                  <span>Moral: {(moral * 100).toFixed(0)}%</span>
                  <span>Suerte: {(luck * 100).toFixed(1)}%</span>
                </div>
              </div>
            </>
          )}

          {/* Spy Details */}
          {isSpy && (
            <div className="space-y-4">
              <div className={`p-3 rounded border ${success ? 'bg-green-900/10 border-green-900/30' : 'bg-red-900/10 border-red-900/30'}`}>
                <h4 className={`font-bold ${success ? 'text-green-400' : 'text-red-400'} mb-2`}>
                  {success ? '¡Espionaje Exitoso!' : 'Misión Fallida'}
                </h4>
                <div className="flex justify-between text-sm text-gray-300">
                  <span>Espías enviados: {attacker.spies}</span>
                  <span>Espías defensores: {defender.spies}</span>
                </div>
              </div>

              {success && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {resources && (
                    <div className="bg-black/20 p-3 rounded border border-gray-800">
                      <h5 className="font-bold text-amber-200 mb-2 text-sm">Recursos</h5>
                      <div className="space-y-1 text-sm">
                        <div className="flex justify-between"><span>Madera</span><span>{formatNumber(resources.wood)}</span></div>
                        <div className="flex justify-between"><span>Barro</span><span>{formatNumber(resources.clay)}</span></div>
                        <div className="flex justify-between"><span>Hierro</span><span>{formatNumber(resources.iron)}</span></div>
                      </div>
                    </div>
                  )}
                  
                  {troops && (
                    <div className="bg-black/20 p-3 rounded border border-gray-800">
                      <h5 className="font-bold text-amber-200 mb-2 text-sm">Tropas</h5>
                      <div className="space-y-1 text-sm">
                        {Object.entries(troops).map(([unit, count]) => (
                          <div key={unit} className="flex justify-between">
                            <span className="text-gray-400">{TROOP_TYPES[unit] || unit}</span>
                            <span className="text-gray-200">{count}</span>
                          </div>
                        ))}
                        {Object.keys(troops).length === 0 && <span className="text-gray-500 italic">Sin tropas</span>}
                      </div>
                    </div>
                  )}

                  {buildings && (
                    <div className="bg-black/20 p-3 rounded border border-gray-800">
                      <h5 className="font-bold text-amber-200 mb-2 text-sm">Edificios</h5>
                      <div className="space-y-1 text-sm">
                        {Object.entries(buildings).map(([name, level]) => (
                          <div key={name} className="flex justify-between">
                            <span className="text-gray-400">{name}</span>
                            <span className="text-amber-500">Nivel {level}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

        </div>
      )}
    </div>
  );
};

export default ReportCard;
