import { useEffect, useState } from 'react';
import { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';

const EQUIPMENT_SLOTS = ['head', 'body', 'feet', 'weapon', 'horse', 'artifact'];

const HeroView = () => {
  const { currentCity, loadCity } = useCityStore();
  const worldId = currentCity?.world_id;
  const [hero, setHero] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [points, setPoints] = useState({ attack: 0, defense: 0, production: 0 });

  const fetchData = async () => {
    if (!worldId) return;
    setLoading(true);
    setError('');
    try {
      const [heroRes, itemsRes] = await Promise.all([
        api.getHero(worldId),
        api.getHeroItems(worldId),
      ]);
      setHero(heroRes.data);
      setItems(itemsRes.data || []);
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || 'No se pudo cargar el héroe.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [worldId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDistribute = async () => {
    try {
      const res = await api.distributeHeroPoints(worldId, points);
      setHero(res.data);
      setPoints({ attack: 0, defense: 0, production: 0 });
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudieron distribuir los puntos.');
    }
  };

  const handleRevive = async () => {
    try {
      const res = await api.reviveHero(worldId);
      setHero(res.data);
      await loadCity();
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo revivir el héroe.');
    }
  };

  const handleEquip = async (itemId) => {
    try {
      const res = await api.equipHeroItem(itemId, worldId);
      setItems(res.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo equipar el objeto.');
    }
  };

  const handleUnequip = async (itemId) => {
    try {
      const res = await api.unequipHeroItem(itemId, worldId);
      setItems(res.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo desequipar el objeto.');
    }
  };

  const incrementPoint = (type) => {
    const currentTotal = points.attack + points.defense + points.production;
    if (currentTotal < hero.available_points) {
      setPoints((prev) => ({ ...prev, [type]: prev[type] + 1 }));
    }
  };

  const decrementPoint = (type) => {
    if (points[type] > 0) {
      setPoints((prev) => ({ ...prev, [type]: prev[type] - 1 }));
    }
  };

  const templateFor = (item) => item.template || item;
  const equippedItems = items.filter((item) => item.is_equipped);
  const inventoryItems = items.filter((item) => !item.is_equipped);
  const getEquippedInSlot = (slot) => equippedItems.find((item) => templateFor(item).slot === slot);

  const renderItemCard = (item, actionLabel, onAction) => {
    const template = templateFor(item);
    return (
      <div key={item.id} className="bg-gray-700 p-3 rounded border border-gray-600 flex flex-col justify-between" data-testid={`hero-item-${item.id}`}>
        <div>
          <div className="font-bold text-yellow-400">{template.name}</div>
          <div className="text-xs text-gray-300 capitalize">{template.slot}</div>
          <div className="text-sm text-green-400 mt-1">
            +{Math.round(Number(template.bonus_value || 0) * 100)}% {String(template.bonus_type || '').replaceAll('_', ' ')}
          </div>
        </div>
        <button type="button" onClick={() => onAction(item.id)} className="mt-2 bg-blue-600 hover:bg-blue-500 text-xs py-1 px-2 rounded">
          {actionLabel}
        </button>
      </div>
    );
  };

  if (!worldId) return <div className="p-4 text-white">Cargando mundo...</div>;
  if (loading) return <div className="p-4 text-white">Cargando héroe...</div>;
  if (!hero) return <div className="p-4 text-red-500">{error || 'Héroe no disponible'}</div>;

  const pendingPoints = points.attack + points.defense + points.production;
  const xpPercent = hero.next_level_xp > 0 ? Math.min(100, (hero.xp / hero.next_level_xp) * 100) : 100;

  return (
    <div className="p-4 max-w-6xl mx-auto text-white" data-testid="hero-view">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 mb-6">
        <h1 className="text-3xl font-bold text-yellow-500">Héroe: {hero.name}</h1>
        <span className="text-xs text-gray-400" data-testid="hero-rules-version">Reglas {hero.rules_version}</span>
      </div>
      {error && <div role="alert" className="alert alert-error mb-4">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="space-y-8">
          <div className="bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xl font-semibold">Nivel {hero.level}</span>
              <span className={`px-3 py-1 rounded-full text-sm ${hero.status === 'dead' ? 'bg-red-600' : 'bg-green-600'}`} data-testid="hero-status">
                {hero.status.toUpperCase()}
              </span>
            </div>
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1"><span>XP</span><span>{hero.xp} / {hero.next_level_xp || 'MAX'}</span></div>
              <div className="w-full bg-gray-700 rounded-full h-2.5"><div className="bg-blue-600 h-2.5 rounded-full" style={{ width: `${xpPercent}%` }} /></div>
            </div>
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1"><span>Salud</span><span>{Math.round(hero.health)}%</span></div>
              <div className="w-full bg-gray-700 rounded-full h-2.5"><div className="bg-red-600 h-2.5 rounded-full" style={{ width: `${Math.max(0, Math.min(100, hero.health))}%` }} /></div>
            </div>
            {hero.status === 'dead' && (
              <button type="button" onClick={handleRevive} className="w-full mt-4 bg-yellow-600 hover:bg-yellow-700 text-white font-bold py-2 px-4 rounded transition" data-testid="hero-revive">
                Revivir por 250 oro
              </button>
            )}
          </div>

          <div className="bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-700">
            <h2 className="text-xl font-semibold mb-4 text-yellow-400">Atributos</h2>
            <div className="mb-4 text-sm text-gray-400">Puntos disponibles: <span className="text-white font-bold">{hero.available_points - pendingPoints}</span></div>
            <div className="space-y-4">
              {['attack', 'defense', 'production'].map((attr) => (
                <div key={attr} className="flex items-center justify-between">
                  <span className="capitalize w-24">{attr}</span>
                  <span className="font-mono text-lg w-8 text-center">{hero[`${attr}_points`] + points[attr]}</span>
                  <div className="flex gap-2">
                    <button type="button" onClick={() => decrementPoint(attr)} disabled={points[attr] === 0} className="w-8 h-8 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50">-</button>
                    <button type="button" onClick={() => incrementPoint(attr)} disabled={hero.available_points - pendingPoints <= 0} className="w-8 h-8 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50">+</button>
                  </div>
                </div>
              ))}
            </div>
            {pendingPoints > 0 && <button type="button" onClick={handleDistribute} className="w-full mt-6 bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition">Guardar cambios</button>}
          </div>
        </div>

        <div className="bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-700">
          <h2 className="text-xl font-semibold mb-6 text-yellow-400 text-center">Equipo</h2>
          <div className="flex flex-col items-center gap-4">
            {EQUIPMENT_SLOTS.map((slot) => {
              const item = getEquippedInSlot(slot);
              const template = item ? templateFor(item) : null;
              return (
                <div key={slot} className="w-full max-w-xs" data-testid={`hero-slot-${slot}`}>
                  <div className="text-xs text-gray-400 mb-1 capitalize text-center">{slot}</div>
                  {item ? (
                    <div className="bg-gray-700 p-3 rounded border border-yellow-600 relative group">
                      <div className="font-bold text-yellow-400 text-center">{template.name}</div>
                      <div className="text-sm text-green-400 text-center">+{Math.round(Number(template.bonus_value || 0) * 100)}% {String(template.bonus_type || '').replaceAll('_', ' ')}</div>
                      <button type="button" onClick={() => handleUnequip(item.id)} className="absolute top-0 right-0 bg-red-600 text-white text-xs p-1 rounded">X</button>
                    </div>
                  ) : <div className="bg-gray-900 p-4 rounded border border-gray-700 border-dashed text-center text-gray-600 h-16 flex items-center justify-center">Vacío</div>}
                </div>
              );
            })}
          </div>
        </div>

        <div className="bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-700">
          <h2 className="text-xl font-semibold mb-4 text-yellow-400">Inventario</h2>
          {inventoryItems.length === 0
            ? <div className="text-gray-500 text-center italic">No hay objetos en el inventario</div>
            : <div className="grid grid-cols-2 gap-3">{inventoryItems.map((item) => renderItemCard(item, 'Equipar', handleEquip))}</div>}
        </div>
      </div>
    </div>
  );
};

export default HeroView;
