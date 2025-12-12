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
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!currentCity) loadCity();
    
    const fetchTarget = async () => {
      try {
        if (currentCity) {
            if (isOasis) {
                const res = await api.getOasis(targetCityId);
                setTargetCity({
                    name: `Oasis ${res.data.resource_type} (+${res.data.bonus_percent}%)`,
                    x: res.data.x,
                    y: res.data.y,
                    isOasis: true
                });
            } else {
                const res = await api.getCityStatus({ cityId: targetCityId, worldId: currentCity.world_id });
                setTargetCity(res.data);
            }
        }
      } catch (e) {
        console.error("Error fetching target", e);
      }
    };
    fetchTarget();
  }, [targetCityId, currentCity, loadCity, isOasis]);

  const handleTroopChange = (unit, value) => {
    setTroops(prev => ({
      ...prev,
      [unit]: parseInt(value) || 0
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const troopsToSend = Object.entries(troops).reduce((acc, [unit, count]) => {
        if (count > 0) acc[unit] = count;
        return acc;
      }, {});

      if (Object.keys(troopsToSend).length === 0 && movementType !== 'spy') {
        alert("Debes enviar al menos una tropa.");
        setLoading(false);
        return;
      }

      const payload = {
        movementType,
        troops: troopsToSend,
        targetBuilding: targetBuilding || null
      };

      if (isOasis) {
          payload.targetOasisId = parseInt(targetCityId);
      } else {
          payload.targetCityId = parseInt(targetCityId);
      }

      await sendMovement(payload);
      
      alert("Movimiento enviado!");
      navigate('/movements');
    } catch (error) {
      console.error(error);
      alert("Error al enviar movimiento");
    } finally {
      setLoading(false);
    }
  };

  const availableTroops = currentCity?.troops || [];
  const getAvailable = (unit) => {
    const t = availableTroops.find(t => t.unit_type === unit);
    return t ? t.quantity : 0;
  };

  const buildingOptions = [
    { value: '', label: 'Sin objetivo específico' },
    { value: 'headquarters', label: 'Edificio Principal' },
    { value: 'barracks', label: 'Cuartel' },
    { value: 'stable', label: 'Establo' },
    { value: 'workshop', label: 'Taller' },
    { value: 'academy', label: 'Academia' },
    { value: 'market', label: 'Mercado' },
    { value: 'farm', label: 'Granja' },
    { value: 'warehouse', label: 'Almacén' },
    { value: 'wall', label: 'Muralla' },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-6 text-amber-500">Enviar Tropas</h1>
      
      {targetCity && (
        <div className="mb-6 p-4 bg-gray-800 rounded border border-gray-700">
          <h2 className="text-xl font-bold text-white">Objetivo: {targetCity.name}</h2>
          <p className="text-gray-400">Coordenadas: ({targetCity.x}, {targetCity.y})</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Troop Selection */}
          <div className="bg-gray-900 p-4 rounded">
            <h3 className="text-lg font-bold mb-4 text-gray-300">Seleccionar Tropas</h3>
            <div className="space-y-3">
              {Object.entries(TROOP_TYPES).map(([unit, label]) => {
                const max = getAvailable(unit);
                if (max === 0) return null;
                
                return (
                  <div key={unit} className="flex items-center justify-between">
                    <label className="text-sm text-gray-400 w-1/3">{label}</label>
                    <div className="flex items-center gap-2 w-2/3">
                      <input 
                        type="number" 
                        min="0" 
                        max={max}
                        className="input input-sm bg-gray-800 w-full"
                        value={troops[unit] || ''}
                        onChange={(e) => handleTroopChange(unit, e.target.value)}
                        placeholder={`Max: ${max}`}
                      />
                      <button 
                        type="button"
                        className="btn btn-xs btn-ghost text-blue-400"
                        onClick={() => handleTroopChange(unit, max)}
                      >
                        Max
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Mission Settings */}
          <div className="space-y-6">
            <div className="bg-gray-900 p-4 rounded">
              <h3 className="text-lg font-bold mb-4 text-gray-300">Tipo de Misión</h3>
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
                <label className="label cursor-pointer justify-start gap-4">
                  <input 
                    type="radio" 
                    name="type" 
                    className="radio radio-info" 
                    checked={movementType === 'support'} 
                    onChange={() => setMovementType('support')} 
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
              </div>
            </div>

            {movementType === 'attack' && (
              <div className="bg-gray-900 p-4 rounded">
                <h3 className="text-lg font-bold mb-4 text-gray-300">Objetivo de Catapultas</h3>
                <select 
                  className="select select-bordered w-full bg-gray-800"
                  value={targetBuilding}
                  onChange={(e) => setTargetBuilding(e.target.value)}
                  disabled={!troops['catapult']}
                >
                  {buildingOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
                {!troops['catapult'] && (
                  <p className="text-xs text-gray-500 mt-2">Necesitas catapultas para seleccionar un objetivo.</p>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-4">
          <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)}>Cancelar</button>
          <button type="submit" className="btn btn-primary px-8" disabled={loading}>
            {loading ? 'Enviando...' : 'Enviar Tropas'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default SendMovementView;
