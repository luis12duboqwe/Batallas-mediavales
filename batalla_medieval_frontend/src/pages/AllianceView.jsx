import { useEffect, useState } from 'react';
import axiosClient, { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';
import { useUserStore } from '../store/userStore';
import { formatDate } from '../utils/format';
import AllianceDiplomacy from '../components/AllianceDiplomacy';
import AllianceForum from '../components/AllianceForum';

const AllianceView = () => {
  const { user } = useUserStore();
  const { alliance, loadAlliance, currentCity } = useCityStore();
  const [loading, setLoading] = useState(false);
  const [createName, setCreateName] = useState('');
  const [activeTab, setActiveTab] = useState('general'); // general, members, diplomacy, forum
  
  // General Tab State
  const [chatMessage, setChatMessage] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  const [showMassMessageModal, setShowMassMessageModal] = useState(false);
  const [massMessageSubject, setMassMessageSubject] = useState('');
  const [massMessageContent, setMassMessageContent] = useState('');

  // Members Tab State
  const [members, setMembers] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [inviteSearch, setInviteSearch] = useState('');
  const [inviteResults, setInviteResults] = useState([]);
  const [showInviteModal, setShowInviteModal] = useState(false);

  useEffect(() => {
    loadAlliance().catch(() => {});
  }, [loadAlliance]);

  useEffect(() => {
    if (alliance) {
      fetchChat();
      fetchMembers();
      const interval = setInterval(fetchChat, 5000);
      return () => clearInterval(interval);
    } else if (currentCity) {
      fetchInvitations();
    }
  }, [alliance, currentCity]);

  const fetchChat = () => {
    if (!alliance) return;
    axiosClient.get(`/alliance/${alliance.id}/chat`)
      .then(res => setChatMessages(res.data))
      .catch(console.error);
  };

  const fetchMembers = () => {
    if (!alliance) return;
    axiosClient.get(`/alliance/${alliance.id}/members`)
      .then(res => setMembers(res.data))
      .catch(console.error);
  };

  const fetchInvitations = () => {
    if (!currentCity) return;
    api.getInvitations(currentCity.world_id)
      .then(res => setInvitations(res.data))
      .catch(console.error);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!createName.trim()) return;
    
    setLoading(true);
    try {
      await axiosClient.post('/alliance/create', {
        name: createName,
        description: 'Nueva alianza',
        world_id: currentCity.world_id
      });
      await loadAlliance();
      setCreateName('');
    } catch (error) {
      alert(error.response?.data?.detail || 'Error al crear alianza');
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatMessage.trim() || !alliance) return;

    try {
      await axiosClient.post(`/alliance/${alliance.id}/chat`, { message: chatMessage });
      setChatMessage('');
      fetchChat();
    } catch (error) {
      console.error(error);
    }
  };

  const handleAcceptInvitation = async (id) => {
    try {
      await axiosClient.acceptInvitation(id);
      await loadAlliance();
    } catch (error) {
      console.error(error);
      alert('Error al aceptar invitación');
    }
  };

  const handleSearchInvite = async (query) => {
    setInviteSearch(query);
    if (query.length < 3) {
      setInviteResults([]);
      return;
    }
    try {
      const { data } = await axiosClient.searchPlayers(currentCity.world_id, query);
      setInviteResults(data);
    } catch (error) {
      console.error(error);
    }
  };

  const handleInvite = async (userId) => {
    try {
      await axiosClient.invitePlayer(alliance.id, userId);
      alert('Invitación enviada');
      setInviteSearch('');
      setInviteResults([]);
      setShowInviteModal(false);
    } catch (error) {
      alert(error.response?.data?.detail || 'Error al invitar');
    }
  };

  const handleSendMassMessage = async (e) => {
    e.preventDefault();
    if (!massMessageSubject || !massMessageContent) return;
    try {
      await api.sendMassMessage(alliance.id, massMessageSubject, massMessageContent);
      setShowMassMessageModal(false);
      setMassMessageSubject('');
      setMassMessageContent('');
      alert('Mensaje enviado a todos los miembros.');
    } catch (error) {
      console.error(error);
      alert('Error al enviar mensaje.');
    }
  };

  const myRank = members.find(m => m.user_id === user?.id)?.rank || 0;
  const canSendMassMessage = myRank >= 2;

  if (!alliance) {
    return (
      <div className="max-w-4xl mx-auto mt-10 grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Create Alliance */}
        <div className="card bg-black/40 border border-amber-900/30 p-8 text-center">
          <h1 className="text-3xl font-bold text-amber-100 mb-4">Sin Alianza</h1>
          <p className="text-gray-400 mb-8">
            No perteneces a ninguna alianza. Puedes crear una nueva y reclutar a otros señores.
          </p>
          
          <div className="bg-gray-900/50 p-6 rounded-xl border border-gray-800 max-w-md mx-auto">
            <h3 className="text-lg font-bold text-amber-200 mb-4">Fundar una Alianza</h3>
            <form onSubmit={handleCreate} className="space-y-4">
              <input
                type="text"
                placeholder="Nombre de la alianza"
                className="input input-bordered w-full bg-black/50 border-gray-700"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                maxLength={20}
              />
              <button 
                type="submit" 
                className="btn btn-primary w-full bg-amber-700 hover:bg-amber-600 border-none"
                disabled={loading || !createName.trim()}
              >
                {loading ? 'Creando...' : 'Fundar Alianza'}
              </button>
            </form>
          </div>
        </div>

        {/* Invitations */}
        <div className="card bg-black/40 border border-amber-900/30 p-8">
          <h2 className="text-2xl font-bold text-amber-100 mb-4">Invitaciones Pendientes</h2>
          {invitations.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No tienes invitaciones pendientes.</p>
          ) : (
            <div className="space-y-4">
              {invitations.map(inv => (
                <div key={inv.id} className="bg-gray-900/50 p-4 rounded border border-gray-700 flex justify-between items-center">
                  <div>
                    <div className="font-bold text-amber-500">Alianza #{inv.alliance_id}</div>
                    <div className="text-xs text-gray-400">{formatDate(inv.created_at)}</div>
                  </div>
                  <button 
                    onClick={() => handleAcceptInvitation(inv.id)}
                    className="btn btn-sm btn-success bg-green-700 border-none text-white"
                  >
                    Aceptar
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col gap-6 relative">
      {/* Header & Tabs */}
      <div className="flex justify-between items-end border-b border-amber-900/30 pb-2">
        <div>
          <h1 className="text-3xl font-bold text-amber-100">{alliance.name}</h1>
          <p className="text-gray-400 text-sm">{alliance.description}</p>
        </div>
        <div className="tabs tabs-boxed bg-black/40">
          <a className={`tab ${activeTab === 'general' ? 'tab-active' : ''}`} onClick={() => setActiveTab('general')}>General</a>
          <a className={`tab ${activeTab === 'members' ? 'tab-active' : ''}`} onClick={() => setActiveTab('members')}>Miembros</a>
          <a className={`tab ${activeTab === 'diplomacy' ? 'tab-active' : ''}`} onClick={() => setActiveTab('diplomacy')}>Diplomacia</a>
          <a className={`tab ${activeTab === 'forum' ? 'tab-active' : ''}`} onClick={() => setActiveTab('forum')}>Foro</a>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'general' && (
          <div className="h-full flex gap-6">
            <div className="w-1/3 space-y-6">
              <div className="card bg-black/40 border border-amber-900/30 p-6">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div className="bg-black/20 p-3 rounded border border-gray-800">
                    <span className="text-gray-500 block">Miembros</span>
                    <span className="text-xl font-bold text-amber-200">{members.length}</span>
                  </div>
                  <div className="bg-black/20 p-3 rounded border border-gray-800">
                    <span className="text-gray-500 block">Diplomacia</span>
                    <span className="text-xl font-bold text-amber-200">{alliance.diplomacy}</span>
                  </div>
                </div>
                <button 
                  onClick={() => setShowInviteModal(true)}
                  className="btn btn-sm w-full mt-4 bg-amber-800 hover:bg-amber-700 border-none"
                >
                  Invitar Jugador
                </button>
                {canSendMassMessage && (
                  <button 
                    onClick={() => setShowMassMessageModal(true)}
                    className="btn btn-sm w-full mt-2 bg-blue-800 hover:bg-blue-700 border-none"
                  >
                    Mensaje Masivo
                  </button>
                )}
              </div>
            </div>

            <div className="flex-1 card bg-black/40 border border-amber-900/30 p-4 flex flex-col">
              <h3 className="text-lg font-bold text-amber-200 mb-4">Chat de Alianza</h3>
              <div className="flex-1 overflow-y-auto space-y-3 mb-4 custom-scrollbar pr-2">
                {chatMessages.map(msg => (
                  <div key={msg.id} className="bg-black/20 p-2 rounded border border-gray-800/50">
                    <div className="flex justify-between items-baseline mb-1">
                      <span className="font-bold text-amber-500 text-xs">{msg.username}</span>
                      <span className="text-[10px] text-gray-600">{formatDate(msg.created_at)}</span>
                    </div>
                    <p className="text-sm text-gray-300 break-words">{msg.message}</p>
                  </div>
                ))}
              </div>
              <form onSubmit={handleSendMessage} className="flex gap-2">
                <input
                  type="text"
                  className="input input-sm flex-1 bg-black/50 border-gray-700"
                  placeholder="Escribe un mensaje..."
                  value={chatMessage}
                  onChange={(e) => setChatMessage(e.target.value)}
                />
                <button type="submit" className="btn btn-sm btn-ghost text-amber-500">
                  ➤
                </button>
              </form>
            </div>
          </div>
        )}

        {activeTab === 'members' && (
          <div className="h-full card bg-black/40 border border-amber-900/30 p-6 overflow-hidden flex flex-col">
            <h3 className="text-xl font-bold text-amber-200 mb-4">Lista de Miembros</h3>
            <div className="overflow-y-auto flex-1">
              <table className="table w-full">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-800">
                    <th>Nombre</th>
                    <th>Rango</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map(member => (
                    <tr key={member.user_id} className="hover:bg-white/5">
                      <td className="font-bold text-gray-300">{member.username}</td>
                      <td>
                        {member.rank === 3 ? 'Líder' : member.rank === 2 ? 'General' : 'Miembro'}
                      </td>
                      <td>
                        {/* Actions placeholder */}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'diplomacy' && (
          <AllianceDiplomacy alliance={alliance} myRank={myRank} />
        )}

        {activeTab === 'forum' && (
          <AllianceForum alliance={alliance} />
        )}
      </div>

      {/* Modals */}
      {showInviteModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-amber-700 p-6 rounded-lg w-96">
            <h3 className="text-xl font-bold text-amber-500 mb-4">Invitar Jugador</h3>
            <div className="relative mb-4">
              <input
                type="text"
                placeholder="Buscar jugador..."
                className="input input-bordered w-full bg-black/50"
                value={inviteSearch}
                onChange={(e) => handleSearchInvite(e.target.value)}
              />
              {inviteResults.length > 0 && (
                <div className="absolute w-full bg-gray-800 border border-gray-600 mt-1 max-h-40 overflow-y-auto z-10">
                  {inviteResults.map(user => (
                    <div 
                      key={user.id}
                      className="p-2 hover:bg-gray-700 cursor-pointer flex justify-between"
                      onClick={() => handleInvite(user.id)}
                    >
                      <span>{user.username}</span>
                      <span className="text-xs text-green-500">Invitar</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <button 
              onClick={() => setShowInviteModal(false)}
              className="btn btn-sm btn-ghost w-full"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {showMassMessageModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="bg-gray-900 p-6 rounded-lg w-96 border border-amber-900">
            <h3 className="text-xl font-bold text-amber-500 mb-4">Enviar Mensaje Masivo</h3>
            <form onSubmit={handleSendMassMessage} className="space-y-4">
              <input
                type="text"
                placeholder="Asunto"
                className="input input-bordered w-full bg-black/50"
                value={massMessageSubject}
                onChange={(e) => setMassMessageSubject(e.target.value)}
              />
              <textarea
                placeholder="Mensaje"
                className="textarea textarea-bordered w-full bg-black/50 h-32"
                value={massMessageContent}
                onChange={(e) => setMassMessageContent(e.target.value)}
              />
              <div className="flex gap-2">
                <button type="submit" className="btn btn-primary flex-1">Enviar</button>
                <button 
                  type="button" 
                  onClick={() => setShowMassMessageModal(false)}
                  className="btn btn-ghost flex-1"
                >
                  Cancelar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default AllianceView;
