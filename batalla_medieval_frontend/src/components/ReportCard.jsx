import { useMemo } from 'react';
import { formatDate, formatNumber } from '../utils/format';

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

const parseNumber = (value) => {
  const parsed = Number(String(value).replace(/[^0-9.-]/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
};

const parseTroopList = (ul) => {
  const troops = {};
  if (!ul) return troops;
  ul.querySelectorAll('li').forEach((li) => {
    const [unit, amountRaw] = li.textContent.split(':');
    if (!amountRaw) return;
    const amount = parseNumber(amountRaw);
    troops[unit.trim()] = amount;
  });
  return troops;
};

const parseBattleContent = (content) => {
  if (typeof window === 'undefined') return {};
  const parser = new DOMParser();
  const doc = parser.parseFromString(content || '', 'text/html');
  const paragraphs = Array.from(doc.querySelectorAll('p'));

  const getCityFromLabel = (label) => {
    const line = paragraphs.find((p) => p.textContent.toLowerCase().includes(label));
    if (!line) return '';
    const [, value = ''] = line.textContent.split(':');
    return value.split('(')[0].trim();
  };

  const uls = Array.from(doc.querySelectorAll('ul'));
  const survivorsAtt = parseTroopList(uls[0]);
  const survivorsDef = parseTroopList(uls[1]);
  const lossesAtt = parseTroopList(uls[2]);
  const lossesDef = parseTroopList(uls[3]);

  const lootLine = paragraphs.find((p) => p.textContent.toLowerCase().includes('madera'));
  const loot = lootLine
    ? {
        wood: parseNumber(/Madera:\s*([0-9]+)/i.exec(lootLine.textContent)?.[1]),
        clay: parseNumber(/Barro:\s*([0-9]+)/i.exec(lootLine.textContent)?.[1]),
        iron: parseNumber(/Hierro:\s*([0-9]+)/i.exec(lootLine.textContent)?.[1]),
      }
    : null;

  const wallParagraph = paragraphs.find((p) => p.textContent.includes('Muralla dañada'));
  const wallDamage = wallParagraph
    ? (() => {
        const match = /Muralla dañada: Nivel\s*([0-9]+)\s*→\s*Nivel\s*([0-9]+)/.exec(wallParagraph.textContent);
        if (!match) return null;
        return { from: parseNumber(match[1]), to: parseNumber(match[2]) };
      })()
    : null;

  const moraleLine = paragraphs.find((p) => p.textContent.toLowerCase().includes('moral aplicada'));
  const morale = moraleLine ? parseFloat(/Moral aplicada:\s*([0-9.]+)/i.exec(moraleLine.textContent)?.[1]) : null;
  const luck = moraleLine ? parseFloat(/Suerte:\s*([0-9.]+)/i.exec(moraleLine.textContent)?.[1]) : null;

  const powerLine = paragraphs.find((p) => p.textContent.toLowerCase().includes('ataque efectivo'));
  const attackPower = powerLine ? parseFloat(/Ataque efectivo:\s*([0-9.]+)/i.exec(powerLine.textContent)?.[1]) : null;
  const defensePower = powerLine ? parseFloat(/Defensa efectiva:\s*([0-9.]+)/i.exec(powerLine.textContent)?.[1]) : null;

  return {
    attacker: getCityFromLabel('atacante'),
    defender: getCityFromLabel('defensor'),
    survivors: { attacker: survivorsAtt, defender: survivorsDef },
    losses: { attacker: lossesAtt, defender: lossesDef },
    loot,
    wallDamage,
    morale,
    luck,
    attackPower,
    defensePower,
  };
};

const parseSpyContent = (content) => {
  if (typeof window === 'undefined') return {};
  const parser = new DOMParser();
  const doc = parser.parseFromString(content || '', 'text/html');
  const paragraphs = Array.from(doc.querySelectorAll('p'));

  const textFromLabel = (label) => {
    const line = paragraphs.find((p) => p.textContent.toLowerCase().includes(label));
    if (!line) return '';
    const [, value = ''] = line.textContent.split(':');
    return value.trim();
  };

  const success = textFromLabel('resultado').toLowerCase().includes('éxito');

  const resources = {};
  const troops = {};
  const buildings = {};

  const listByHeading = (heading) => {
    const h3s = Array.from(doc.querySelectorAll('h3'));
    const target = h3s.find((h) => h.textContent.toLowerCase().includes(heading));
    if (!target) return null;
    const list = target.nextElementSibling?.tagName === 'UL' ? target.nextElementSibling : null;
    return list;
  };

  const resourceList = listByHeading('recursos');
  resourceList?.querySelectorAll('li').forEach((li) => {
    const [name, amountRaw] = li.textContent.split(':');
    resources[name?.toLowerCase()] = parseNumber(amountRaw);
  });

  const troopList = listByHeading('tropas');
  troopList?.querySelectorAll('li').forEach((li) => {
    const [unit, amountRaw] = li.textContent.split(':');
    troops[unit?.trim()] = parseNumber(amountRaw);
  });

  const buildingList = listByHeading('edificios');
  buildingList?.querySelectorAll('li').forEach((li) => {
    const [name, levelRaw] = li.textContent.split(':');
    buildings[name?.trim()] = parseNumber(levelRaw);
  });

  return {
    attacker: textFromLabel('atacante'),
    defender: textFromLabel('defensor'),
    success,
    resources,
    troops,
    buildings,
    spies: textFromLabel('espías atacantes'),
  };
};

const TroopTable = ({ title, survivors = {}, losses = {} }) => {
  const units = Array.from(new Set([...Object.keys(survivors), ...Object.keys(losses)]));

  return (
    <div className="flex-1 rounded-xl border border-amber-400/20 bg-amber-900/20 px-4 py-3 shadow-inner shadow-black/30">
      <div className="flex items-center justify-between pb-2">
        <p className="text-sm uppercase tracking-wide text-amber-200/90">{title}</p>
        <span className="text-xs text-amber-100/70">Enviado / Perdido / Vivo</span>
      </div>
      <div className="space-y-2">
        {units.length === 0 && <p className="text-sm text-amber-100/60">Sin tropas</p>}
        {units.map((unit) => {
          const survived = survivors[unit] ?? 0;
          const lost = losses[unit] ?? 0;
          const sent = survived + lost;
          return (
            <div key={unit} className="flex items-center justify-between rounded-lg bg-black/20 px-3 py-2">
              <div className="flex items-center gap-2 text-amber-50">
                <span className="text-xs font-semibold uppercase tracking-wide text-amber-200/90">{unit}</span>
              </div>
              <div className="flex items-center gap-3 text-sm font-medium text-amber-100">
                <span className="min-w-[72px] text-right text-amber-50/90">{formatNumber(sent)}</span>
                <span className="min-w-[72px] text-right text-rose-200/90">{formatNumber(lost)}</span>
                <span className="min-w-[72px] text-right text-emerald-200/90">{formatNumber(survived)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ResourcePill = ({ type, amount }) => (
  <div className="flex flex-1 items-center gap-2 rounded-lg border border-amber-400/30 bg-black/25 px-3 py-2 text-amber-50 shadow-inner shadow-black/20">
    <ResourceIcon type={type} />
    <span className="text-sm capitalize text-amber-100/90">{type}</span>
    <span className="ml-auto text-base font-semibold text-amber-50">{formatNumber(amount || 0)}</span>
  </div>
);

const SectionTitle = ({ children }) => (
  <h4 className="text-sm uppercase tracking-[0.2em] text-amber-200/80">{children}</h4>
);

const ReportCard = ({ report }) => {
  const parsed = useMemo(() => {
    if (report.report_type === 'battle') {
      return parseBattleContent(report.content);
    }
    if (report.report_type === 'spy') {
      return parseSpyContent(report.content);
    }
    return {};
  }, [report]);

  const isBattle = report.report_type === 'battle';
  const headerIcon = isBattle ? <BattleIcon /> : <SpyIcon />;

  return (
    <div className="overflow-hidden rounded-2xl border border-amber-400/30 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.08),_rgba(109,72,27,0.08))] shadow-2xl shadow-amber-900/30">
      <div className="flex flex-col gap-3 border-b border-amber-400/20 bg-amber-900/30 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          {headerIcon}
          <div>
            <div className="flex flex-wrap items-center gap-2 text-amber-50">
              <span className="rounded-full bg-black/30 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-amber-200">
                {isBattle ? 'Batalla' : 'Espionaje'}
              </span>
              <div className="flex items-center gap-2 text-base font-semibold">
                <span className="text-amber-50/90">{parsed.attacker || 'Ciudad atacante'}</span>
                <ArrowIcon />
                <span className="text-amber-50">{parsed.defender || 'Ciudad objetivo'}</span>
              </div>
            </div>
            <p className="text-sm text-amber-100/70">{formatDate(report.created_at || report.createdAt)}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          {isBattle && parsed.morale !== null && !Number.isNaN(parsed.morale) && (
            <span className="rounded-full bg-amber-500/15 px-3 py-1 font-semibold text-amber-100">
              Moral {parsed.morale}
            </span>
          )}
          {isBattle && parsed.luck !== null && !Number.isNaN(parsed.luck) && (
            <span className="rounded-full bg-sky-500/15 px-3 py-1 font-semibold text-sky-100">
              Suerte {parsed.luck}
            </span>
          )}
          {isBattle && parsed.attackPower !== null && (
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 font-semibold text-emerald-100">
              Ataque {parsed.attackPower}
            </span>
          )}
          {isBattle && parsed.defensePower !== null && (
            <span className="rounded-full bg-indigo-500/15 px-3 py-1 font-semibold text-indigo-100">
              Defensa {parsed.defensePower}
            </span>
          )}
          {!isBattle && (
            <span
              className={`rounded-full px-3 py-1 font-semibold ${
                parsed.success ? 'bg-emerald-500/15 text-emerald-100' : 'bg-rose-500/15 text-rose-100'
              }`}
            >
              {parsed.success ? 'Misión exitosa' : 'Misión fallida'}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-4 p-5">
        {isBattle ? (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <TroopTable title="Atacante" survivors={parsed.survivors?.attacker} losses={parsed.losses?.attacker} />
              <TroopTable title="Defensor" survivors={parsed.survivors?.defender} losses={parsed.losses?.defender} />
            </div>

            {parsed.loot && (
              <div className="rounded-2xl border border-amber-400/25 bg-amber-900/20 p-4 shadow-inner shadow-black/30">
                <div className="mb-3 flex items-center gap-2">
                  <SectionTitle>Botín obtenido</SectionTitle>
                  <span className="text-xs text-amber-100/70">Recursos saqueados durante la batalla</span>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <ResourcePill type="wood" amount={parsed.loot.wood} />
                  <ResourcePill type="clay" amount={parsed.loot.clay} />
                  <ResourcePill type="iron" amount={parsed.loot.iron} />
                </div>
              </div>
            )}

            {parsed.wallDamage && (
              <div className="flex items-center gap-3 rounded-xl border border-amber-400/25 bg-black/30 px-4 py-3 text-amber-50 shadow-inner shadow-black/40">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/15 ring-1 ring-amber-400/40">
                  <CrackedWallIcon />
                </span>
                <div>
                  <p className="text-sm font-semibold">Muralla dañada</p>
                  <p className="text-sm text-amber-100/80">
                    Nivel {parsed.wallDamage.from} → Nivel {parsed.wallDamage.to}
                  </p>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-sky-400/25 bg-sky-900/20 p-3 text-sky-50 shadow-inner shadow-black/30">
                <SectionTitle>Detalles</SectionTitle>
                <ul className="mt-2 space-y-1 text-sm text-sky-100/90">
                  <li>
                    <span className="text-sky-200">Atacante:</span> {parsed.attacker || '—'}
                  </li>
                  <li>
                    <span className="text-sky-200">Defensor:</span> {parsed.defender || '—'}
                  </li>
                  <li>
                    <span className="text-sky-200">Espías enviados:</span> {parsed.spies || '—'}
                  </li>
                </ul>
              </div>

              {(parsed.resources && Object.keys(parsed.resources).length > 0) || (
                parsed.troops && Object.keys(parsed.troops).length > 0
              ) ? (
                <div className="rounded-xl border border-amber-400/25 bg-amber-900/20 p-3 text-amber-50 shadow-inner shadow-black/30">
                  <SectionTitle>Descubrimientos</SectionTitle>
                  <div className="mt-2 space-y-2 text-sm text-amber-100/90">
                    {Object.keys(parsed.resources || {}).length > 0 && (
                      <p>
                        <span className="text-amber-200">Recursos:</span>{' '}
                        {Object.entries(parsed.resources)
                          .map(([name, amount]) => `${name}: ${formatNumber(amount)}`)
                          .join(' | ')}
                      </p>
                    )}
                    {Object.keys(parsed.troops || {}).length > 0 && (
                      <p>
                        <span className="text-amber-200">Tropas:</span>{' '}
                        {Object.entries(parsed.troops)
                          .map(([name, qty]) => `${name}: ${formatNumber(qty)}`)
                          .join(' | ')}
                      </p>
                    )}
                    {Object.keys(parsed.buildings || {}).length > 0 && (
                      <p>
                        <span className="text-amber-200">Edificios:</span>{' '}
                        {Object.entries(parsed.buildings)
                          .map(([name, lvl]) => `${name}: Nivel ${formatNumber(lvl)}`)
                          .join(' | ')}
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="rounded-xl border border-amber-400/25 bg-black/20 p-3 text-sm text-amber-100/90 shadow-inner shadow-black/30">
                  Sin información adicional recopilada.
                </div>
              )}
            </div>
          </div>
        )}

        <div className="rounded-xl border border-amber-400/15 bg-black/25 p-3 text-xs text-amber-100/60">
          <p>
            Informe original:
            <span className="ml-1 text-amber-50" dangerouslySetInnerHTML={{ __html: report.content || report.body }} />
          </p>
        </div>
      </div>
    </div>
  );
};

export default ReportCard;
