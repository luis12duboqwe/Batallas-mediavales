import { useEffect, useMemo, useState } from 'react';
import SimulatorTroopInput from '../components/SimulatorTroopInput';
import SimulatorResult from '../components/SimulatorResult';
import { SIMULATOR_TROOPS, fetchSimulationModifiers, simulateBattle } from '../services/simulator';

const createTroopMap = () =>
  SIMULATOR_TROOPS.reduce((acc, troop) => {
    acc[troop] = 0;
    return acc;
  }, {});

const BattleSimulator = () => {
  const [attackerTroops, setAttackerTroops] = useState(createTroopMap);
  const [defenderTroops, setDefenderTroops] = useState(createTroopMap);
  const [wallLevel, setWallLevel] = useState(0);
  const [loyalty, setLoyalty] = useState(100);
  const [morale, setMorale] = useState(100);
  const [luck, setLuck] = useState(0);
  const [speedOptions, setSpeedOptions] = useState([1, 1.5, 2, 3]);
  const [speedModifier, setSpeedModifier] = useState(1);
  const [eventModifiers, setEventModifiers] = useState([{ id: 'none', name: 'Sin evento', description: '' }]);
  const [selectedEvent, setSelectedEvent] = useState('none');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    fetchSimulationModifiers()
      .then(({ data }) => {
        if (Array.isArray(data?.events)) {
          setEventModifiers([{ id: 'none', name: 'Sin evento', description: '' }, ...data.events]);
        }
        if (Array.isArray(data?.speedModifiers) && data.speedModifiers.length > 0) {
          const normalized = data.speedModifiers
            .map((entry) =>
              typeof entry === 'number'
                ? entry
                : entry?.value ?? entry?.multiplier ?? null
            )
            .filter((value) => value !== null);
          if (normalized.length > 0) {
            setSpeedOptions(normalized);
            setSpeedModifier(normalized[0]);
          }
        }
      })
      .catch(() => {
        setEventModifiers([{ id: 'none', name: 'Sin evento', description: '' }]);
      });
  }, []);

  const totalAttackers = useMemo(
    () => Object.values(attackerTroops).reduce((sum, value) => sum + (Number(value) || 0), 0),
    [attackerTroops]
  );

  const totalDefenders = useMemo(
    () => Object.values(defenderTroops).reduce((sum, value) => sum + (Number(value) || 0), 0),
    [defenderTroops]
  );

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const payload = {
        attacker: {
          troops: attackerTroops,
          morale,
          luck,
        },
        defender: {
          troops: defenderTroops,
          wallLevel,
          loyalty,
        },
        modifiers: {
          speed: speedModifier,
          event: selectedEvent,
        },
      };
      const { data } = await simulateBattle(payload);
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo simular la batalla');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-yellow-300">Simulador de Batallas</h1>
          <p className="text-gray-400">Prueba combinaciones y resultados antes de arriesgar tus tropas.</p>
        </div>
        <div className="text-right text-sm text-gray-400">
          <p>Total atacante: <span className="text-yellow-300 font-semibold">{totalAttackers}</span></p>
          <p>Total defensor: <span className="text-yellow-300 font-semibold">{totalDefenders}</span></p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid lg:grid-cols-2 gap-4">
          <SimulatorTroopInput
            title="Tropas atacantes"
            description="Incluye unidades ofensivas y de asedio"
            troops={attackerTroops}
            onChange={setAttackerTroops}
          />
          <SimulatorTroopInput
            title="Tropas defensoras"
            description="Incluye defensores y tropas en apoyo"
            troops={defenderTroops}
            onChange={setDefenderTroops}
          />
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="card bg-gray-900/70 border border-yellow-800/30 p-4 space-y-3">
            <h3 className="text-xl text-yellow-300 font-semibold">Defensas de ciudad</h3>
            <label className="flex items-center justify-between">
              <span className="text-gray-200">Nivel de muralla</span>
              <input
                type="number"
                min="0"
                value={wallLevel}
                onChange={(e) => setWallLevel(Math.max(0, Number(e.target.value) || 0))}
                className="w-24 bg-gray-800 text-right text-gray-100 border border-gray-700 rounded px-2 py-1"
              />
            </label>
            <label className="flex items-center justify-between">
              <span className="text-gray-200">Lealtad de la ciudad</span>
              <input
                type="number"
                min="0"
                max="100"
                value={loyalty}
                onChange={(e) => setLoyalty(Math.min(100, Math.max(0, Number(e.target.value) || 0)))}
                className="w-24 bg-gray-800 text-right text-gray-100 border border-gray-700 rounded px-2 py-1"
              />
            </label>
          </div>

          <div className="card bg-gray-900/70 border border-yellow-800/30 p-4 space-y-3">
            <h3 className="text-xl text-yellow-300 font-semibold">Factores globales</h3>
            <label className="flex items-center justify-between">
              <span className="text-gray-200">Modificador de velocidad</span>
              <select
                value={speedModifier}
                onChange={(e) => setSpeedModifier(Number(e.target.value))}
                className="bg-gray-800 text-gray-100 border border-gray-700 rounded px-2 py-1"
              >
                {speedOptions.map((speed) => (
                  <option key={speed} value={speed}>
                    x{speed}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-2">
              <span className="text-gray-200">Eventos activos</span>
              <select
                value={selectedEvent}
                onChange={(e) => setSelectedEvent(e.target.value)}
                className="bg-gray-800 text-gray-100 border border-gray-700 rounded px-2 py-1"
              >
                {eventModifiers.length === 0 && <option value="none">Sin evento</option>}
                {eventModifiers.map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.name}
                  </option>
                ))}
              </select>
              {selectedEvent !== 'none' && (
                <p className="text-sm text-gray-400">
                  {eventModifiers.find((event) => event.id === selectedEvent)?.description || 'Evento de combate activo'}
                </p>
              )}
            </label>
          </div>

          <div className="card bg-gray-900/70 border border-yellow-800/30 p-4 space-y-3">
            <h3 className="text-xl text-yellow-300 font-semibold">Mecánicas de combate</h3>
            <label className="flex flex-col gap-1">
              <div className="flex justify-between text-sm text-gray-300">
                <span>Moral (defensor)</span>
                <span className="text-yellow-300 font-semibold">{morale}%</span>
              </div>
              <input
                type="range"
                min="50"
                max="150"
                value={morale}
                onChange={(e) => setMorale(Number(e.target.value))}
                className="w-full"
              />
            </label>
            <label className="flex flex-col gap-1">
              <div className="flex justify-between text-sm text-gray-300">
                <span>Suerte</span>
                <span className="text-yellow-300 font-semibold">{luck}%</span>
              </div>
              <input
                type="range"
                min="-25"
                max="25"
                value={luck}
                onChange={(e) => setLuck(Number(e.target.value))}
                className="w-full"
              />
            </label>
          </div>
        </div>

        {error && <p className="text-red-400 bg-red-900/30 border border-red-700 rounded p-3">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full md:w-auto px-6 py-3 rounded bg-yellow-600 hover:bg-yellow-500 transition text-black font-semibold shadow-lg disabled:opacity-70"
        >
          {loading ? 'Calculando...' : 'Calcular batalla'}
        </button>
      </form>

      <SimulatorResult result={result} />
    </div>
  );
};

export default BattleSimulator;
