import PropTypes from 'prop-types';

const StatRow = ({ label, value }) => (
  <div className="flex justify-between py-1">
    <span className="text-gray-300">{label}</span>
    <span className="text-yellow-300 font-semibold">{value}</span>
  </div>
);

StatRow.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
};

const TroopList = ({ troops }) => (
  <div className="grid md:grid-cols-2 gap-2">
    {Object.entries(troops || {}).map(([name, count]) => (
      <div key={name} className="flex justify-between bg-gray-950/60 border border-gray-800 rounded px-3 py-2">
        <span className="text-gray-200 text-sm">{name}</span>
        <span className="text-yellow-200 font-semibold">{count}</span>
      </div>
    ))}
  </div>
);

TroopList.propTypes = {
  troops: PropTypes.object,
};

const SimulatorResult = ({ result }) => {
  if (!result) return null;

  return (
    <div className="card bg-gray-900/80 border border-yellow-800/30 p-4 space-y-4 mt-4">
      <h3 className="text-2xl font-semibold text-yellow-300">Resultado de la simulación</h3>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <h4 className="text-lg text-gray-100 mb-2">Tropas atacantes sobrevivientes</h4>
          <TroopList troops={result.attacker?.survivors} />
        </div>
        <div>
          <h4 className="text-lg text-gray-100 mb-2">Tropas defensoras sobrevivientes</h4>
          <TroopList troops={result.defender?.survivors} />
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-gray-950/60 border border-gray-800 rounded p-3">
          <h4 className="text-lg text-gray-100 mb-2">Recursos saqueados</h4>
          <StatRow label="Madera" value={result.loot?.wood ?? 0} />
          <StatRow label="Ladrillo" value={result.loot?.clay ?? 0} />
          <StatRow label="Hierro" value={result.loot?.iron ?? 0} />
        </div>
        <div className="bg-gray-950/60 border border-gray-800 rounded p-3">
          <h4 className="text-lg text-gray-100 mb-2">Daño estimado a edificios</h4>
          <StatRow label="Muralla" value={result.buildingDamage?.wall ?? '—'} />
          <StatRow label="Otros" value={result.buildingDamage?.other ?? '—'} />
        </div>
      </div>
    </div>
  );
};

SimulatorResult.propTypes = {
  result: PropTypes.shape({
    attacker: PropTypes.shape({ survivors: PropTypes.object }),
    defender: PropTypes.shape({ survivors: PropTypes.object }),
    loot: PropTypes.shape({ wood: PropTypes.number, clay: PropTypes.number, iron: PropTypes.number }),
    buildingDamage: PropTypes.object,
  }),
};

export default SimulatorResult;
