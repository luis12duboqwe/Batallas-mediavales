import { useState } from 'react';
import { api } from '../api/axiosClient';

const AdminPanel = () => {
  const [targetCityId, setTargetCityId] = useState('');
  const [message, setMessage] = useState('');
  
  // Resources
  const [res, setRes] = useState({ wood: 1000, clay: 1000, iron: 1000 });
  
  // Building
  const [buildType, setBuildType] = useState('town_hall');
  const [buildLevel, setBuildLevel] = useState(10);
  
  // Troops
  const [troopType, setTroopType] = useState('basic_infantry');
  const [troopAmount, setTroopAmount] = useState(100);

  // Teleport
  const [coords, setCoords] = useState({ x: 0, y: 0 });

  // Create City
  const [newCity, setNewCity] = useState({ owner_id: '', name: 'New City', x: 0, y: 0 });

  // Delete User
  const [deleteUserId, setDeleteUserId] = useState('');

  const log = (msg) => setMessage(prev => prev + '\n' + msg);

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
      try {
          const res = await api.adminCreateCity(newCity);
          log(`City created! ID: ${res.data.id}`);
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
                      <input type="number" value={res.clay} onChange={e => setRes({...res, clay: +e.target.value})} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Barro" />
                      <input type="number" value={res.iron} onChange={e => setRes({...res, iron: +e.target.value})} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Hierro" />
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
