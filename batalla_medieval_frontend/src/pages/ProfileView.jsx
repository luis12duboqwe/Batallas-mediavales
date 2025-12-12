import { useState, useEffect } from 'react';
import { useUserStore } from '../store/userStore';
import { api } from '../api/axiosClient';
import ThemeSelector from '../components/ThemeSelector';

const ProfileView = () => {
  const { user, loadUser } = useUserStore();
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    email_notifications: false,
    language: 'en'
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (user) {
      setFormData({
        email: user.email || '',
        password: '',
        email_notifications: user.email_notifications || false,
        language: user.language || 'en'
      });
    }
  }, [user]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');
    
    const payload = {};
    if (formData.email !== user.email) payload.email = formData.email;
    if (formData.password) payload.password = formData.password;
    if (formData.email_notifications !== user.email_notifications) payload.email_notifications = formData.email_notifications;
    if (formData.language !== user.language) payload.language = formData.language;

    if (Object.keys(payload).length === 0) {
        setLoading(false);
        return;
    }

    try {
      await api.updateProfile(payload);
      await loadUser(); // Refresh user store
      setMessage('Perfil actualizado correctamente');
      setFormData(prev => ({ ...prev, password: '' }));
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error al actualizar perfil');
    } finally {
      setLoading(false);
    }
  };

  if (!user) return <div>Cargando...</div>;

  return (
    <div className="max-w-2xl mx-auto mt-10 pb-20">
      <div className="card bg-black/40 border border-amber-900/30 p-8">
        <h1 className="text-3xl font-bold text-amber-100 mb-6">Perfil de Usuario</h1>
        
        <div className="mb-6 p-4 bg-gray-900/50 rounded border border-gray-700">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-gray-500 text-sm">Usuario</label>
              <div className="text-xl font-bold text-amber-500">{user.username}</div>
            </div>
            <div>
              <label className="text-gray-500 text-sm">ID</label>
              <div className="text-xl text-gray-300">#{user.id}</div>
            </div>
            <div>
              <label className="text-gray-500 text-sm">Rubíes</label>
              <div className="text-xl text-red-400">💎 {user.rubies_balance}</div>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-gray-400 mb-1">Email</label>
            <input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              className="input input-bordered w-full bg-black/50 border-gray-700"
            />
          </div>

          <div>
            <label className="block text-gray-400 mb-1">Nueva Contraseña (dejar en blanco para no cambiar)</label>
            <input
              type="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              className="input input-bordered w-full bg-black/50 border-gray-700"
              placeholder="••••••••"
            />
          </div>

          <div>
            <label className="block text-gray-400 mb-1">Idioma</label>
            <select
              name="language"
              value={formData.language}
              onChange={handleChange}
              className="select select-bordered w-full bg-black/50 border-gray-700"
            >
              <option value="en">English</option>
              <option value="es">Español</option>
            </select>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              name="email_notifications"
              checked={formData.email_notifications}
              onChange={handleChange}
              className="checkbox checkbox-warning"
            />
            <label className="text-gray-300">Recibir notificaciones por email</label>
          </div>

          <div className="divider border-gray-800"></div>

          <ThemeSelector />

          <div className="divider border-gray-800"></div>

          <button 
            type="submit" 
            disabled={loading}
            className="btn bg-amber-600 hover:bg-amber-500 text-black w-full font-bold border-none"
          >
            {loading ? 'Guardando...' : 'Guardar Cambios'}
          </button>

          {message && (
            <div className={`p-3 rounded text-center ${message.includes('Error') ? 'bg-red-900/30 text-red-400' : 'bg-green-900/30 text-green-400'}`}>
              {message}
            </div>
          )}
        </form>
      </div>
    </div>
  );
};

export default ProfileView;
