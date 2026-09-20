import { useEffect, useState } from 'react';
import axiosClient, { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';
import { useUserStore } from '../store/userStore';
import { formatDate } from '../utils/format';
import AllianceDiplomacy from '../components/AllianceDiplomacy';
import AllianceForum from '../components/AllianceForum';
import useModalAccessibility from '../hooks/useModalAccessibility';

const AllianceView = () => {
  const { user } = useUserStore();
  const { alliance, loadAlliance, currentCity } = useCityStore();
  const [loading, setLoading] = useState(false);
  const [createName, setCreateName] = useState('');
  const [activeTab, setActiveTab] = useState('general');

  const [chatMessage, setChatMessage] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  const [showMassMessageModal, setShowMassMessageModal] = useState(false);
  const [massMessageSubject, setMassMessageSubject] = useState('');
  const [massMessageContent, setMassMessageContent] = useState('');

  const [members, setMembers] = useState([]);
  const [memberActionId, setMemberActionId] = useState(null);
  const [invitations, setInvitations] = useState([]);
  const [inviteSearch, setInviteSearch] = useState('');
  const [inviteResults, setInviteResults] = useState([]);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const inviteDialogRef = useModalAccessibility(showInviteModal, () => setShowInviteModal(false));
  const massMessageDialogRef = useModalAccessibility(showMassMessageModal, () => setShowMassMessageModal(false));

  useEffect(() => {
    loadAlliance().catch(() => {});
  }, [loadAlliance]);

  useEffect(() => {
    if (alliance) {
      fetchChat();
      fetchMembers();
      const interval = setInterval(fetchChat, 5000);
      return () => clearInterval(interval);
    }
    if (currentCity) fetchInvitations();
    return undefined;
  }, [alliance, currentCity]);

  const fetchChat = () => {
    if (!alliance) return;
    axiosClient.get(`/alliance/${alliance.id}/chat`)
      .then((res) => setChatMessages(res.data))
      .catch(console.error);
  };

  const fetchMembers = () => {
    if (!alliance) return;
    axiosClient.get(`/alliance/${alliance.id}/members`)
      .then((res) => setMembers(res.data))
      .catch(console.error);
  };

  const fetchInvitations = () => {
    if (!currentCity) return;
    api.getInvitations(currentCity.world_id)
      .then((res) => setInvitations(res.data))
      .catch(console.error);
  };

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!createName.trim()) return;
    setLoading(true);
    try {
      await axiosClient.post('/alliance/create', {
        name: createName,
        description: 'Nueva alianza',
        world_id: currentCity.world_id,
      });
      await loadAlliance();
      setCreateName('');
    } catch (error) {
      alert(error.response?.data?.detail || 'Error al crear alianza');
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (event) => {
    event.preventDefault();
    if (!chatMessage.trim() || !alliance) return;
    try {
      await axiosClient.post(`/alliance/${alliance.id}/chat`, { message: chatMessage });
      setChatMessage('');
      fetchChat();
    } catch (error) {
      alert(error.response?.data?.detail || 'No se pudo enviar el mensaje');
    }
  };

  const handleAcceptInvitation = async (id) => {
    try {
      await axiosClient.acceptInvitation(id);
      await loadAlliance();
    } catch (error) {
      alert(error.response?.data?.detail || 'Error al aceptar invitación');
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

  const handleSendMassMessage = async (event) => {
    event.preventDefault();
    if (!massMessageSubject.trim() || !massMessageContent.trim()) return;
    try {
      await api.sendMassMessage(alliance.id, massMessageSubject, massMessageContent);
      setShowMassMessageModal(false);
      setMassMessageSubject('');
      setMassMessageContent('');
      alert('Mensaje enviado a todos los miembros.');
    } catch (error) {
      alert(error.response?.data?.detail || 'Error al enviar mensaje.');
    }
  };

  const handleMemberAction = async (member, action) => {
    if (!alliance || !member?.id) return;
    const labels = {
      promote: 'ascender',
      demote: 'degradar',
      kick: 'expulsar',
      transfer: 'transferir el liderazgo a',
    };
    if (!window.confirm(`¿Confirmas ${labels[action]} ${member.username}?`)) return;
    setMemberActionId(member.id);
    try {
      if (action === 'promote') {
        await axiosClient.post(`/alliance/${alliance.id}/members/${member.id}/promote`);
      } else if (action === 'demote') {
        await axiosClient.post(`/alliance/${alliance.id}/members/${member.id}/demote`);
      } else if (action === 'kick') {
        await axiosClient.delete(`/alliance/${alliance.id}/members/${member.id}`);
      } else if (action === 'transfer') {
        await axiosClient.post(`/alliance/${alliance.id}/leadership/transfer`, {
          target_member_id: member.id,
        });
        await loadAlliance();
      }
      await fetchMembers();
    } catch (error) {
      alert(error.response?.data?.detail || 'No se pudo completar la acción');
    } finally {
      setMemberActionId(null);
    }
  };

  const myRank = Number(members.find((member) => Number(member.user_id) === Number(user?.id))?.rank || 0);
  const canSendMassMessage = myRank >= 2;
  const tabs = [
    ['general', 'General'],
    ['members', 'Miembros'],
    ['diplomacy', 'Diplomacia'],
    ['forum', 'Foro'],
  ];

  if (!alliance) {
    return (
      <div className="max-w-4xl mx-auto mt-10 grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="card bg-black/40 border border-amber-900/30 p-8 text-center">
          <h1 className="text-3xl font-bold text-amber-100 mb-4">Sin Alianza</h1>
          <p className="text-gray-400 mb-8">
            No perteneces a ninguna alianza. Puedes crear una nueva y reclutar a otros señores.
          </p>
          <div className="bg-gray-900/50 p-6 rounded-xl border border-gray-800 max-w-md mx-auto">
            <h2 className="text-lg font-bold text-amber-200 mb-4">Fundar una Alianza</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <label htmlFor="alliance-create-name" className="sr-only">Nombre de la alianza</label>
              <input
                id="alliance-create-name"
                type="text"
                placeholder="Nombre de la alianza"
                className="input input-bordered w-full bg-black/50 border-gray-700"
                value={createName}
                onChange={(event) => setCreateName(event.target.value)}
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

        <section className="card bg-black/40 border border-amber-900/30 p-8" aria-labelledby="alliance-invitations-title">
          <h2 id="alliance-invitations-title" className="text-2xl font-bold text-amber-100 mb-4">Invitaciones Pendientes</h2>
          {invitations.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No tienes invitaciones pendientes.</p>
          ) : (
            <div className="space-y-4">
              {invitations.map((invitation) => (
                <div key={invitation.id} className="bg-gray-900/50 p-4 rounded border border-gray-700 flex justify-between items-center gap-3">
                  <div>
                    <div className="font-bold text-amber-500">Alianza #{invitation.alliance_id}</div>
                    <div className="text-xs text-gray-400">{formatDate(invitation.created_at)}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleAcceptInvitation(invitation.id)}
                    className="btn btn-sm btn-success bg-green-700 border-none text-white"
                  >
                    Aceptar
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-8rem)] flex flex-col gap-6 relative" data-testid="alliance-community-view">
      <div className="flex flex-col gap-3 border-b border-amber-900/30 pb-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-amber-100">{alliance.name}</h1>
          <p className="text-gray-400 text-sm">{alliance.description}</p>
        </div>
        <div className="tabs tabs-boxed bg-black/40 flex-wrap" role="tablist" aria-label="Secciones de alianza">
          {tabs.map(([tab, label]) => (
            <button
              type="button"
              key={tab}
              role="tab"
              aria-selected={activeTab === tab}
              aria-controls={`alliance-panel-${tab}`}
              id={`alliance-tab-${tab}`}
              className={`tab ${activeTab === tab ? 'tab-active' : ''}`}
              onClick={() => setActiveTab(tab)}
              data-testid={tab === 'members' ? 'alliance-members-tab' : tab === 'forum' ? 'alliance-forum-tab' : undefined}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {activeTab === 'general' && (
          <div id="alliance-panel-general" role="tabpanel" aria-labelledby="alliance-tab-general" className="h-full flex flex-col gap-6 lg:flex-row">
            <div className="w-full space-y-6 lg:w-1/3">
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
                {myRank >= 2 && (
                  <button
                    type="button"
                    onClick={() => setShowInviteModal(true)}
                    className="btn btn-sm w-full mt-4 bg-amber-800 hover:bg-amber-700 border-none"
                  >
                    Invitar Jugador
                  </button>
                )}
                {canSendMassMessage && (
                  <button
                    type="button"
                    onClick={() => setShowMassMessageModal(true)}
                    className="btn btn-sm w-full mt-2 bg-blue-800 hover:bg-blue-700 border-none"
                  >
                    Mensaje Masivo
                  </button>
                )}
              </div>
            </div>

            <section className="flex-1 card bg-black/40 border border-amber-900/30 p-4 flex flex-col min-h-[24rem]" aria-labelledby="alliance-chat-title">
              <h2 id="alliance-chat-title" className="text-lg font-bold text-amber-200 mb-4">Chat de Alianza</h2>
              <div className="flex-1 overflow-y-auto space-y-3 mb-4 custom-scrollbar pr-2" data-testid="alliance-chat-history" aria-live="polite">
                {chatMessages.map((message) => (
                  <div key={message.id} className="bg-black/20 p-2 rounded border border-gray-800/50">
                    <div className="flex justify-between items-baseline mb-1">
                      <span className="font-bold text-amber-500 text-xs">{message.username}</span>
                      <span className="text-[10px] text-gray-600">{formatDate(message.created_at)}</span>
                    </div>
                    <p className="text-sm text-gray-300 break-words">{message.message}</p>
                  </div>
                ))}
              </div>
              <form onSubmit={handleSendMessage} className="flex gap-2">
                <label htmlFor="alliance-chat-input" className="sr-only">Mensaje para el chat de alianza</label>
                <input
                  id="alliance-chat-input"
                  type="text"
                  className="input input-sm flex-1 bg-black/50 border-gray-700"
                  placeholder="Escribe un mensaje..."
                  value={chatMessage}
                  onChange={(event) => setChatMessage(event.target.value)}
                  maxLength={1000}
                  data-testid="alliance-chat-input"
                />
                <button type="submit" aria-label="Enviar mensaje al chat" className="btn btn-sm btn-ghost text-amber-500" data-testid="alliance-chat-send">➤</button>
              </form>
            </section>
          </div>
        )}

        {activeTab === 'members' && (
          <section id="alliance-panel-members" role="tabpanel" aria-labelledby="alliance-tab-members" className="h-full card bg-black/40 border border-amber-900/30 p-6 overflow-hidden flex flex-col">
            <h2 className="text-xl font-bold text-amber-200 mb-4">Lista de Miembros</h2>
            <div className="overflow-auto flex-1">
              <table className="table w-full">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-800">
                    <th scope="col">Nombre</th>
                    <th scope="col">Rango</th>
                    <th scope="col">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((member) => {
                    const targetRank = Number(member.rank || 0);
                    const isSelf = Number(member.user_id) === Number(user?.id);
                    const canManageTarget = myRank >= 2 && myRank > targetRank && !isSelf;
                    const isBusy = memberActionId === member.id;
                    return (
                      <tr key={member.id} className="hover:bg-white/5" data-testid={`alliance-member-${member.user_id}`}>
                        <th scope="row" className="font-bold text-gray-300 text-left">{member.username}</th>
                        <td>{targetRank === 3 ? 'Líder' : targetRank === 2 ? 'General' : 'Miembro'}</td>
                        <td>
                          <div className="flex flex-wrap gap-2">
                            {canManageTarget && targetRank === 1 && (
                              <button type="button" className="btn btn-xs btn-outline" disabled={isBusy} onClick={() => handleMemberAction(member, 'promote')} data-testid={`promote-member-${member.user_id}`}>Ascender</button>
                            )}
                            {canManageTarget && targetRank > 1 && (
                              <button type="button" className="btn btn-xs btn-outline" disabled={isBusy} onClick={() => handleMemberAction(member, 'demote')} data-testid={`demote-member-${member.user_id}`}>Degradar</button>
                            )}
                            {canManageTarget && (
                              <button type="button" className="btn btn-xs btn-error btn-outline" disabled={isBusy} onClick={() => handleMemberAction(member, 'kick')} data-testid={`kick-member-${member.user_id}`}>Expulsar</button>
                            )}
                            {myRank === 3 && !isSelf && (
                              <button type="button" className="btn btn-xs btn-warning btn-outline" disabled={isBusy} onClick={() => handleMemberAction(member, 'transfer')} data-testid={`transfer-leadership-${member.user_id}`}>Hacer líder</button>
                            )}
                            {!canManageTarget && !(myRank === 3 && !isSelf) && <span className="text-xs text-gray-600">Sin acciones disponibles</span>}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {activeTab === 'diplomacy' && (
          <div id="alliance-panel-diplomacy" role="tabpanel" aria-labelledby="alliance-tab-diplomacy">
            <AllianceDiplomacy alliance={alliance} myRank={myRank} />
          </div>
        )}

        {activeTab === 'forum' && (
          <div id="alliance-panel-forum" role="tabpanel" aria-labelledby="alliance-tab-forum">
            <AllianceForum alliance={alliance} />
          </div>
        )}
      </div>

      {showInviteModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div
            ref={inviteDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="alliance-invite-dialog-title"
            tabIndex={-1}
            className="bg-gray-900 border border-amber-700 p-6 rounded-lg w-full max-w-sm"
          >
            <h2 id="alliance-invite-dialog-title" className="text-xl font-bold text-amber-500 mb-4">Invitar Jugador</h2>
            <div className="relative mb-4">
              <label htmlFor="alliance-invite-search" className="sr-only">Buscar jugador para invitar</label>
              <input
                id="alliance-invite-search"
                type="text"
                placeholder="Buscar jugador..."
                className="input input-bordered w-full bg-black/50"
                value={inviteSearch}
                onChange={(event) => handleSearchInvite(event.target.value)}
                autoComplete="off"
                aria-expanded={inviteResults.length > 0}
              />
              {inviteResults.length > 0 && (
                <div className="absolute w-full bg-gray-800 border border-gray-600 mt-1 max-h-40 overflow-y-auto z-10" aria-label="Jugadores encontrados">
                  {inviteResults.map((inviteUser) => (
                    <button
                      type="button"
                      key={inviteUser.id}
                      className="p-2 hover:bg-gray-700 cursor-pointer flex justify-between w-full text-left"
                      onClick={() => handleInvite(inviteUser.id)}
                    >
                      <span>{inviteUser.username}</span>
                      <span className="text-xs text-green-500">Invitar</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button type="button" onClick={() => setShowInviteModal(false)} className="btn btn-sm btn-ghost w-full">Cancelar</button>
          </div>
        </div>
      )}

      {showMassMessageModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div
            ref={massMessageDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="alliance-mass-message-title"
            tabIndex={-1}
            className="bg-gray-900 p-6 rounded-lg w-full max-w-sm border border-amber-900"
          >
            <h2 id="alliance-mass-message-title" className="text-xl font-bold text-amber-500 mb-4">Enviar Mensaje Masivo</h2>
            <form onSubmit={handleSendMassMessage} className="space-y-4">
              <div>
                <label htmlFor="alliance-mass-subject" className="block text-sm text-gray-300 mb-1">Asunto</label>
                <input
                  id="alliance-mass-subject"
                  type="text"
                  className="input input-bordered w-full bg-black/50"
                  value={massMessageSubject}
                  onChange={(event) => setMassMessageSubject(event.target.value)}
                />
              </div>
              <div>
                <label htmlFor="alliance-mass-content" className="block text-sm text-gray-300 mb-1">Mensaje</label>
                <textarea
                  id="alliance-mass-content"
                  className="textarea textarea-bordered w-full bg-black/50 h-32"
                  value={massMessageContent}
                  onChange={(event) => setMassMessageContent(event.target.value)}
                />
              </div>
              <div className="flex gap-2">
                <button type="submit" className="btn btn-primary flex-1">Enviar</button>
                <button type="button" onClick={() => setShowMassMessageModal(false)} className="btn btn-ghost flex-1">Cancelar</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default AllianceView;
