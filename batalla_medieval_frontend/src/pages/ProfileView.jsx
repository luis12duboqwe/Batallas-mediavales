import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '../store/userStore';
import { api } from '../api/axiosClient';
import ThemeSelector from '../components/ThemeSelector';

const ProfileView = () => {
  const { t, i18n } = useTranslation();
  const { user, loadUser } = useUserStore();
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    email_notifications: false,
    language: 'en'
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageIsError, setMessageIsError] = useState(false);

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
    setMessageIsError(false);

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
      const refreshedUser = await loadUser();
      if (refreshedUser?.language) {
        await i18n.changeLanguage(refreshedUser.language);
      }
      setMessage(t('profile.updated'));
      setFormData(prev => ({ ...prev, password: '' }));
    } catch (error) {
      setMessageIsError(true);
      setMessage(error.response?.data?.detail || t('profile.update_error'));
    } finally {
      setLoading(false);
    }
  };

  if (!user) return <div role="status">{t('common.loading')}</div>;

  return (
    <div className="max-w-2xl mx-auto mt-4 sm:mt-10 pb-20">
      <div className="card bg-black/40 border border-amber-900/30 p-4 sm:p-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-amber-100 mb-6">{t('profile.title')}</h1>

        <div className="mb-6 p-4 bg-gray-900/50 rounded border border-gray-700">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <div className="text-gray-500 text-sm">{t('profile.username')}</div>
              <div className="text-xl font-bold text-amber-500">{user.username}</div>
            </div>
            <div>
              <div className="text-gray-500 text-sm">{t('profile.id')}</div>
              <div className="text-xl text-gray-300">#{user.id}</div>
            </div>
            <div>
              <div className="text-gray-500 text-sm">{t('profile.rubies')}</div>
              <div className="text-xl text-red-400">💎 {user.rubies_balance}</div>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="profile-email" className="block text-gray-400 mb-1">{t('profile.email')}</label>
            <input
              id="profile-email"
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              className="input input-bordered w-full bg-black/50 border-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
            />
          </div>

          <div>
            <label htmlFor="profile-password" className="block text-gray-400 mb-1">{t('profile.new_password')}</label>
            <input
              id="profile-password"
              type="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              className="input input-bordered w-full bg-black/50 border-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
              placeholder="••••••••"
            />
          </div>

          <div>
            <label htmlFor="profile-language" className="block text-gray-400 mb-1">{t('profile.language')}</label>
            <select
              id="profile-language"
              name="language"
              value={formData.language}
              onChange={handleChange}
              className="select select-bordered w-full bg-black/50 border-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
            >
              <option value="en">English</option>
              <option value="es">Español</option>
            </select>
          </div>

          <div className="flex items-center gap-3">
            <input
              id="profile-email-notifications"
              type="checkbox"
              name="email_notifications"
              checked={formData.email_notifications}
              onChange={handleChange}
              className="checkbox checkbox-warning focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
            />
            <label htmlFor="profile-email-notifications" className="text-gray-300">{t('profile.email_notifications')}</label>
          </div>

          <div className="divider border-gray-800"></div>

          <ThemeSelector />

          <div className="divider border-gray-800"></div>

          <button
            type="submit"
            disabled={loading}
            className="btn bg-amber-600 hover:bg-amber-500 text-black w-full font-bold border-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-200"
          >
            {loading ? t('profile.saving') : t('profile.save_changes')}
          </button>

          {message && (
            <div
              role={messageIsError ? 'alert' : 'status'}
              aria-live="polite"
              className={`p-3 rounded text-center ${messageIsError ? 'bg-red-900/30 text-red-400' : 'bg-green-900/30 text-green-400'}`}
            >
              {message}
            </div>
          )}
        </form>
      </div>
    </div>
  );
};

export default ProfileView;
