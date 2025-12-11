import PropTypes from 'prop-types';
import { SIMULATOR_TROOPS } from '../services/simulator';

const SimulatorTroopInput = ({ title, troops, onChange, description }) => {
  const handleChange = (name, value) => {
    const safeValue = Math.max(0, Number(value) || 0);
    onChange({ ...troops, [name]: safeValue });
  };

  return (
    <div className="card bg-gray-900/70 border border-yellow-800/30 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-semibold text-yellow-300">{title}</h3>
          {description && <p className="text-gray-400 text-sm">{description}</p>}
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        {SIMULATOR_TROOPS.map((troop) => (
          <label key={troop} className="flex items-center justify-between bg-gray-950/60 border border-gray-800 rounded px-3 py-2">
            <span className="text-gray-200 text-sm">{troop}</span>
            <input
              type="number"
              min="0"
              value={troops[troop] ?? 0}
              onChange={(e) => handleChange(troop, e.target.value)}
              className="w-28 bg-gray-800 text-right text-gray-100 border border-gray-700 rounded px-2 py-1 focus:outline-none focus:border-yellow-500"
            />
          </label>
        ))}
      </div>
    </div>
  );
};

SimulatorTroopInput.propTypes = {
  title: PropTypes.string.isRequired,
  description: PropTypes.string,
  troops: PropTypes.object.isRequired,
  onChange: PropTypes.func.isRequired,
};

export default SimulatorTroopInput;
