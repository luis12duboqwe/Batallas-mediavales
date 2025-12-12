import { useState, useEffect } from 'react';
import axiosClient, { api } from '../api/axiosClient';
import { useTranslation } from 'react-i18next';

const HeroView = () => {
  const { t } = useTranslation();
  const [hero, setHero] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [points, setPoints] = useState({ attack: 0, defense: 0, production: 0 });

  const fetchData = async () => {
    try {
      const [heroRes, itemsRes] = await Promise.all([
        axiosClient.get('/hero/'),
        api.getHeroItems()
      ]);
      setHero(heroRes.data);
      setItems(itemsRes.data);
    } catch (err) {
      console.error(err);
      setError('Failed to load hero data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleDistribute = async () => {
    try {
      const res = await axiosClient.post('/hero/distribute', points);
      setHero(res.data);
      setPoints({ attack: 0, defense: 0, production: 0 });
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to distribute points');
    }
  };

  const handleRevive = async () => {
    try {
      const res = await axiosClient.post('/hero/revive');
      setHero(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to revive hero');
    }
  };

  const handleEquip = async (itemId) => {
    try {
      const res = await api.equipHeroItem(itemId);
      setItems(res.data);
      // Refresh hero stats as they might have changed
      const heroRes = await axiosClient.get('/hero/');
      setHero(heroRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to equip item');
    }
  };

  const handleUnequip = async (itemId) => {
    try {
      const res = await api.unequipHeroItem(itemId);
      setItems(res.data);
      // Refresh hero stats
      const heroRes = await axiosClient.get('/hero/');
      setHero(heroRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to unequip item');
    }
  };

  const incrementPoint = (type) => {
    const currentTotal = points.attack + points.defense + points.production;
    if (currentTotal < hero.available_points) {
      setPoints(prev => ({ ...prev, [type]: prev[type] + 1 }));
    }
  };

  const decrementPoint = (type) => {
    if (points[type] > 0) {
      setPoints(prev => ({ ...prev, [type]: prev[type] - 1 }));
    }
  };

  if (loading) return <div className="p-4 text-white">Loading hero...</div>;
  if (!hero) return <div className="p-4 text-red-500">{error}</div>;

  const equippedItems = items.filter(i => i.is_equipped);
  const inventoryItems = items.filter(i => !i.is_equipped);

  const getEquippedInSlot = (slot) => equippedItems.find(i => i.slot === slot);

  const renderItemCard = (item, actionLabel, onAction) => (
    <div key={item.id} className="bg-gray-700 p-3 rounded border border-gray-600 flex flex-col justify-between">
      <div>
        <div className="font-bold text-yellow-400">{item.name}</div>
        <div className="text-xs text-gray-300 capitalize">{item.slot}</div>
        <div className="text-sm text-green-400 mt-1">
          +{item.bonus_value}% {item.bonus_type.replace('_', ' ')}
        </div>
      </div>
      <button
        onClick={() => onAction(item.id)}
        className="mt-2 bg-blue-600 hover:bg-blue-500 text-xs py-1 px-2 rounded"
      >
        {actionLabel}
      </button>
    </div>
  );

  return (
    <div className="p-4 max-w-6xl mx-auto text-white">
      <h1 className="text-3xl font-bold mb-6 text-yellow-500">Hero: {hero.name}</h1>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Stats & Attributes */}
        <div className="space-y-8">
          {/* Hero Stats */}
          <div className="bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xl font-semibold">Level {hero.level}</span>
              <span className={`px-3 py-1 rounded-full text-sm ${hero.status === 'dead' ? 'bg-red-600' : 'bg-green-600'}`}>
                {hero.status.toUpperCase()}
              </span>
            </div>
            
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1">
                <span>XP</span>
                <span>{hero.xp} / {hero.next_level_xp}</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2.5">
                <div 
                  className="bg-blue-600 h-2.5 rounded-full" 
                  style={{ width: `${Math.min(100, (hero.xp / hero.next_level_xp) * 100)}%` }}
                ></div>
              </div>
            </div>

            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1">
                <span>Health</span>
                <span>{Math.round(hero.health)}%</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2.5">
                <div 
                  className="bg-red-600 h-2.5 rounded-full" 
                  style={{ width: `${hero.health}%` }}
                ></div>
              </div>
            </div>

            {hero.status === 'dead' && (
              <button 
                onClick={handleRevive}
                className="w-full mt-4 bg-yellow-600 hover:bg-yellow-700 text-white font-bold py-2 px-4 rounded transition"
              >
                Revive Hero
              </button>
            )}
          </div>

          {/* Attributes */}
          <div className="bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-700">
            <h2 className="text-xl font-semibold mb-4 text-yellow-400">Attributes</h2>
            <div className="mb-4 text-sm text-gray-400">
              Available Points: <span className="text-white font-bold">{hero.available_points - (points.attack + points.defense + points.production)}</span>
            </div>

            <div className="space-y-4">
              {['attack', 'defense', 'production'].map(attr => (
                <div key={attr} className="flex items-center justify-between">
                  <span className="capitalize w-24">{attr}</span>
                  <span className="font-mono text-lg w-8 text-center">
                    {hero[`${attr}_points`] + points[attr]}
                  </span>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => decrementPoint(attr)}
                      disabled={points[attr] === 0}
                      className="w-8 h-8 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50"
                    >
                      -
                    </button>
                    <button 
                      onClick={() => incrementPoint(attr)}
                      disabled={hero.available_points - (points.attack + points.defense + points.production) <= 0}
                      className="w-8 h-8 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50"
                    >
                      +
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {(points.attack > 0 || points.defense > 0 || points.production > 0) && (
              <button 
                onClick={handleDistribute}
                className="w-full mt-6 bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition"
              >
                Save Changes
              </button>
            )}
          </div>

          {/* Conquest Info */}
          <div className="bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-700">
            <h3 className="text-xl font-semibold mb-4 text-amber-500">Conquista de Oasis</h3>
            <p className="text-sm text-gray-300 mb-2">
              Tu héroe es esencial para expandir tu imperio. Envía a tu héroe en ataques a Oasis salvajes para anexionarlos a tu ciudad.
            </p>
            <ul className="list-disc list-inside text-sm text-gray-400 space-y-1">
              <li>Requiere que el héroe sobreviva a la batalla.</li>
              <li>Elimina todas las bestias salvajes.</li>
              <li>Otorga bonificaciones de producción permanentes.</li>
            </ul>
          </div>
        </div>

        {/* Middle Column: Equipment Slots */}
        <div className="bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-700">
          <h2 className="text-xl font-semibold mb-6 text-yellow-400 text-center">Equipment</h2>
          <div className="flex flex-col items-center gap-4">
            {['helmet', 'weapon', 'armor', 'boots', 'mount'].map(slot => {
              const item = getEquippedInSlot(slot);
              return (
                <div key={slot} className="w-full max-w-xs">
                  <div className="text-xs text-gray-400 mb-1 capitalize text-center">{slot}</div>
                  {item ? (
                    <div className="bg-gray-700 p-3 rounded border border-yellow-600 relative group">
                      <div className="font-bold text-yellow-400 text-center">{item.name}</div>
                      <div className="text-sm text-green-400 text-center">
                        +{item.bonus_value}% {item.bonus_type.replace('_', ' ')}
                      </div>
                      <button
                        onClick={() => handleUnequip(item.id)}
                        className="absolute top-0 right-0 bg-red-600 text-white text-xs p-1 rounded opacity-0 group-hover:opacity-100 transition"
                      >
                        X
                      </button>
                    </div>
                  ) : (
                    <div className="bg-gray-900 p-4 rounded border border-gray-700 border-dashed text-center text-gray-600 h-16 flex items-center justify-center">
                      Empty
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Inventory */}
        <div className="bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-700">
          <h2 className="text-xl font-semibold mb-4 text-yellow-400">Inventory</h2>
          {inventoryItems.length === 0 ? (
            <div className="text-gray-500 text-center italic">No items in inventory</div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {inventoryItems.map(item => renderItemCard(item, 'Equip', handleEquip))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default HeroView;
