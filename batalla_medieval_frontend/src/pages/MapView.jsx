import { useEffect, useMemo, useState } from 'react';
import MapGrid from '../components/MapGrid';
import CityPopup from '../components/CityPopup';
import axiosClient from '../api/axiosClient';

const DEFAULT_SIZE = 20;

const formatRelation = (city, currentPlayer) => {
  if (!city) return 'neutral';
  if (city.owner_id === currentPlayer?.id) return 'own';
  if (city.relation) return city.relation;
  return city.status || 'neutral';
};

const MapView = () => {
  const [center, setCenter] = useState({ x: Math.floor(DEFAULT_SIZE / 2), y: Math.floor(DEFAULT_SIZE / 2) });
  const [cities, setCities] = useState([]);
  const [selectedCoord, setSelectedCoord] = useState(null);
  const [popupCityId, setPopupCityId] = useState(null);
  const [filter, setFilter] = useState('all');
  const [jump, setJump] = useState('');
  const [message, setMessage] = useState('Selecciona una coordenada para ver detalles.');
  const [loadingMap, setLoadingMap] = useState(false);

  const loadCities = async () => {
    setLoadingMap(true);
    try {
      const response = await axiosClient.get('/city/map');
      const payload = response.data || [];
      const currentPlayer = payload.current_player;
      const cityList = Array.isArray(payload) ? payload : payload.cities || [];
      const enriched = cityList.map((city) => ({
        ...city,
        relation: formatRelation(city, currentPlayer),
        ownerTag: city.owner_name?.slice(0, 3)?.toUpperCase(),
      }));
      setCities(enriched);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'No se pudo cargar el mapa');
    } finally {
      setLoadingMap(false);
    }
  };

  useEffect(() => {
    loadCities();
  }, []);

  const handleCellSelect = async ({ x, y }) => {
    setSelectedCoord({ x, y });
    setMessage('Buscando ciudad...');
    try {
      const response = await axiosClient.get('/city/by-coordinates', { params: { x, y } });
      if (response.data?.id) {
        setPopupCityId(response.data.id);
        setMessage(`Ciudad encontrada en (${x}, ${y})`);
      } else {
        setPopupCityId(null);
        setMessage('No city here');
      }
    } catch (error) {
      setPopupCityId(null);
      setMessage(error.response?.data?.detail || 'No city here');
    }
  };

  const filteredCities = useMemo(() => {
    if (filter === 'all') return cities;
    if (filter === 'own') return cities.filter((city) => city.relation === 'own');
    if (filter === 'alliance') return cities.filter((city) => city.relation === 'alliance');
    return cities;
  }, [cities, filter]);

  const handleJump = () => {
    const [xStr, yStr] = jump.split(',').map((v) => v.trim());
    const x = Number(xStr);
    const y = Number(yStr);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      setCenter({ x, y });
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px,1fr] gap-6 h-[calc(100vh-120px)]">
      <div className="card p-4 space-y-4 h-full bg-gradient-to-b from-emerald-950/80 via-slate-950 to-amber-950/60 border border-amber-900/50">
        <div>
          <h1 className="text-3xl text-amber-100">Mapa del mundo</h1>
          <p className="text-amber-200/80">Explora las coordenadas y selecciona objetivos</p>
        </div>
        <div className="space-y-2">
          <label className="text-sm text-amber-200/80">Ir a coordenada</label>
          <div className="flex gap-2">
            <input
              className="input w-full"
              placeholder="x,y"
              value={jump}
              onChange={(e) => setJump(e.target.value)}
            />
            <button type="button" className="btn-primary" onClick={handleJump}>
              Ir
            </button>
          </div>
        </div>
        <div className="space-y-2">
          <label className="text-sm text-amber-200/80">Filtros</label>
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" checked={filter === 'all'} onChange={() => setFilter('all')} />
              <span>Todos</span>
            </label>
            <label className="flex items-center gap-2 text-sm text-blue-300">
              <input type="radio" checked={filter === 'own'} onChange={() => setFilter('own')} />
              <span>Mis ciudades</span>
            </label>
            <label className="flex items-center gap-2 text-sm text-green-300">
              <input type="radio" checked={filter === 'alliance'} onChange={() => setFilter('alliance')} />
              <span>Alianza</span>
            </label>
          </div>
        </div>
        <div className="space-y-1 text-sm text-amber-100/80">
          <p>Centro actual: {center.x}, {center.y}</p>
          <p>Selección: {selectedCoord ? `${selectedCoord.x}, ${selectedCoord.y}` : '---'}</p>
          <p className="text-yellow-200">{message}</p>
          {loadingMap && <p className="text-xs text-amber-200/80">Actualizando mapa...</p>}
        </div>
      </div>

      <div className="relative h-full">
        <MapGrid
          gridSize={DEFAULT_SIZE}
          center={center}
          onCenterChange={setCenter}
          cities={filteredCities}
          filter={filter}
          selected={selectedCoord}
          onCellClick={handleCellSelect}
        />
        {popupCityId && selectedCoord && (
          <CityPopup
            cityId={popupCityId}
            coordinate={selectedCoord}
            onClose={() => setPopupCityId(null)}
          />
        )}
      </div>
    </div>
  );
};

export default MapView;
