import { useEffect, useRef, useState } from 'react';
import axiosClient from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';
import { troopList, TROOP_TYPES } from '../utils/gameMath';

const relationText = {
  own: 'Tus dominios',
  alliance: 'Alianza',
  enemy: 'Enemigo',
  neutral: 'Neutral',
};

const CityPopup = ({ cityId, coordinate, onClose }) => {
  const [loading, setLoading] = useState(true);
  const [city, setCity] = useState(null);
  const [actionState, setActionState] = useState({ status: 'idle', message: '' });
  const [showTroopSelector, setShowTroopSelector] = useState(false);
  const [selectedTroops, setSelectedTroops] = useState({});
  const popupRef = useRef(null);
  const { currentCity } = useCityStore();

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (popupRef.current && !popupRef.current.contains(event.target)) {
        onClose?.();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  useEffect(() => {
    if (!cityId) return;
    setLoading(true);
    setSelectedTroops({});
    setShowTroopSelector(false);
    axiosClient
      .get(`/city/${cityId}`)
      .then((response) => {
        setCity(response.data);
      })
      .catch(() => {
        setCity(null);
      })
      .finally(() => setLoading(false));
  }, [cityId]);

  const handleTroopChange = (unit, value) => {
    setSelectedTroops(prev => ({
      ...prev,
      [unit]: parseInt(value) || 0
    }));
  };

  const sendAction = async (type) => {
    if (!cityId || !currentCity) return;
    
    if (type === 'attack' && !showTroopSelector) {
      setShowTroopSelector(true);
      return;
    }

    setActionState({ status: 'loading', message: '' });
    try {
      const payload = {
        origin_city_id: currentCity.id,
        target_city_id: cityId,
        movement_type: type,
        world_id: currentCity.world_id,
        troops: type === 'attack' ? selectedTroops : {},
        spy_count: type === 'spy' ? 1 : 0 // Default spy count for now
      };
      
      await axiosClient.post('/movements/', payload);
      setActionState({ status: 'success', message: `Orden enviada: ${type}` });
      setShowTroopSelector(false);
      setSelectedTroops({});
    } catch (error) {
      setActionState({ status: 'error', message: error.response?.data?.detail || 'No se pudo enviar la orden' });
    }
  };

  if (!cityId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div ref={popupRef} className="w-full max-w-md rounded-xl border border-amber-700/50 bg-gray-900 p-6 shadow-2xl">
        {loading ? (
          <div className="flex justify-center py-8">
            <span className="loading loading-spinner text-amber-500"></span>
          </div>
        ) : city ? (
          <div className="space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-2xl font-bold text-amber-100">{city.name}</h2>
                <p className="text-amber-200/60">
                  Jugador: <span className="text-amber-100">{city.owner?.username || 'Bárbaro'}</span>
                </p>
                <p className="text-sm text-gray-400">Coordenadas: ({city.x}, {city.y})</p>
              </div>
              <button onClick={onClose} className="btn btn-ghost btn-sm text-gray-400 hover:text-white">✕</button>
            </div>

            {showTroopSelector ? (
              <div className="space-y-3 bg-gray-800/50 p-3 rounded">
                <h3 className="text-sm font-bold text-amber-200">Seleccionar Tropas</h3>
                <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                  {troopList.map(unit => (
                    <div key={unit} className="flex items-center gap-2">
                      <label className="text-xs text-gray-300 w-20 truncate" title={TROOP_TYPES[unit]}>
                        {TROOP_TYPES[unit]}
                      </label>
                      <input 
                        type="number" 
                        className="input input-xs w-16 bg-gray-900 border-gray-700"
                        min="0"
                        placeholder="0"
                        onChange={(e) => handleTroopChange(unit, e.target.value)}
                      />
                    </div>
                  ))}
                </div>
                <div className="flex gap-2 pt-2">
                  <button 
                    className="btn btn-sm btn-error flex-1"
                    onClick={() => setShowTroopSelector(false)}
                  >
                    Cancelar
                  </button>
                  <button 
                    className="btn btn-sm btn-primary flex-1"
                    onClick={() => sendAction('attack')}
                  >
                    Confirmar Ataque
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 pt-2">
                <button 
                  className="btn bg-red-900/40 hover:bg-red-800/60 text-red-100 border-red-800/50"
                  onClick={() => sendAction('attack')}
                >
                  ⚔️ Atacar
                </button>
                <button 
                  className="btn bg-blue-900/40 hover:bg-blue-800/60 text-blue-100 border-blue-800/50"
                  onClick={() => sendAction('spy')}
                >
                  👁️ Espiar
                </button>
              </div>
            )}

            {actionState.message && (
              <div className={`alert ${actionState.status === 'error' ? 'alert-error' : 'alert-success'} py-2 text-sm`}>
                {actionState.message}
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-400">
            No se pudo cargar la información de la ciudad.
          </div>
        )}
      </div>
    </div>
  );
};

export default CityPopup;

