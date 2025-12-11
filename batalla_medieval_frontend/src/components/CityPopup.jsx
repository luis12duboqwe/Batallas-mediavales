import { useEffect, useRef, useState } from 'react';
import axiosClient from '../api/axiosClient';

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
      .get(`/city/${cityId}`)
      .then((response) => {
        setCity(response.data);
      })
      .catch(() => {
        setCity(null);
      })
      .finally(() => setLoading(false));
  }, [cityId]);

  const sendAction = async (type) => {
    if (!cityId) return;
    setActionState({ status: 'loading', message: '' });
    try {
      await axiosClient.post('/movement/send', { city_id: cityId, type });
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
        className="relative w-full max-w-md bg-gradient-to-br from-emerald-950 via-slate-950 to-amber-950 border border-amber-900/70 rounded-2xl shadow-2xl p-6 m-4"
      >
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-amber-200/80">Coordenadas ({coordinate?.x}, {coordinate?.y})</p>
            <h2 className="text-3xl font-semibold text-amber-100">{city?.name || 'Ciudad desconocida'}</h2>
            <p className="text-sm text-amber-100/80">
              Propietario: <span className="text-amber-200 font-semibold">{city?.owner_name || '---'}</span>
            </p>
            <p className="text-xs text-amber-300/70">{relationText[city?.relation] || 'Sin relación'}</p>
          </div>
          <button
            type="button"
            aria-label="Cerrar"
            className="text-amber-200/70 hover:text-amber-100"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        {loading ? (
          <p className="text-amber-100/70 mt-4">Cargando información...</p>
        ) : (
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-amber-100/80">
            <div className="rounded-lg border border-amber-900/60 bg-black/20 p-3">
              <p className="text-xs uppercase tracking-wide text-amber-300/70">Habitantes</p>
              <p className="text-lg font-semibold">{city?.population ?? 'N/D'}</p>
            </div>
            <div className="rounded-lg border border-amber-900/60 bg-black/20 p-3">
              <p className="text-xs uppercase tracking-wide text-amber-300/70">Producción</p>
              <p className="text-lg font-semibold">{city?.production ?? 'N/D'}</p>
            </div>
            <div className="rounded-lg border border-amber-900/60 bg-black/20 p-3 col-span-2">
              <p className="text-xs uppercase tracking-wide text-amber-300/70">Defensas</p>
              <p className="text-lg font-semibold">{city?.defense ?? 'N/D'}</p>
            </div>
          </div>
        )}

        <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => sendAction('attack')}
            className="btn-primary text-center bg-gradient-to-r from-red-600 to-amber-600 border-none shadow-[0_10px_25px_-12px_rgba(248,113,113,0.65)]"
            disabled={actionState.status === 'loading'}
          >
            Atacar
          </button>
          <button
            type="button"
            onClick={() => sendAction('spy')}
            className="btn-primary bg-gradient-to-r from-slate-800 to-emerald-800 text-amber-100 border-none"
            disabled={actionState.status === 'loading'}
          >
            Espiar
          </button>
          <button
            type="button"
            onClick={() => sendAction('reinforce')}
            className="btn-primary bg-gradient-to-r from-blue-700 to-emerald-700 text-amber-50 border-none"
            disabled={actionState.status === 'loading'}
          >
            Reforzar
          </button>
        </div>

        {actionState.message && (
          <p
            className={`mt-3 text-sm ${
              actionState.status === 'success'
                ? 'text-green-300'
                : actionState.status === 'error'
                  ? 'text-red-300'
                  : 'text-amber-100/80'
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
