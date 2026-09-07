import { useState } from 'react';
import axiosClient from '../api/axiosClient';

const errorDetail = (error) => error?.response?.data?.detail || error?.message || 'Error desconocido';

const AdminCityCreateCard = () => {
  const [form, setForm] = useState({
    ownerId: '',
    worldId: '',
    name: 'Nueva ciudad',
    x: 0,
    y: 0,
    reason: '',
    supportCaseId: '',
  });
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const createCity = async (event) => {
    event.preventDefault();
    if (!form.ownerId || !form.worldId || !form.name.trim() || !form.reason.trim()) {
      setMessage('Propietario, mundo, nombre y motivo son obligatorios.');
      return;
    }

    setSubmitting(true);
    setMessage('');
    try {
      const response = await axiosClient.post('/admin/city/create', {
        owner_id: Number(form.ownerId),
        world_id: Number(form.worldId),
        name: form.name.trim(),
        x: Number(form.x),
        y: Number(form.y),
        reason: form.reason.trim(),
        ...(form.supportCaseId ? { support_case_id: Number(form.supportCaseId) } : {}),
      });
      setMessage(`Ciudad creada correctamente. ID: ${response.data.id}`);
    } catch (error) {
      setMessage(`Crear ciudad: ${errorDetail(error)}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section
      className="card bg-gray-900 p-5 border border-emerald-800/60 mt-6"
      data-testid="admin-city-create"
    >
      <h2 className="text-xl font-bold text-emerald-400 mb-2">Crear ciudad administrativa</h2>
      <p className="text-sm text-gray-400 mb-4">
        Operación de corrección controlada: exige capacidad de juego, motivo y queda auditada.
      </p>

      <form onSubmit={createCity} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        <input
          type="number"
          min="1"
          value={form.ownerId}
          onChange={(event) => updateField('ownerId', event.target.value)}
          className="input w-full bg-black/50 border-gray-600"
          placeholder="ID del propietario"
          data-testid="admin-city-owner-id"
        />
        <input
          type="number"
          min="1"
          value={form.worldId}
          onChange={(event) => updateField('worldId', event.target.value)}
          className="input w-full bg-black/50 border-gray-600"
          placeholder="ID del mundo"
          data-testid="admin-city-world-id"
        />
        <input
          value={form.name}
          onChange={(event) => updateField('name', event.target.value)}
          className="input w-full bg-black/50 border-gray-600"
          placeholder="Nombre de ciudad"
          data-testid="admin-city-name"
        />
        <input
          type="number"
          value={form.x}
          onChange={(event) => updateField('x', event.target.value)}
          className="input w-full bg-black/50 border-gray-600"
          placeholder="Coordenada X"
          data-testid="admin-city-x"
        />
        <input
          type="number"
          value={form.y}
          onChange={(event) => updateField('y', event.target.value)}
          className="input w-full bg-black/50 border-gray-600"
          placeholder="Coordenada Y"
          data-testid="admin-city-y"
        />
        <input
          type="number"
          min="1"
          value={form.supportCaseId}
          onChange={(event) => updateField('supportCaseId', event.target.value)}
          className="input w-full bg-black/50 border-gray-600"
          placeholder="Caso de soporte (opcional)"
          data-testid="admin-city-support-case-id"
        />
        <input
          value={form.reason}
          onChange={(event) => updateField('reason', event.target.value)}
          className="input w-full bg-black/50 border-gray-600 md:col-span-2"
          placeholder="Motivo administrativo obligatorio"
          data-testid="admin-city-reason"
        />
        <button
          type="submit"
          disabled={submitting}
          className="btn bg-emerald-700 hover:bg-emerald-600 text-white border-none"
          data-testid="admin-city-submit"
        >
          {submitting ? 'Creando…' : 'Crear ciudad'}
        </button>
      </form>

      {message && (
        <p className="mt-3 text-sm text-gray-200" data-testid="admin-city-message">{message}</p>
      )}
    </section>
  );
};

export default AdminCityCreateCard;
