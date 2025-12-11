import { useEffect, useRef, useState } from 'react';
import axiosClient from '../api/axiosClient';

const relationText = {
  own: 'Tus dominios',
  alliance: 'Alianza',
  enemy: 'Enemigo',
  neutral: 'Neutral',
};

const CityPopup = ({ cityId, coordinate, originCityId, onClose }) => {
  const [loading, setLoading] = useState(true);
  const [city, setCity] = useState(null);
  const [actionState, setActionState] = useState({ status: 'idle', message: '' });
  const popupRef = useRef(null);

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
    axiosClient
      .get(`/cities/${cityId}`)
      .then((response) => {
        setCity(response.data);
      })
      .catch(() => {
        setCity(null);
      })
      .finally(() => setLoading(false));
  }, [cityId]);

  const sendAction = async (type) => {
    if (!cityId || !originCityId) {
      setActionState({ status: 'error', message: 'Selecciona una ciudad válida de origen y destino' });
      return;
    }
    setActionState({ status: 'loading', message: '' });
    try {
      await axiosClient.post('/movements', {
        origin_city_id: originCityId,
        target_city_id: cityId,
        movement_type: type,
      });
      setActionState({ status: 'success', message: `Orden enviada: ${type}` });
    } catch (error) {
      setActionState({ status: 'error', message: error.response?.data?.detail || 'No se pudo enviar la orden' });
    }
  };

  return (
    <div className="absolute inset-0 flex items-start justify-center md:items-center z-40">
      <div className="fixed inset-0 bg-black/50" />
      <div
        ref={popupRef}
        className="relative w-full max-w-md bg-gray-900 border border-yellow-800/60 rounded-xl shadow-2xl p-6 m-4"
      >
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-gray-400">Coordenada {coordinate?.x},{coordinate?.y}</p>
            <h2 className="text-2xl text-gold">{city?.name || 'Ciudad desconocida'}</h2>
            <p className="text-sm text-gray-400">
              Propietario: <span className="text-yellow-200">{city?.owner_name || '---'}</span>
            </p>
            <p className="text-xs text-gray-500">{relationText[city?.relation] || 'Sin relación'}</p>
          </div>
          <button
            type="button"
            aria-label="Cerrar"
            className="text-gray-400 hover:text-yellow-300"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        {loading ? (
          <p className="text-gray-400 mt-4">Cargando información...</p>
        ) : (
          <div className="mt-4 space-y-2 text-sm text-gray-300">
            <p>Habitantes: {city?.population ?? 'N/D'}</p>
            <p>Producción: {city?.production ?? 'N/D'}</p>
            <p>Defensas: {city?.defense ?? 'N/D'}</p>
          </div>
        )}

        <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => sendAction('attack')}
            className="btn-primary text-center"
            disabled={actionState.status === 'loading'}
          >
            Atacar
          </button>
          <button
            type="button"
            onClick={() => sendAction('spy')}
            className="btn-primary bg-gray-800 text-yellow-300"
            disabled={actionState.status === 'loading'}
          >
            Espiar
          </button>
          <button
            type="button"
            onClick={() => sendAction('reinforce')}
            className="btn-primary bg-gray-800 text-yellow-300"
            disabled={actionState.status === 'loading'}
          >
            Reforzar
          </button>
        </div>

        {actionState.message && (
          <p
            className={`mt-3 text-sm ${
              actionState.status === 'success'
                ? 'text-green-400'
                : actionState.status === 'error'
                  ? 'text-red-400'
                  : 'text-gray-300'
            }`}
          >
            {actionState.message}
          </p>
        )}
      </div>
    </div>
  );
};

export default CityPopup;
