import { useEffect, useMemo, useState } from 'react';
import axiosClient, { api } from '../api/axiosClient';
import { useUserStore } from '../store/userStore';
import { formatDate } from '../utils/format';

const TITLE_MAX = 160;
const POST_MAX = 5000;

const AllianceForum = ({ alliance }) => {
  const user = useUserStore((state) => state.user);
  const [threads, setThreads] = useState([]);
  const [members, setMembers] = useState([]);
  const [activeThread, setActiveThread] = useState(null);
  const [view, setView] = useState('list'); // 'list', 'create', 'detail'
  const [busyModeration, setBusyModeration] = useState(false);

  // Create form
  const [newTitle, setNewTitle] = useState('');
  const [newContent, setNewContent] = useState('');

  // Reply form
  const [replyContent, setReplyContent] = useState('');

  const myRank = useMemo(() => {
    const membership = members.find((entry) => Number(entry.user_id) === Number(user?.id));
    return Number(membership?.rank || 0);
  }, [members, user?.id]);
  const canModerate = myRank >= 2;

  useEffect(() => {
    let cancelled = false;
    const loadMembers = async () => {
      try {
        const response = await axiosClient.get(`/alliance/${alliance.id}/members`);
        if (!cancelled) setMembers(response.data || []);
      } catch (error) {
        if (!cancelled) setMembers([]);
        console.error(error);
      }
    };
    loadMembers();
    return () => {
      cancelled = true;
    };
  }, [alliance.id]);

  useEffect(() => {
    if (view === 'list') fetchThreads();
  }, [view, alliance.id]);

  const fetchThreads = async () => {
    try {
      const res = await api.getForumThreads(alliance.id);
      setThreads(res.data);
    } catch (error) {
      console.error(error);
    }
  };

  const handleCreateThread = async (e) => {
    e.preventDefault();
    try {
      await api.createForumThread(alliance.id, newTitle.trim(), newContent.trim());
      setNewTitle('');
      setNewContent('');
      setView('list');
    } catch (error) {
      alert(error.response?.data?.detail || 'Error al crear hilo');
    }
  };

  const handleOpenThread = async (threadId) => {
    try {
      const res = await api.getForumThread(threadId);
      setActiveThread(res.data);
      setView('detail');
    } catch (error) {
      console.error(error);
    }
  };

  const handleReply = async (e) => {
    e.preventDefault();
    if (!activeThread) return;
    try {
      await api.replyForumThread(activeThread.id, replyContent.trim());
      setReplyContent('');
      await handleOpenThread(activeThread.id);
    } catch (error) {
      alert(error.response?.data?.detail || 'Error al responder');
    }
  };

  const handleModeration = async (changes) => {
    if (!activeThread || !canModerate || busyModeration) return;
    setBusyModeration(true);
    try {
      const response = await axiosClient.patch(
        `/forum/threads/${activeThread.id}/moderation`,
        changes,
      );
      setActiveThread(response.data);
    } catch (error) {
      alert(error.response?.data?.detail || 'No se pudo moderar el hilo');
    } finally {
      setBusyModeration(false);
    }
  };

  if (view === 'create') {
    return (
      <div className="card bg-black/40 border border-amber-900/30 p-6" data-testid="alliance-forum-create">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-xl font-bold text-amber-200">Nuevo Hilo</h3>
          <button onClick={() => setView('list')} className="btn btn-sm btn-ghost">Volver</button>
        </div>
        <form onSubmit={handleCreateThread} className="space-y-4">
          <input
            type="text"
            placeholder="Título"
            className="input input-bordered w-full bg-black/50"
            value={newTitle}
            onChange={e => setNewTitle(e.target.value)}
            maxLength={TITLE_MAX}
            data-testid="forum-thread-title"
            required
          />
          <div className="text-xs text-gray-500 text-right">{newTitle.length}/{TITLE_MAX}</div>
          <textarea
            placeholder="Contenido"
            className="textarea textarea-bordered w-full h-40 bg-black/50"
            value={newContent}
            onChange={e => setNewContent(e.target.value)}
            maxLength={POST_MAX}
            data-testid="forum-thread-content"
            required
          />
          <div className="text-xs text-gray-500 text-right">{newContent.length}/{POST_MAX}</div>
          <button type="submit" className="btn btn-primary" data-testid="forum-thread-submit">Publicar</button>
        </form>
      </div>
    );
  }

  if (view === 'detail' && activeThread) {
    return (
      <div className="space-y-4" data-testid={`forum-thread-${activeThread.id}`}>
        <button onClick={() => setView('list')} className="btn btn-sm btn-ghost mb-2">← Volver al Foro</button>

        <div className="card bg-black/40 border border-amber-900/30 p-6">
          <div className="flex flex-wrap justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold text-amber-100 mb-2">{activeThread.title}</h1>
              <div className="text-xs text-gray-500 mb-4">
                Por {activeThread.author_name} • {formatDate(activeThread.created_at)}
              </div>
            </div>
            <div className="flex items-start gap-2" data-testid="forum-thread-status">
              {activeThread.is_pinned && <span className="badge badge-warning">📌 Fijado</span>}
              {activeThread.is_locked && <span className="badge badge-error">🔒 Cerrado</span>}
            </div>
          </div>

          {canModerate && (
            <div className="flex flex-wrap gap-2 mb-5" data-testid="forum-moderation-controls">
              <button
                type="button"
                className="btn btn-xs btn-outline"
                disabled={busyModeration}
                onClick={() => handleModeration({ is_pinned: !activeThread.is_pinned })}
                data-testid="forum-toggle-pin"
              >
                {activeThread.is_pinned ? 'Desfijar' : 'Fijar'}
              </button>
              <button
                type="button"
                className="btn btn-xs btn-outline"
                disabled={busyModeration}
                onClick={() => handleModeration({ is_locked: !activeThread.is_locked })}
                data-testid="forum-toggle-lock"
              >
                {activeThread.is_locked ? 'Reabrir' : 'Cerrar'}
              </button>
            </div>
          )}

          <div className="space-y-6">
            {activeThread.posts.map((post, idx) => (
              <div key={post.id} className={`p-4 rounded ${idx === 0 ? 'bg-amber-900/20 border border-amber-900/30' : 'bg-black/30 border border-gray-800'}`}>
                <div className="flex justify-between items-baseline mb-2">
                  <span className="font-bold text-amber-500">{post.author_name}</span>
                  <span className="text-xs text-gray-600">{formatDate(post.created_at)}</span>
                </div>
                <div className="text-gray-300 whitespace-pre-wrap">{post.content}</div>
              </div>
            ))}
          </div>
        </div>

        {!activeThread.is_locked && (
          <div className="card bg-black/40 border border-amber-900/30 p-4">
            <form onSubmit={handleReply} className="flex gap-2">
              <textarea
                placeholder="Escribe una respuesta..."
                className="textarea textarea-bordered flex-1 bg-black/50"
                value={replyContent}
                onChange={e => setReplyContent(e.target.value)}
                maxLength={POST_MAX}
                data-testid="forum-reply-content"
                required
              />
              <button type="submit" className="btn btn-primary self-end" data-testid="forum-reply-submit">Responder</button>
            </form>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="card bg-black/40 border border-amber-900/30 p-6" data-testid="alliance-forum">
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-xl font-bold text-amber-200">Foro de la Alianza</h3>
        <button onClick={() => setView('create')} className="btn btn-sm btn-primary" data-testid="forum-new-thread">Nuevo Hilo</button>
      </div>

      {threads.length === 0 ? (
        <p className="text-gray-500 text-center py-8">No hay hilos de discusión.</p>
      ) : (
        <div className="space-y-2">
          {threads.map(thread => (
            <div
              key={thread.id}
              className="p-4 bg-black/30 border border-gray-800 hover:bg-white/5 cursor-pointer rounded flex justify-between items-center"
              onClick={() => handleOpenThread(thread.id)}
              data-testid={`forum-thread-row-${thread.id}`}
            >
              <div>
                <div className="flex items-center gap-2">
                  {thread.is_pinned && <span className="text-yellow-500">📌</span>}
                  {thread.is_locked && <span className="text-red-500">🔒</span>}
                  <span className="font-bold text-gray-200">{thread.title}</span>
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Por {thread.author_name} • Última actividad: {formatDate(thread.updated_at)}
                </div>
              </div>
              <div className="text-sm text-gray-400">
                {thread.reply_count} respuestas
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AllianceForum;
