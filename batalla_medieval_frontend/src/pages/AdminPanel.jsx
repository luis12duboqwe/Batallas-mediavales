import { useEffect, useState } from 'react';
import { api } from '../api/axiosClient';

const AdminPanel = () => {
  const [targetCityId, setTargetCityId] = useState('');
  const [message, setMessage] = useState('');
  const [worlds, setWorlds] = useState([]);
  const [selectedWorldId, setSelectedWorldId] = useState('');
  const [lifecycleReason, setLifecycleReason] = useState('');
  
  // Resources
  const [res, setRes] = useState({ wood: 1000, stone: 1000, iron: 1000, gold: 1000 });
  
  // Building
  const [buildType, setBuildType] = useState('town_hall');
  const [buildLevel, setBuildLevel] = useState(10);
  
  // Troops
  const [troopType, setTroopType] = useState('basic_infantry');
  const [troopAmount, setTroopAmount] = useState(100);

  // Teleport
  const [coords, setCoords] = useState({ x: 0, y: 0 });

  // Create City
  const [newCity, setNewCity] = useState({ owner_id: '', world_id: '', name: 'New City', x: 0, y: 0 });

  // Delete User
  const [deleteUserId, setDeleteUserId] = useState('');

  const log = (msg) => setMessage(prev => prev + '\n' + msg);

  const loadWorlds = async () => {
      try {
          const response = await api.getWorlds();
          setWorlds(response.data || []);
          if (!selectedWorldId && response.data?.length) {
              setSelectedWorldId(String(response.data[0].id));
          }
      } catch (e) {
          log('Error al cargar mundos: ' + (e.response?.data?.detail || e.message));
      }
  };

  useEffect(() => {
      loadWorlds();
      // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedLifecycleWorld = worlds.find(world => String(world.id) === String(selectedWorldId));

  const transitionWorld = async (targetStatus) => {
      if (!selectedLifecycleWorld) return log('Selecciona un mundo');
      if (!lifecycleReason.trim()) return log('El motivo de transición es obligatorio');
      try {
          const response = await api.transitionWorldLifecycle(
              selectedLifecycleWorld.id,
              selectedLifecycleWorld.lifecycle_status,
              targetStatus,
              lifecycleReason.trim(),
          );
          log(`Mundo ${selectedLifecycleWorld.id}: ${selectedLifecycleWorld.lifecycle_status} → ${response.data.lifecycle_status}`);
          setLifecycleReason('');
          await loadWorlds();
      } catch (e) {
          log('Error lifecycle: ' + (e.response?.data?.detail || e.message));
          await loadWorlds();
      }
  };

  const allowedLifecycleTargets = {
      draft: ['open'],
      open: ['paused', 'closed'],
      paused: ['open', 'closed'],
      closed: ['archived'],
      archived: [],
  };

  const updateResources = async () => {
      if (!targetCityId) return log('City ID required');
      try {
          await api.adminUpdateResources(targetCityId, res);
          log(`Resources updated for city ${targetCityId}`);
      } catch (e) { log('Error: ' + (e.response?.data?.detail || e.message)); }
  };

  const setBuildingLevel = async () => {
      if (!targetCityId) return log('City ID required');
      try {
          await api.adminSetBuildingLevel(targetCityId, buildType, buildLevel);
          log(`Building ${buildType} set to ${buildLevel} for city ${targetCityId}`);
      } catch (e) { log('Error: ' + (e.response?.data?.detail || e.message)); }
  };

  const setTroops = async () => {
      if (!targetCityId) return log('City ID required');
      try {
          await api.adminSetTroops(targetCityId, { [troopType]: troopAmount });
          log(`Troops ${troopType} set to ${troopAmount} for city ${targetCityId}`);
      } catch (e) { log('Error: ' + (e.response?.data?.detail || e.message)); }
  };

  const teleportCity = async () => {
      if (!targetCityId) return log('City ID required');
      try {
          await api.adminTeleportCity(targetCityId, coords.x, coords.y);
          log(`City ${targetCityId} teleported to (${coords.x}, ${coords.y})`);
      } catch (e) { log('Error: ' + (e.response?.data?.detail || e.message)); }
  };

  const createCity = async () => {
      if (!newCity.owner_id) return log('Owner ID required');
      if (!newCity.world_id) return log('World ID required');
      try {
          const payload = {
              ...newCity,
              owner_id: Number(newCity.owner_id),
              world_id: Number(newCity.world_id),
          };
          const response = await api.adminCreateCity(payload);
          log(`City created! ID: ${response.data.id}`);
      } catch (e) { log('Error: ' + (e.response?.data?.detail || e.message)); }
  };

  const deleteCity = async () => {
      if (!targetCityId) return log('City ID required');
      if (!confirm(`¿Eliminar ciudad ${targetCityId}?`)) return;
      try {
          await api.adminDeleteCity(targetCityId);
          log(`City ${targetCityId} deleted`);
      } catch (e) { log('Error: ' + (e.response?.data?.detail || e.message)); }
  };

  const deleteUser = async () => {
      if (!deleteUserId) return log('User ID required');
      if (!confirm(`¿Eliminar usuario ${deleteUserId}?`)) return;
      try {
          await api.adminDeleteUser(deleteUserId);
          log(`User ${deleteUserId} deleted`);
      } catch (e) { log('Error: ' + (e.response?.data?.detail || e.message)); }
  };

  return (
      <div className="p-6 space-y-8 max-w-6xl mx-auto pb-20">
          <h1 className="text-3xl font-bold text-red-500">Panel de Administración</h1>
          
          <section className="card bg-gray-900 p-5 border border-amber-700/50" data-testid="world-lifecycle-admin">
              <div className="flex flex-col md:flex-row md:items-end gap-4">
                  <div className="flex-1">
                      <h2 className="text-xl font-bold text-amber-400 mb-3">Ciclo de vida de mundos</h2>
                      <label className="block text-gray-400 mb-1 text-sm">Mundo</label>
                      <select
                          value={selectedWorldId}
                          onChange={e => setSelectedWorldId(e.target.value)}
                          className="select w-full bg-black/50 border-gray-600"
                          data-testid="world-lifecycle-select"
                      >
                          {worlds.map(world => (
                              <option key={world.id} value={world.id}>
                                  {world.name} — {world.lifecycle_status}
                              </option>
                          ))}
                      </select>
                  </div>
                  <div className="flex-1">
                      <label className="block text-gray-400 mb-1 text-sm">Motivo obligatorio</label>
                      <input
                          value={lifecycleReason}
                          onChange={e => setLifecycleReason(e.target.value)}
                          className="input w-full bg-black/50 border-gray-600"
                          placeholder="Motivo de la transición"
                          data-testid="world-lifecycle-reason"
                      />
                  </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                  <span className="badge badge-outline" data-testid="world-lifecycle-current">
                      Estado: {selectedLifecycleWorld?.lifecycle_status || '—'}
                  </span>
                  {(allowedLifecycleTargets[selectedLifecycleWorld?.lifecycle_status] || []).map(target => (
                      <button
                          key={target}
                          onClick={() => transitionWorld(target)}
                          className="btn btn-sm bg-amber-700 hover:bg-amber-600 text-white border-none"
                          data-testid={`world-lifecycle-to-${target}`}
                      >
                          Cambiar a {target}
                      </button>
                  ))}
              </div>
          </section>

          {/* Target City Selector */}
          <div className="bg-gray-900 p-4 rounded border border-red-900 flex items-center gap-4">
              <div className="flex-1">
                <label className="block text-gray-400 mb-1 text-sm">ID Ciudad Objetivo (Operaciones)</label>
                <input 
                    type="number" 
                    value={targetCityId} 
                    onChange={e => setTargetCityId(e.target.value)}
                    className="input input-bordered bg-black/50 w-full border-gray-600"
                    placeholder="ID de Ciudad"
                />
              </div>
              <button onClick={deleteCity} className="btn bg-red-900/50 hover:bg-red-900 text-red-200 border-red-800 mt-6">
                  🗑️ Eliminar Ciudad
              </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {/* Resources */}
              <div className="card bg-gray-800 p-4 border border-gray-700">
                  <h3 className="font-bold mb-4 text-amber-500">1. Recursos</h3>
                  <div className="space-y-2">
                      <input type="number" value={res.wood} onChange={e => setRes({...res, wood: +e.target.value})} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Madera" />
                      <input type="number" value={res.stone} onChange={e => setRes({...res, stone: +e.target.value})} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Piedra" />
                      <input type="number" value={res.iron} onChange={e => setRes({...res, iron: +e.target.value})} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Hierro" />
                      <input type="number" value={res.gold} onChange={e => setRes({...res, gold: +e.target.value})} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Oro" />
                      <button onClick={updateResources} className="btn btn-sm bg-red-700 hover:bg-red-600 text-white w-full border-none">Actualizar</button>
                  </div>
              </div>

              {/* Buildings */}
              <div className="card bg-gray-800 p-4 border border-gray-700">
                  <h3 className="font-bold mb-4 text-amber-500">2. Edificios</h3>
                  <div className="space-y-2">
                      <select value={buildType} onChange={e => setBuildType(e.target.value)} className="select select-sm w-full bg-black/50 border-gray-600">
                          <option value="town_hall">Ayuntamiento</option>
                          <option value="warehouse">Almacén</option>
                          <option value="barracks">Cuartel</option>
                          <option value="farm">Granja</option>
                          <option value="mine">Mina</option>
                          <option value="wall">Muralla</option>
                          <option value="stable">Establo</option>
                      </select>
                      <input type="number" value={buildLevel} onChange={e => setBuildLevel(+e.target.value)} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Nivel" />
                      <button onClick={setBuildingLevel} className="btn btn-sm bg-red-700 hover:bg-red-600 text-white w-full border-none">Fijar Nivel</button>
                  </div>
              </div>

              {/* Troops */}
              <div className="card bg-gray-800 p-4 border border-gray-700">
                  <h3 className="font-bold mb-4 text-amber-500">3. Tropas</h3>
                  <div className="space-y-2">
                      <select value={troopType} onChange={e => setTroopType(e.target.value)} className="select select-sm w-full bg-black/50 border-gray-600">
                          <option value="basic_infantry">Infantería Básica</option>
                          <option value="heavy_infantry">Infantería Pesada</option>
                          <option value="archer">Arquero</option>
                          <option value="fast_cavalry">Caballería Ligera</option>
                          <option value="heavy_cavalry">Caballería Pesada</option>
                          <option value="spy">Espía</option>
                          <option value="ram">Ariete</option>
                          <option value="catapult">Catapulta</option>
                      </select>
                      <input type="number" value={troopAmount} onChange={e => setTroopAmount(+e.target.value)} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Cantidad" />
                      <button onClick={setTroops} className="btn btn-sm bg-red-700 hover:bg-red-600 text-white w-full border-none">Fijar Tropas</button>
                  </div>
              </div>

              {/* Teleport */}
              <div className="card bg-gray-800 p-4 border border-gray-700">
                  <h3 className="font-bold mb-4 text-amber-500">4. Teletransporte</h3>
                  <div className="space-y-2">
                      <div className="flex gap-2">
                        <input type="number" value={coords.x} onChange={e => setCoords({...coords, x: +e.target.value})} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="X" />
                        <input type="number" value={coords.y} onChange={e => setCoords({...coords, y: +e.target.value})} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Y" />
                      </div>
                      <button onClick={teleportCity} className="btn btn-sm bg-purple-700 hover:bg-purple-600 text-white w-full border-none">Teletransportar</button>
                  </div>
              </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Create City */}
              <div className="card bg-gray-800 p-4 border border-gray-700">
                  <h3 className="font-bold mb-4 text-green-500">Crear Nueva Ciudad</h3>
                  <div className="grid grid-cols-2 gap-2">
                      <input type="number" value={newCity.owner_id} onChange={e => setNewCity({...newCity, owner_id: e.target.value})} className="input input-sm bg-black/50 border-gray-600" placeholder="ID Dueño" />
                      <input type="number" value={newCity.world_id} onChange={e => setNewCity({...newCity, world_id: e.target.value})} className="input input-sm bg-black/50 border-gray-600" placeholder="ID Mundo" />
                      <input type="text" value={newCity.name} onChange={e => setNewCity({...newCity, name: e.target.value})} className="input input-sm bg-black/50 border-gray-600" placeholder="Nombre Ciudad" />
                      <input type="number" value={newCity.x} onChange={e => setNewCity({...newCity, x: +e.target.value})} className="input input-sm bg-black/50 border-gray-600" placeholder="X" />
                      <input type="number" value={newCity.y} onChange={e => setNewCity({...newCity, y: +e.target.value})} className="input input-sm bg-black/50 border-gray-600" placeholder="Y" />
                  </div>
                  <button onClick={createCity} className="btn btn-sm bg-green-700 hover:bg-green-600 text-white w-full border-none mt-4">Crear Ciudad</button>
              </div>

              {/* User Management */}
              <div className="card bg-gray-800 p-4 border border-gray-700">
                  <h3 className="font-bold mb-4 text-red-500">Gestión de Usuarios</h3>
                  <div className="flex gap-2">
                      <input type="number" value={deleteUserId} onChange={e => setDeleteUserId(e.target.value)} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="ID Usuario" />
                      <button onClick={deleteUser} className="btn btn-sm bg-red-900 hover:bg-red-800 text-white border-none">Eliminar Usuario</button>
                  </div>
              </div>
          </div>

          <div className="bg-black p-4 rounded font-mono text-xs text-green-500 whitespace-pre-wrap h-40 overflow-y-auto border border-gray-700 shadow-inner">
              {message || '> Sistema listo...'}
          </div>
      </div>
  );
};

export default AdminPanel;
