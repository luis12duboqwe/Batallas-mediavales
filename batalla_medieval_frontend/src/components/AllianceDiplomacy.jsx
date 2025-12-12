import { useEffect, useState } from 'react';
import { api } from '../api/axiosClient';
import { formatDate } from '../utils/format';

const AllianceDiplomacy = ({ alliance, myRank }) => {
  const [relations, setRelations] = useState([]);
  const [targetId, setTargetId] = useState('');
  const [statusType, setStatusType] = useState('nap');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchDiplomacy();
  }, [alliance.id]);

  const fetchDiplomacy = async () => {
    try {
      const res = await api.getDiplomacy(alliance.id);
      setRelations(res.data);
    } catch (error) {
      console.error(error);
    }
  };

  const handleRequest = async (e) => {
    e.preventDefault();
    if (!targetId) return;
    setLoading(true);
    try {
      await api.requestDiplomacy(alliance.id, parseInt(targetId), statusType);
      setTargetId('');
      fetchDiplomacy();
      alert('Solicitud enviada / Estado actualizado');
    } catch (error) {
      alert(error.response?.data?.detail || 'Error');
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = async (diplomacyId) => {
    try {
      await api.acceptDiplomacy(alliance.id, diplomacyId);
      fetchDiplomacy();
    } catch (error) {
      alert('Error al aceptar');
    }
  };

  const handleCancel = async (diplomacyId) => {
    if (!confirm('¿Seguro que quieres cancelar esta relación?')) return;
    try {
      await api.cancelDiplomacy(alliance.id, diplomacyId);
      fetchDiplomacy();
    } catch (error) {
      alert('Error al cancelar');
    }
  };

  const getStatusLabel = (status) => {
    switch (status) {
      case 'war': return <span className="text-red-500 font-bold">GUERRA</span>;
      case 'nap': return <span className="text-blue-400 font-bold">PNA (Pacto No Agresión)</span>;
      case 'ally': return <span className="text-green-500 font-bold">ALIADOS</span>;
      default: return <span className="text-gray-400 italic">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div className="card bg-black/40 border border-amber-900/30 p-6">
        <h3 className="text-xl font-bold text-amber-200 mb-4">Relaciones Diplomáticas</h3>
        
        {relations.length === 0 ? (
          <p className="text-gray-500">No hay relaciones activas.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="table w-full">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th>Alianza</th>
                  <th>Estado</th>
                  <th>Actualizado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {relations.map(rel => {
                  const otherId = rel.alliance_a_id === alliance.id ? rel.alliance_b_id : rel.alliance_a_id;
                  const isPending = rel.status.startsWith('pending_');
                  
                  return (
                    <tr key={rel.id} className="hover:bg-white/5">
                      <td className="font-bold text-gray-300">ID: {otherId}</td>
                      <td>{getStatusLabel(rel.status)}</td>
                      <td className="text-xs text-gray-500">{formatDate(rel.updated_at)}</td>
                      <td>
                        {isPending && rel.alliance_b_id === alliance.id && myRank >= 2 && (
                          <button onClick={() => handleAccept(rel.id)} className="btn btn-xs btn-success mr-2">
                            Aceptar
                          </button>
                        )}
                        {myRank >= 2 && (
                          <button onClick={() => handleCancel(rel.id)} className="btn btn-xs btn-error">
                            Cancelar
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {myRank >= 2 && (
        <div className="card bg-black/40 border border-amber-900/30 p-6 max-w-md">
          <h3 className="text-lg font-bold text-amber-200 mb-4">Gestionar Diplomacia</h3>
          <form onSubmit={handleRequest} className="space-y-4">
            <div>
              <label className="label text-sm text-gray-400">ID de Alianza Objetivo</label>
              <input 
                type="number" 
                className="input input-bordered w-full bg-black/50"
                value={targetId}
                onChange={e => setTargetId(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="label text-sm text-gray-400">Tipo de Relación</label>
              <select 
                className="select select-bordered w-full bg-black/50"
                value={statusType}
                onChange={e => setStatusType(e.target.value)}
              >
                <option value="nap">PNA (Pacto No Agresión)</option>
                <option value="ally">Alianza Total</option>
                <option value="war">Declarar GUERRA</option>
              </select>
            </div>
            <button type="submit" className="btn btn-primary w-full" disabled={loading}>
              {loading ? 'Enviando...' : 'Enviar Solicitud'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
};

export default AllianceDiplomacy;
