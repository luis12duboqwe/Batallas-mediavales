import { useState } from 'react';
import { api } from '../api/axiosClient';

const AdminPanel = () => {
  const [form, setForm] = useState({ wood: 0, clay: 0, iron: 0, building: '', level: 1, message: '' });
  const [status, setStatus] = useState('');

  const resolveCityId = async () => {
    const { data } = await api.getCities();
    if (!data?.length) {
      throw new Error('No hay ciudades disponibles');
    }
    return data[0].id;
  };

  const handleResources = async () => {
    try {
      const cityId = await resolveCityId();
      await api.updateCity(cityId, { resources: form });
      setStatus('Recursos modificados.');
    } catch (err) {
      setStatus('Error al modificar recursos');
    }
  };

  const handleBuilding = async () => {
    try {
      const cityId = await resolveCityId();
      await api.updateCity(cityId, { building: form.building, level: form.level });
      setStatus('Edificio actualizado.');
    } catch (err) {
      setStatus('Error al modificar edificio');
    }
  };

  const handleMessage = async () => {
    try {
      await api.getMessages({ body: form.message });
      setStatus('Mensaje enviado.');
    } catch (err) {
      setStatus('Error al enviar mensaje');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Panel de Administración</h1>
          <p className="text-gray-400">Herramientas avanzadas para game masters</p>
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="card p-4 space-y-3">
          <h2 className="text-xl">Modificar recursos</h2>
          <div className="grid grid-cols-3 gap-2">
            {['wood', 'clay', 'iron'].map((res) => (
              <input
                key={res}
                type="number"
                className="input"
                placeholder={res}
                value={form[res]}
                onChange={(e) => setForm({ ...form, [res]: Number(e.target.value) })}
              />
            ))}
          </div>
          <button className="btn-primary" onClick={handleResources}>Aplicar</button>
        </div>
        <div className="card p-4 space-y-3">
          <h2 className="text-xl">Modificar edificios</h2>
          <input
            className="input w-full"
            placeholder="Nombre del edificio"
            value={form.building}
            onChange={(e) => setForm({ ...form, building: e.target.value })}
          />
          <input
            type="number"
            className="input w-full"
            placeholder="Nivel"
            value={form.level}
            onChange={(e) => setForm({ ...form, level: Number(e.target.value) })}
          />
          <button className="btn-primary" onClick={handleBuilding}>Actualizar</button>
        </div>
        <div className="card p-4 space-y-3 md:col-span-2">
          <h2 className="text-xl">Mensajes del sistema</h2>
          <textarea
            className="input w-full min-h-[120px]"
            placeholder="Contenido del mensaje"
            value={form.message}
            onChange={(e) => setForm({ ...form, message: e.target.value })}
          />
          <button className="btn-primary" onClick={handleMessage}>Enviar mensaje</button>
        </div>
      </div>
      {status && <p className="text-yellow-300">{status}</p>}
    </div>
  );
};

export default AdminPanel;
