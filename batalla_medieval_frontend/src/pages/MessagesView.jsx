import { useState, useEffect } from 'react';
import { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';
import { formatDate } from '../utils/format';

const MessagesView = () => {
  const { currentCity } = useCityStore();
  const [activeTab, setActiveTab] = useState('inbox');
  const [messages, setMessages] = useState([]);
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [loading, setLoading] = useState(false);

  // Compose state
  const [recipientSearch, setRecipientSearch] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [recipientId, setRecipientId] = useState(null);
  const [subject, setSubject] = useState('');
  const [content, setContent] = useState('');

  useEffect(() => {
    if (activeTab === 'inbox') loadInbox();
    if (activeTab === 'sent') loadSent();
  }, [activeTab]);

  const loadInbox = async () => {
    setLoading(true);
    try {
      const { data } = await api.getInbox();
      setMessages(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const loadSent = async () => {
    setLoading(true);
    try {
      const { data } = await api.getSent();
      setMessages(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (query) => {
    setRecipientSearch(query);
    if (query.length < 3) {
      setSearchResults([]);
      return;
    }
    try {
      const { data } = await api.searchPlayers(currentCity.world_id, query);
      setSearchResults(data);
    } catch (error) {
      console.error(error);
    }
  };

  const handleSend = async () => {
    if (!recipientId || !subject || !content) return;
    try {
      await api.sendMessage({
        receiver_id: recipientId,
        subject,
        content,
      });
      setActiveTab('sent');
      setRecipientId(null);
      setRecipientSearch('');
      setSubject('');
      setContent('');
    } catch (error) {
      console.error(error);
      alert('Error sending message');
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure?')) return;
    try {
      await api.deleteMessage(id);
      setMessages(messages.filter(m => m.id !== id));
      if (selectedMessage?.id === id) setSelectedMessage(null);
    } catch (error) {
      console.error(error);
    }
  };

  const handleRead = async (msg) => {
    setSelectedMessage(msg);
    if (!msg.read && activeTab === 'inbox') {
        try {
            await api.readMessage(msg.id);
            setMessages(messages.map(m => m.id === msg.id ? { ...m, read: true } : m));
        } catch (error) {
            console.error(error);
        }
    }
  };

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-yellow-500">Mensajería</h1>
        <div className="flex space-x-2">
          <button
            onClick={() => { setActiveTab('inbox'); setSelectedMessage(null); }}
            className={`px-4 py-2 rounded ${activeTab === 'inbox' ? 'bg-yellow-600 text-black' : 'bg-gray-700'}`}
          >
            Bandeja de Entrada
          </button>
          <button
            onClick={() => { setActiveTab('sent'); setSelectedMessage(null); }}
            className={`px-4 py-2 rounded ${activeTab === 'sent' ? 'bg-yellow-600 text-black' : 'bg-gray-700'}`}
          >
            Enviados
          </button>
          <button
            onClick={() => { setActiveTab('compose'); setSelectedMessage(null); }}
            className={`px-4 py-2 rounded ${activeTab === 'compose' ? 'bg-yellow-600 text-black' : 'bg-gray-700'}`}
          >
            Redactar
          </button>
        </div>
      </div>

      {activeTab === 'compose' ? (
        <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 max-w-2xl mx-auto">
          <h2 className="text-xl mb-4">Nuevo Mensaje</h2>
          <div className="space-y-4">
            <div className="relative">
              <label className="block text-sm text-gray-400 mb-1">Destinatario</label>
              <input
                type="text"
                value={recipientSearch}
                onChange={(e) => handleSearch(e.target.value)}
                className="w-full bg-gray-900 border border-gray-600 rounded p-2"
                placeholder="Buscar jugador..."
              />
              {searchResults.length > 0 && (
                <div className="absolute z-10 w-full bg-gray-900 border border-gray-600 mt-1 rounded max-h-40 overflow-y-auto">
                  {searchResults.map(user => (
                    <div
                      key={user.id}
                      onClick={() => {
                        setRecipientId(user.id);
                        setRecipientSearch(user.username);
                        setSearchResults([]);
                      }}
                      className="p-2 hover:bg-gray-700 cursor-pointer"
                    >
                      {user.username}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Asunto</label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="w-full bg-gray-900 border border-gray-600 rounded p-2"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Mensaje</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="w-full bg-gray-900 border border-gray-600 rounded p-2 h-32"
              />
            </div>
            <button
              onClick={handleSend}
              disabled={!recipientId || !subject || !content}
              className="w-full bg-yellow-600 text-black font-bold py-2 rounded hover:bg-yellow-500 disabled:opacity-50"
            >
              Enviar
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-1 bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
            <div className="p-2 bg-gray-900 border-b border-gray-700 font-bold">
              {activeTab === 'inbox' ? 'Recibidos' : 'Enviados'}
            </div>
            <div className="max-h-[600px] overflow-y-auto">
              {loading ? (
                <div className="p-4 text-center text-gray-500">Cargando...</div>
              ) : messages.length === 0 ? (
                <div className="p-4 text-center text-gray-500">No hay mensajes</div>
              ) : (
                messages.map(msg => (
                  <div
                    key={msg.id}
                    onClick={() => handleRead(msg)}
                    className={`p-3 border-b border-gray-700 cursor-pointer hover:bg-gray-700 ${selectedMessage?.id === msg.id ? 'bg-gray-700' : ''} ${!msg.read && activeTab === 'inbox' ? 'border-l-4 border-l-yellow-500' : ''}`}
                  >
                    <div className="font-bold truncate">{msg.subject}</div>
                    <div className="text-xs text-gray-400 flex justify-between">
                      <span>{activeTab === 'inbox' ? `De: ${msg.sender?.username || msg.sender_id}` : `Para: ${msg.receiver?.username || msg.receiver_id}`}</span>
                      <span>{formatDate(msg.timestamp)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
          <div className="md:col-span-2 bg-gray-800 rounded-lg border border-gray-700 p-6">
            {selectedMessage ? (
              <div>
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h2 className="text-2xl font-bold text-yellow-500">{selectedMessage.subject}</h2>
                    <p className="text-sm text-gray-400">
                      {formatDate(selectedMessage.timestamp)} - {activeTab === 'inbox' ? `De: ${selectedMessage.sender?.username || selectedMessage.sender_id}` : `Para: ${selectedMessage.receiver?.username || selectedMessage.receiver_id}`}
                    </p>
                  </div>
                  <button
                    onClick={() => handleDelete(selectedMessage.id)}
                    className="text-red-500 hover:text-red-400"
                  >
                    Eliminar
                  </button>
                </div>
                <div className="bg-gray-900 p-4 rounded border border-gray-700 min-h-[200px] whitespace-pre-wrap">
                  {selectedMessage.content}
                </div>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500">
                Selecciona un mensaje para leer
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default MessagesView;
