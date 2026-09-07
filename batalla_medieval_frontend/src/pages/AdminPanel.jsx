import { useCallback, useEffect, useMemo, useState } from 'react';
import axiosClient, { api } from '../api/axiosClient';

const errorDetail = (error) => error?.response?.data?.detail || error?.message || 'Error desconocido';

const AdminPanel = () => {
  const [message, setMessage] = useState('');
  const [worlds, setWorlds] = useState([]);
  const [selectedWorldId, setSelectedWorldId] = useState('');
  const [lifecycleReason, setLifecycleReason] = useState('');
  const [reason, setReason] = useState('');
  const [supportCaseId, setSupportCaseId] = useState('');
  const [logs, setLogs] = useState([]);
  const [supportCases, setSupportCases] = useState([]);

  const [targetCityId, setTargetCityId] = useState('');
  const [resources, setResources] = useState({ wood: 1000, stone: 1000, iron: 1000, gold: 1000 });
  const [buildingType, setBuildingType] = useState('town_hall');
  const [buildingLevel, setBuildingLevel] = useState(1);
  const [troopType, setTroopType] = useState('basic_infantry');
  const [troopAmount, setTroopAmount] = useState(0);
  const [coords, setCoords] = useState({ x: 0, y: 0 });

  const [targetUserId, setTargetUserId] = useState('');
  const [adminRole, setAdminRole] = useState('support');
  const [moderationKind, setModerationKind] = useState('chat');
  const [moderationTargetId, setModerationTargetId] = useState('');

  const log = useCallback((text) => {
    setMessage((previous) => `${previous}${previous ? '\n' : ''}${text}`);
  }, []);

  const commonPayload = useCallback(() => ({
    reason: reason.trim(),
    ...(supportCaseId ? { support_case_id: Number(supportCaseId) } : {}),
  }), [reason, supportCaseId]);

  const requireReason = () => {
    if (reason.trim()) return true;
    log('El motivo administrativo es obligatorio.');
    return false;
  };

  const loadWorlds = useCallback(async () => {
    try {
      const response = await api.adminGetWorlds();
      const rows = response.data || [];
      setWorlds(rows);
      setSelectedWorldId((current) => current || (rows[0] ? String(rows[0].id) : ''));
    } catch (error) {
      log(`Mundos: ${errorDetail(error)}`);
    }
  }, [log]);

  const loadOperationalData = useCallback(async () => {
    const [logResult, caseResult] = await Promise.allSettled([
      axiosClient.get('/admin/logs', { params: { limit: 50 } }),
      axiosClient.get('/support/admin/cases', { params: { limit: 50 } }),
    ]);
    if (logResult.status === 'fulfilled') setLogs(logResult.value.data || []);
    if (caseResult.status === 'fulfilled') setSupportCases(caseResult.value.data || []);
  }, []);

  useEffect(() => {
    loadWorlds();
    loadOperationalData();
  }, [loadWorlds, loadOperationalData]);

  const selectedLifecycleWorld = useMemo(
    () => worlds.find((world) => String(world.id) === String(selectedWorldId)),
    [worlds, selectedWorldId],
  );

  const allowedLifecycleTargets = {
    draft: ['open'],
    open: ['paused', 'closed'],
    paused: ['open', 'closed'],
    closed: ['archived'],
    archived: [],
  };

  const transitionWorld = async (targetStatus) => {
    if (!selectedLifecycleWorld) return log('Selecciona un mundo.');
    if (!lifecycleReason.trim()) return log('El motivo de transición es obligatorio.');
    try {
      const response = await api.transitionWorldLifecycle(
        selectedLifecycleWorld.id,
        selectedLifecycleWorld.lifecycle_status,
        targetStatus,
        lifecycleReason.trim(),
      );
      log(`Mundo ${selectedLifecycleWorld.id}: ${selectedLifecycleWorld.lifecycle_status} → ${response.data.lifecycle_status}`);
      setLifecycleReason('');
      await Promise.all([loadWorlds(), loadOperationalData()]);
    } catch (error) {
      log(`Lifecycle: ${errorDetail(error)}`);
      await loadWorlds();
    }
  };

  const runAdminAction = async (label, action) => {
    if (!requireReason()) return;
    try {
      await action();
      log(`${label}: operación registrada y auditada.`);
      await loadOperationalData();
    } catch (error) {
      log(`${label}: ${errorDetail(error)}`);
    }
  };

  const updateResources = () => {
    if (!targetCityId) return log('ID de ciudad obligatorio.');
    return runAdminAction('Recursos', () => axiosClient.patch(
      `/admin/city/${targetCityId}/resources`,
      { ...resources, ...commonPayload() },
    ));
  };

  const setBuildingLevel = () => {
    if (!targetCityId) return log('ID de ciudad obligatorio.');
    return runAdminAction('Edificio', () => axiosClient.patch(
      `/admin/city/${targetCityId}/building/${buildingType}`,
      { new_level: Number(buildingLevel), ...commonPayload() },
    ));
  };

  const setTroops = () => {
    if (!targetCityId) return log('ID de ciudad obligatorio.');
    return runAdminAction('Tropas', () => axiosClient.patch(
      `/admin/city/${targetCityId}/troops`,
      { troops: { [troopType]: Number(troopAmount) }, ...commonPayload() },
    ));
  };

  const teleportCity = () => {
    if (!targetCityId) return log('ID de ciudad obligatorio.');
    return runAdminAction('Coordenadas', () => axiosClient.patch(
      `/admin/city/${targetCityId}/coordinates`,
      { x: Number(coords.x), y: Number(coords.y), ...commonPayload() },
    ));
  };

  const setFreeze = (isFrozen) => {
    if (!targetUserId) return log('ID de usuario obligatorio.');
    return runAdminAction(isFrozen ? 'Congelar cuenta' : 'Descongelar cuenta', () => axiosClient.patch(
      `/admin/user/${targetUserId}/freeze`,
      { is_frozen: isFrozen, ...commonPayload() },
    ));
  };

  const setRole = (enabled) => {
    if (!targetUserId) return log('ID de usuario obligatorio.');
    return runAdminAction(enabled ? 'Asignar rol' : 'Revocar rol', () => axiosClient.patch(
      `/admin/user/${targetUserId}/role`,
      { enabled, role: enabled ? adminRole : null, ...commonPayload() },
    ));
  };

  const moderateContent = (hidden) => {
    if (!moderationTargetId) return log('ID del contenido obligatorio.');
    return runAdminAction(hidden ? 'Ocultar contenido' : 'Restaurar contenido', () => axiosClient.patch(
      `/admin/moderation/${moderationKind}/${moderationTargetId}`,
      { hidden, ...commonPayload() },
    ));
  };

  const revertLog = async (entry) => {
    if (!requireReason()) return;
    try {
      await axiosClient.post(`/admin/logs/${entry.id}/revert`, { reason: reason.trim() });
      log(`Auditoría #${entry.id}: reversión aplicada.`);
      await loadOperationalData();
    } catch (error) {
      log(`Reversión #${entry.id}: ${errorDetail(error)}`);
    }
  };

  const updateCase = async (supportCase, status) => {
    if (!requireReason()) return;
    try {
      await axiosClient.patch(`/support/admin/cases/${supportCase.id}`, {
        status,
        reason: reason.trim(),
        ...(status === 'resolved' ? { resolution: `Resuelto desde administración: ${reason.trim()}` } : {}),
      });
      log(`Caso #${supportCase.id}: ${status}.`);
      await loadOperationalData();
    } catch (error) {
      log(`Caso #${supportCase.id}: ${errorDetail(error)}`);
    }
  };

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto pb-20" data-testid="bm0073-admin-panel">
      <div>
        <h1 className="text-3xl font-bold text-red-500">Administración y soporte</h1>
        <p className="text-sm text-gray-400 mt-1">Sin borrado duro: toda intervención sensible exige motivo y queda auditada.</p>
      </div>

      <section className="card bg-gray-900 p-5 border border-red-900/60" data-testid="admin-operation-context">
        <h2 className="text-lg font-bold text-red-300 mb-3">Contexto obligatorio</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="input w-full bg-black/50 border-gray-600"
            placeholder="Motivo administrativo obligatorio"
            data-testid="admin-reason"
          />
          <input
            type="number"
            min="1"
            value={supportCaseId}
            onChange={(event) => setSupportCaseId(event.target.value)}
            className="input w-full bg-black/50 border-gray-600"
            placeholder="Caso de soporte (opcional)"
            data-testid="admin-support-case-id"
          />
        </div>
      </section>

      <section className="card bg-gray-900 p-5 border border-amber-700/50" data-testid="world-lifecycle-admin">
        <h2 className="text-xl font-bold text-amber-400 mb-3">Ciclo de vida de mundos</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <select
            value={selectedWorldId}
            onChange={(event) => setSelectedWorldId(event.target.value)}
            className="select w-full bg-black/50 border-gray-600"
            data-testid="world-lifecycle-select"
          >
            {worlds.map((world) => <option key={world.id} value={world.id}>{world.name} — {world.lifecycle_status}</option>)}
          </select>
          <input
            value={lifecycleReason}
            onChange={(event) => setLifecycleReason(event.target.value)}
            className="input w-full bg-black/50 border-gray-600"
            placeholder="Motivo de transición"
            data-testid="world-lifecycle-reason"
          />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="badge badge-outline" data-testid="world-lifecycle-current">Estado: {selectedLifecycleWorld?.lifecycle_status || '—'}</span>
          {(allowedLifecycleTargets[selectedLifecycleWorld?.lifecycle_status] || []).map((target) => (
            <button
              key={target}
              onClick={() => transitionWorld(target)}
              className="btn btn-sm bg-amber-700 hover:bg-amber-600 text-white border-none"
              data-testid={`world-lifecycle-to-${target}`}
            >Cambiar a {target}</button>
          ))}
        </div>
      </section>

      <section className="card bg-gray-900 p-5 border border-gray-700" data-testid="admin-game-corrections">
        <h2 className="text-xl font-bold text-amber-400 mb-3">Correcciones del juego</h2>
        <input type="number" value={targetCityId} onChange={(event) => setTargetCityId(event.target.value)} className="input w-full bg-black/50 border-gray-600 mb-4" placeholder="ID de ciudad" />
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          <div className="space-y-2">
            <h3 className="font-semibold">Recursos</h3>
            {Object.keys(resources).map((key) => (
              <input key={key} type="number" value={resources[key]} onChange={(event) => setResources({ ...resources, [key]: Number(event.target.value) })} className="input input-sm w-full bg-black/50 border-gray-600" placeholder={key} />
            ))}
            <button className="btn btn-sm w-full" onClick={updateResources}>Aplicar recursos</button>
          </div>
          <div className="space-y-2">
            <h3 className="font-semibold">Edificio</h3>
            <input value={buildingType} onChange={(event) => setBuildingType(event.target.value)} className="input input-sm w-full bg-black/50 border-gray-600" />
            <input type="number" min="0" value={buildingLevel} onChange={(event) => setBuildingLevel(event.target.value)} className="input input-sm w-full bg-black/50 border-gray-600" />
            <button className="btn btn-sm w-full" onClick={setBuildingLevel}>Fijar nivel</button>
          </div>
          <div className="space-y-2">
            <h3 className="font-semibold">Tropas</h3>
            <input value={troopType} onChange={(event) => setTroopType(event.target.value)} className="input input-sm w-full bg-black/50 border-gray-600" />
            <input type="number" min="0" value={troopAmount} onChange={(event) => setTroopAmount(event.target.value)} className="input input-sm w-full bg-black/50 border-gray-600" />
            <button className="btn btn-sm w-full" onClick={setTroops}>Fijar cantidad</button>
          </div>
          <div className="space-y-2">
            <h3 className="font-semibold">Coordenadas</h3>
            <div className="flex gap-2">
              <input type="number" value={coords.x} onChange={(event) => setCoords({ ...coords, x: event.target.value })} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="X" />
              <input type="number" value={coords.y} onChange={(event) => setCoords({ ...coords, y: event.target.value })} className="input input-sm w-full bg-black/50 border-gray-600" placeholder="Y" />
            </div>
            <button className="btn btn-sm w-full" onClick={teleportCity}>Mover ciudad</button>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="card bg-gray-900 p-5 border border-gray-700" data-testid="admin-account-controls">
          <h2 className="text-xl font-bold text-amber-400 mb-3">Cuenta y roles</h2>
          <input type="number" value={targetUserId} onChange={(event) => setTargetUserId(event.target.value)} className="input w-full bg-black/50 border-gray-600 mb-3" placeholder="ID de usuario" />
          <div className="flex flex-wrap gap-2 mb-4">
            <button className="btn btn-sm" onClick={() => setFreeze(true)}>Congelar</button>
            <button className="btn btn-sm" onClick={() => setFreeze(false)}>Descongelar</button>
          </div>
          <div className="flex gap-2">
            <select value={adminRole} onChange={(event) => setAdminRole(event.target.value)} className="select select-sm bg-black/50 border-gray-600 flex-1">
              <option value="support">support</option>
              <option value="moderator">moderator</option>
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
            <button className="btn btn-sm" onClick={() => setRole(true)}>Asignar</button>
            <button className="btn btn-sm" onClick={() => setRole(false)}>Revocar</button>
          </div>
        </section>

        <section className="card bg-gray-900 p-5 border border-gray-700" data-testid="admin-global-moderation">
          <h2 className="text-xl font-bold text-amber-400 mb-3">Moderación reversible</h2>
          <div className="flex gap-2 mb-3">
            <select value={moderationKind} onChange={(event) => setModerationKind(event.target.value)} className="select select-sm bg-black/50 border-gray-600">
              <option value="chat">Chat</option>
              <option value="forum">Foro</option>
            </select>
            <input type="number" min="1" value={moderationTargetId} onChange={(event) => setModerationTargetId(event.target.value)} className="input input-sm flex-1 bg-black/50 border-gray-600" placeholder="ID del contenido" />
          </div>
          <div className="flex gap-2">
            <button className="btn btn-sm" onClick={() => moderateContent(true)}>Ocultar</button>
            <button className="btn btn-sm" onClick={() => moderateContent(false)}>Restaurar</button>
          </div>
        </section>
      </div>

      <section className="card bg-gray-900 p-5 border border-gray-700" data-testid="admin-support-cases">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xl font-bold text-amber-400">Casos de soporte</h2>
          <button className="btn btn-xs" onClick={loadOperationalData}>Actualizar</button>
        </div>
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead><tr><th>ID</th><th>Asunto</th><th>Estado</th><th>Prioridad</th><th>Acciones</th></tr></thead>
            <tbody>
              {supportCases.map((supportCase) => (
                <tr key={supportCase.id}>
                  <td>#{supportCase.id}</td><td>{supportCase.subject}</td><td>{supportCase.status}</td><td>{supportCase.priority}</td>
                  <td className="flex gap-1"><button className="btn btn-xs" onClick={() => updateCase(supportCase, 'in_progress')}>Tomar</button><button className="btn btn-xs" onClick={() => updateCase(supportCase, 'resolved')}>Resolver</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card bg-gray-900 p-5 border border-gray-700" data-testid="admin-audit-log">
        <h2 className="text-xl font-bold text-amber-400 mb-3">Auditoría reciente</h2>
        <div className="space-y-2 max-h-96 overflow-auto">
          {logs.map((entry) => (
            <div key={entry.id} className="border border-gray-700 rounded p-3 flex flex-col md:flex-row md:items-center gap-2">
              <div className="flex-1 text-sm"><strong>#{entry.id} {entry.action}</strong><div className="text-gray-400">{entry.reason || 'Sin motivo legacy'}</div></div>
              {entry.reversible && !entry.reversed_at && <button className="btn btn-xs" onClick={() => revertLog(entry)}>Revertir</button>}
              {entry.reversed_at && <span className="badge badge-outline">Revertido</span>}
            </div>
          ))}
        </div>
      </section>

      <pre className="bg-black/60 border border-gray-700 rounded p-4 whitespace-pre-wrap text-sm min-h-16" data-testid="admin-operation-log">{message || 'Sin operaciones en esta sesión.'}</pre>
    </div>
  );
};

export default AdminPanel;
