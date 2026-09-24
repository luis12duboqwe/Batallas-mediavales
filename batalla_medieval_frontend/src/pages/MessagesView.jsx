import { useState, useEffect } from 'react';
import { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';
import { formatDate } from '../utils/format';
import { handleTablistKeyDown } from '../utils/accessibility';

const MESSAGE_TABS = [
  ['inbox', 'Bandeja de Entrada'],
  ['sent', 'Enviados'],
  ['compose', 'Redactar'],
];
const MESSAGE_TAB_KEYS = MESSAGE_TABS.map(([tab]) => tab);

const MessagesView = () => {
  const { currentCity } = useCityStore();
  const [activeTab, setActiveTab] = useState('inbox');
  const [messages, setMessages] = useState([]);
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [loading, setLoading] = useState(false);
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
    } finally { setLoading(false); }
  };

  const loadSent = async () => {
    setLoading(true);
    try {
      const { data } = await api.getSent();
      setMessages(data);
    } catch (error) {
      console.error(error);
    } finally { setLoading(false); }
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
      await api.sendMessage({ receiver_id: recipientId, subject, content });
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
      setMessages(messages.filter((message) => message.id !== id));
      if (selectedMessage?.id === id) setSelectedMessage(null);
    } catch (error) { console.error(error); }
  };

  const handleRead = async (message) => {
    setSelectedMessage(message);
    if (!message.read && activeTab === 'inbox') {
      try {
        await api.readMessage(message.id);
        setMessages(messages.map((entry) => entry.id === message.id ? { ...entry, read: true } : entry));
      } catch (error) { console.error(error); }
    }
  };

  const selectTab = (tab) => {
    setActiveTab(tab);
    setSelectedMessage(null);
  };

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <h1 className="text-3xl font-bold text-yellow-500">Mensajería</h1>
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Carpetas de mensajes">
          {MESSAGE_TABS.map(([tab, label]) => (
            <button
              type="button"
              key={tab}
              id={`messages-tab-${tab}`}
              role="tab"
              tabIndex={activeTab === tab ? 0 : -1}
              aria-selected={activeTab === tab}
              aria-controls="messages-panel"
              onClick={() => selectTab(tab)}
              onKeyDown={(event) => handleTablistKeyDown(event, MESSAGE_TAB_KEYS, tab, selectTab, 'messages-tab-')}
              className={`px-4 py-2 rounded ${activeTab === tab ? 'bg-yellow-600 text-black' : 'bg-gray-700'}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div id="messages-panel" role="tabpanel" aria-labelledby={`messages-tab-${activeTab}`} className="focus:outline-none">
        {activeTab === 'compose' ? (
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 max-w-2xl mx-auto">
            <h2 className="text-xl mb-4">Nuevo Mensaje</h2>
            <div className="space-y-4">
              <div className="relative">
                <label htmlFor="message-recipient" className="block text-sm text-gray-400 mb-1">Destinatario</label>
                <input
                  id="message-recipient"
                  type="text"
                  value={recipientSearch}
                  onChange={(event) => handleSearch(event.target.value)}
                  className="w-full bg-gray-900 border border-gray-600 rounded p-2"
                  placeholder="Buscar jugador..."
                  autoComplete="off"
                  aria-expanded={searchResults.length > 0}
                />
                {searchResults.length > 0 && (
                  <div className="absolute z-10 w-full bg-gray-900 border border-gray-600 mt-1 rounded max-h-40 overflow-y-auto" aria-label="Resultados de jugadores">
                    {searchResults.map((searchUser) => (
                      <button
                        type="button"
                        key={searchUser.id}
                        onClick={() => {
                          setRecipientId(searchUser.id);
                          setRecipientSearch(searchUser.username);
                          setSearchResults([]);
                        }}
                        className="p-2 hover:bg-gray-700 cursor-pointer flex justify-between w-full text-left"
                      >
                        {searchUser.username}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <label htmlFor="message-subject" className="block text-sm text-gray-400 mb-1">Asunto</label>
                <input id="message-subject" type="text" value={subject} onChange={(event) => setSubject(event.target.value)} className="w-full bg-gray-900 border border-gray-600 rounded p-2" />
              </div>
              <div>
                <label htmlFor="message-content" className="block text-sm text-gray-400 mb-1">Mensaje</label>
                <textarea id="message-content" value={content} onChange={(event) => setContent(event.target.value)} className="w-full bg-gray-900 border border-gray-600 rounded p-2 h-32" />
              </div>
              <button type="button" onClick={handleSend} disabled={!recipientId || !subject || !content} className="w-full bg-yellow-600 text-black font-bold py-2 rounded hover:bg-yellow-500 disabled:opacity-50">Enviar</button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <section className="md:col-span-1 bg-gray-800 rounded-lg border border-gray-700 overflow-hidden" aria-label={activeTab === 'inbox' ? 'Mensajes recibidos' : 'Mensajes enviados'}>
              <div className="p-2 bg-gray-900 border-b border-gray-700 font-bold">{activeTab === 'inbox' ? 'Recibidos' : 'Enviados'}</div>
              <div className="max-h-[600px] overflow-y-auto">
                {loading ? (
                  <div className="p-4 text-center text-gray-500" role="status">Cargando...</div>
                ) : messages.length === 0 ? (
                  <div className="p-4 text-center text-gray-500">No hay mensajes</div>
                ) : (
                  messages.map((message) => (
                    <button
                      type="button"
                      key={message.id}
                      onClick={() => handleRead(message)}
                      aria-pressed={selectedMessage?.id === message.id}
                      className={`p-3 border-b border-gray-700 cursor-pointer hover:bg-gray-700 w-full text-left ${selectedMessage?.id === message.id ? 'bg-gray-700' : ''} ${!message.read && activeTab === 'inbox' ? 'border-l-4 border-l-yellow-500' : ''}`}
                    >
                      <span className="font-bold truncate block">{message.subject}</span>
                      <span className="text-xs text-gray-400 flex justify-between gap-2">
                        <span>{activeTab === 'inbox' ? `De: ${message.sender?.username || message.sender_id}` : `Para: ${message.receiver?.username || message.receiver_id}`}</span>
                        <span>{formatDate(message.timestamp)}</span>
                      </span>
                    </button>
                  ))
                )}
              </div>
            </section>
            <section className="md:col-span-2 bg-gray-800 rounded-lg border border-gray-700 p-6" aria-label="Contenido del mensaje">
              {selectedMessage ? (
                <article>
                  <div className="flex justify-between items-start mb-4 gap-3">
                    <div>
                      <h2 className="text-2xl font-bold text-yellow-500">{selectedMessage.subject}</h2>
                      <p className="text-sm text-gray-400">{formatDate(selectedMessage.timestamp)} - {activeTab === 'inbox' ? `De: ${selectedMessage.sender?.username || selectedMessage.sender_id}` : `Para: ${selectedMessage.receiver?.username || selectedMessage.receiver_id}`}</p>
                    </div>
                    <button type="button" onClick={() => handleDelete(selectedMessage.id)} className="text-red-500 hover:text-red-400">Eliminar</button>
                  </div>
                  <div className="bg-gray-900 p-4 rounded border border-gray-700 min-h-[200px] whitespace-pre-wrap">{selectedMessage.content}</div>
                </article>
              ) : (
                <div className="h-full flex items-center justify-center text-gray-500">Selecciona un mensaje para leer</div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
};

export default MessagesView;
