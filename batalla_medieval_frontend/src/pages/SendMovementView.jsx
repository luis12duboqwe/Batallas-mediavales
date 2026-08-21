import { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useCityStore } from '../store/cityStore';
import { TROOP_TYPES } from '../utils/gameMath';
import { api } from '../api/axiosClient';

const SendMovementView = () => {
  const { targetCityId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const isOasis = queryParams.get('type') === 'oasis';

  const { currentCity, sendMovement, loadCity } = useCityStore();

  const [targetCity, setTargetCity] = useState(null);
  const [troops, setTroops] = useState({});
  const [movementType, setMovementType] = useState('attack');
  const [targetBuilding, setTargetBuilding] = useState('');
  const [buildingOptions, setBuildingOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState('');
  const [formStatus, setFormStatus] = useState('');

  useEffect(() => {
    if (!currentCity) loadCity();
  }, [currentCity, loadCity]);

  useEffect(() => {
    if (isOasis && movementType !== 'attack') {
      setMovementType('attack');
    }
  }, [isOasis, movementType]);

  useEffect(() => {
    let active = true;
    api.getBalance()
      .then((snapshot) => {
        if (!active) return;
        const catalog = snapshot?.buildings?.catalog ?? {};
        setBuildingOptions(
          Object.entries(catalog).map(([value, definition]) => ({
            value,
            label: definition?.display_name || value,
          }))
        );
      })
      .catch(() => {
        if (active) setBuildingOptions([]);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const fetchTarget = async () => {
      if (!currentCity) return;
      try {
        if (isOasis) {
          const res = await api.getOasis(targetCityId);
          if (active) {
            setTargetCity({
              name: `Oasis ${res.data.resource_type} (+${res.data.bonus_percent}%)`,
              x: res.data.x,
              y: res.data.y,
              isOasis: true,
            });
          }
        } else {
          const res = await api.getCityStatus({
            cityId: targetCityId,
            worldId: currentCity.world_id,
          });
          if (active) setTargetCity(res.data);
        }
      } catch {
        if (active) setFormError('No se pudo cargar el objetivo seleccionado.');
      }
    };
    fetchTarget();
    return () => {
      active = false;
    };
  }, [targetCityId, currentCity, isOasis]);

  const handleTroopChange = (unit, value) => {
    setTroops(prev => ({
      ...prev,
      [unit]: Math.max(parseInt(value, 10) || 0, 0),
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setFormError('');
    setFormStatus('');

    try {
      const troopsToSend = Object.entries(troops).reduce((acc, [unit, count]) => {
        if (count > 0) acc[unit] = count;
        return acc;
      }, {});

      const spyCount = movementType === 'spy' ? Number(troopsToSend.spy || 0) : 0;
      if (movementType === 'spy' && spyCount <= 0) {
        setFormError('Debes seleccionar al menos un espía.');
        return;
      }

      if (movementType !== 'spy' && Object.keys(troopsToSend).length === 0) {
        setFormError('Debes enviar al menos una tropa.');
        return;
      }

      const payload = {
        movementType,
        troops: movementType === 'spy' ? {} : troopsToSend,
        spyCount,
        targetBuilding: movementType === 'attack' ? (targetBuilding || null) : null,
      };

      if (isOasis) {
        payload.targetOasisId = parseInt(targetCityId, 10);
      } else {
        payload.targetCityId = parseInt(targetCityId, 10);
      }

      await sendMovement(payload);
      setFormStatus('Movimiento enviado.');
      navigate('/movements');
    } catch (error) {
      setFormError(error.response?.data?.detail || 'Error al enviar movimiento.');
    } finally {
      setLoading(false);
    }
  };

  const availableTroops = currentCity?.troops || [];
  const getAvailable = (unit) => {
    const troop = availableTroops.find(item => item.unit_type === unit);
    return troop ? troop.quantity : 0;
  };

  const visibleTroopEntries = Object.entries(TROOP_TYPES).filter(([unit]) => {
    if (movementType === 'spy') return unit === 'spy';
    return unit !== 'spy';
  });

  return (
    <div className="p-3 sm:p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl sm:text-3xl font-bold mb-6 text-amber-500">Enviar Tropas</h1>

      {targetCity && (
        <div className="mb-6 p-4 bg-gray-800 rounded border border-gray-700">
          <h2 className="text-xl font-bold text-white break-words">Objetivo: {targetCity.name}</h2>
          <p className="text-gray-400">Coordenadas: ({targetCity.x}, {targetCity.y})</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <fieldset className="bg-gray-900 p-4 rounded">
            <legend className="text-lg font-bold mb-4 text-gray-300 px-1">Seleccionar Tropas</legend>
            <div className="space-y-3">
              {visibleTroopEntries.map(([unit, label]) => {
                const max = getAvailable(unit);
                if (max === 0) return null;
                const inputId = `movement-troop-${unit}`;

                return (
                  <div key={unit} className="grid grid-cols-[minmax(0,1fr)_minmax(8rem,1.4fr)] items-center gap-2">
                    <label htmlFor={inputId} className="text-sm text-gray-300 break-words">{label}</label>
                    <div className="flex items-center gap-2 min-w-0">
                      <input
                        id={inputId}
                        type="number"
                        min="0"
                        max={max}
                        inputMode="numeric"
                        className="input input-sm bg-gray-800 min-w-0 w-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                        value={troops[unit] || ''}
                        onChange={(event) => handleTroopChange(unit, event.target.value)}
                        placeholder={`Máx: ${max}`}
                      />
                      <button
                        type="button"
                        className="btn btn-xs btn-ghost text-blue-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                        onClick={() => handleTroopChange(unit, max)}
                        aria-label={`Seleccionar máximo de ${label}: ${max}`}
                      >
                        Máx
                      </button>
                    </div>
                  </div>
                );
              })}
              {visibleTroopEntries.every(([unit]) => getAvailable(unit) === 0) && (
                <p className="text-sm text-gray-400" role="status">
                  {movementType === 'spy'
                    ? 'No tienes espías disponibles en esta ciudad.'
                    : 'No tienes tropas disponibles para esta misión.'}
                </p>
              )}
            </div>
          </fieldset>

          <div className="space-y-6">
            <fieldset className="bg-gray-900 p-4 rounded">
              <legend className="text-lg font-bold mb-4 text-gray-300 px-1">Tipo de Misión</legend>
              <div className="flex flex-col gap-2">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="radio"
                    name="type"
                    className="radio radio-error"
                    checked={movementType === 'attack'}
                    onChange={() => setMovementType('attack')}
                  />
                  <span className="label-text text-white">Ataque</span>
                </label>
                {!isOasis && (
                  <>
                    <label className="label cursor-pointer justify-start gap-4">
                      <input
                        type="radio"
                        name="type"
                        className="radio radio-info"
                        checked={movementType === 'reinforce'}
                        onChange={() => setMovementType('reinforce')}
                      />
                      <span className="label-text text-white">Refuerzo</span>
                    </label>
                    <label className="label cursor-pointer justify-start gap-4">
                      <input
                        type="radio"
                        name="type"
                        className="radio radio-warning"
                        checked={movementType === 'spy'}
                        onChange={() => setMovementType('spy')}
                      />
                      <span className="label-text text-white">Espionaje</span>
                    </label>
                  </>
                )}
              </div>
            </fieldset>

            {movementType === 'attack' && (
              <div className="bg-gray-900 p-4 rounded">
                <label htmlFor="movement-target-building" className="block text-lg font-bold mb-4 text-gray-300">
                  Objetivo de Catapultas
                </label>
                <select
                  id="movement-target-building"
                  className="select select-bordered w-full bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                  value={targetBuilding}
                  onChange={(event) => setTargetBuilding(event.target.value)}
                  disabled={!troops.catapult}
                >
                  <option value="">Sin objetivo específico</option>
                  {buildingOptions.map(option => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                {!troops.catapult && (
                  <p className="text-xs text-gray-400 mt-2">Necesitas catapultas para seleccionar un objetivo.</p>
                )}
              </div>
            )}
          </div>
        </div>

        {formError && (
          <p role="alert" className="rounded border border-red-700 bg-red-950/50 p-3 text-sm text-red-200">
            {formError}
          </p>
        )}
        {formStatus && (
          <p role="status" className="rounded border border-green-700 bg-green-950/50 p-3 text-sm text-green-200">
            {formStatus}
          </p>
        )}

        <div className="flex flex-col-reverse sm:flex-row justify-end gap-3 sm:gap-4">
          <button
            type="button"
            className="btn btn-ghost focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
            onClick={() => navigate(-1)}
          >
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn-primary px-8 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-200"
            disabled={loading || !targetCity}
          >
            {loading ? 'Enviando...' : 'Enviar Tropas'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default SendMovementView;
