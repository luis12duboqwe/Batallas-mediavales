import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '../store/userStore';
import { api } from '../api/axiosClient';
import GameIcon from '../components/GameIcon';

const ProfileView = () => {
  const { t } = useTranslation();
  const user = useUserStore((state) => state.user);
  const loadUser = useUserStore((state) => state.loadUser);
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    email_notifications: false,
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageIsError, setMessageIsError] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState('');
  const [privacyKind, setPrivacyKind] = useState('erasure');
  const [privacyDetails, setPrivacyDetails] = useState('');
  const [privacyRequests, setPrivacyRequests] = useState([]);
  const [privacyLoading, setPrivacyLoading] = useState(false);
  const [privacySubmitting, setPrivacySubmitting] = useState(false);
  const [privacyError, setPrivacyError] = useState('');
  const [privacyNotice, setPrivacyNotice] = useState('');
  const privacyEpoch = useRef(0);

  useEffect(() => {
    if (user) {
      setFormData({
        email: user.email || '',
        password: '',
        email_notifications: user.email_notifications || false,
      });
    }
  }, [user]);

  const fetchPrivacyRequests = async (keepError = false) => {
    const epoch = ++privacyEpoch.current;
    setPrivacyLoading(true);
    if (!keepError) setPrivacyError('');
    try {
      const { data } = await api.getPrivacyRequests();
      if (epoch === privacyEpoch.current) {
        setPrivacyRequests(Array.isArray(data) ? data : []);
      }
    } catch {
      if (epoch === privacyEpoch.current) {
        setPrivacyError((previous) => keepError && previous ? previous : 'No se pudo consultar el estado de las solicitudes.');
      }
    } finally {
      if (epoch === privacyEpoch.current) setPrivacyLoading(false);
    }
  };

  useEffect(() => {
    setPrivacySubmitting(false);
    setPrivacyDetails('');
    setPrivacyNotice('');
    setPrivacyError('');
    // Never render the previous account's request history on a session switch.
    setPrivacyRequests([]);
    if (user?.id) {
      fetchPrivacyRequests();
    } else {
      setPrivacyLoading(false);
    }
    return () => { privacyEpoch.current += 1; };
    // A session change invalidates any outstanding privacy list response.
  }, [user?.id]);

  const handlePrivacySubmit = async (event) => {
    event.preventDefault();
    if (privacySubmitting) return;
    const epoch = ++privacyEpoch.current;
    setPrivacyLoading(false);
    setPrivacySubmitting(true);
    setPrivacyError('');
    setPrivacyNotice('');
    try {
      const { data } = await api.createPrivacyRequest({
        kind: privacyKind,
        details: privacyDetails,
      });
      if (epoch === privacyEpoch.current) {
        setPrivacyDetails('');
        setPrivacyRequests((previous) => [
          data, ...previous.filter((item) => item.id !== data.id),
        ]);
        setPrivacyNotice('Solicitud registrada para revisión manual. Tu cuenta no se ha eliminado ni modificado.');
      }
    } catch {
      if (epoch === privacyEpoch.current) {
        setPrivacyError('No se pudo registrar la solicitud. Inténtalo de nuevo.');
      }
    } finally {
      if (epoch === privacyEpoch.current) {
        setPrivacySubmitting(false);
        // A submit can invalidate a slower initial GET. Always re-read the
        // complete history, even if the POST failed; preserve its error.
        void fetchPrivacyRequests(true);
      }
    }
  };

  const privacyLabels = {
    erasure: 'Eliminación de cuenta',
    rectification: 'Corrección de datos',
    retention: 'Retención de datos',
    other: 'Consulta de privacidad',
  };
  const privacyStatuses = {
    open: 'Recibida',
    in_progress: 'En revisión',
    resolved: 'Resuelta',
    closed: 'Cerrada',
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
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

    if (Object.keys(payload).length === 0) {
      setLoading(false);
      return;
    }

    try {
      await api.updateProfile(payload);
      await loadUser();
      setMessage(t('profile.updated'));
      setFormData(prev => ({ ...prev, password: '' }));
    } catch (error) {
      setMessageIsError(true);
      setMessage(error.response?.data?.detail || t('profile.update_error'));
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExportLoading(true);
    setExportError('');
    try {
      const { data } = await api.exportAccount();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'medievol-datos-cuenta.json';
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Safari needs the object URL to outlive the synthetic download click.
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setExportError(error.response?.data?.detail || 'No se pudieron exportar los datos. Inténtalo de nuevo.');
    } finally {
      setExportLoading(false);
    }
  };

  if (!user) return <div role="status">{t('common.loading')}</div>;

  return (
    <div className="max-w-2xl mx-auto mt-4 sm:mt-10 pb-32 md:pb-20">
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
              <div className="text-xl text-red-400 inline-flex items-center gap-2">
                <GameIcon name="gem" size={20} /> {user.rubies_balance}
              </div>
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
            <div className="block text-gray-400 mb-1">{t('profile.language')}</div>
            <p data-testid="profile-language" className="rounded border border-gray-700 bg-black/30 px-3 py-2 text-gray-200">
              Español
            </p>
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

        <section aria-labelledby="account-data-title" className="mt-8 border-t border-gray-700 pt-6 space-y-3">
          <h2 id="account-data-title" className="text-xl font-semibold text-amber-100">Tus datos</h2>
          <p className="text-sm text-gray-300">
            Descarga una copia en JSON de tu perfil, progreso de juego y comunicaciones de tu cuenta.
            El archivo contiene información personal; guárdalo en un lugar privado.
          </p>
          <button
            type="button"
            data-testid="account-export"
            onClick={handleExport}
            disabled={exportLoading}
            className="btn bg-gray-700 hover:bg-gray-600 text-white border border-amber-900/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
          >
            {exportLoading ? 'Preparando datos...' : 'Descargar mis datos'}
          </button>
          {exportError && <p role="alert" data-testid="account-export-error" className="text-sm text-red-300">{exportError}</p>}
        </section>

        <section aria-labelledby="privacy-requests-title" className="mt-8 border-t border-gray-700 pt-6 space-y-4">
          <h2 id="privacy-requests-title" className="text-xl font-semibold text-amber-100">Solicitudes de privacidad</h2>
          <p className="text-sm text-gray-300">
            Puedes solicitar una revisión sobre tus datos. El envío no elimina ni modifica tu cuenta:
            el equipo de soporte debe revisar cualquier solicitud antes de realizar cambios.
            No incluyas contraseñas, códigos de acceso ni datos de otras personas.
          </p>
          <form onSubmit={handlePrivacySubmit} className="space-y-3">
            <div>
              <label htmlFor="privacy-kind" className="block text-sm text-gray-300 mb-1">Tipo de solicitud</label>
              <select
                id="privacy-kind"
                data-testid="privacy-kind"
                className="input w-full bg-gray-900 text-white"
                value={privacyKind}
                disabled={privacySubmitting}
                onChange={(e) => setPrivacyKind(e.target.value)}
              >
                <option value="erasure">Solicitar eliminación de mi cuenta</option>
                <option value="rectification">Solicitar corrección de mis datos</option>
                <option value="retention">Consultar la retención de mis datos</option>
                <option value="other">Otra consulta de privacidad</option>
              </select>
            </div>
            <div>
              <label htmlFor="privacy-details" className="block text-sm text-gray-300 mb-1">Detalles (opcional)</label>
              <textarea
                id="privacy-details"
                data-testid="privacy-details"
                className="input w-full bg-gray-900 text-white min-h-24"
                maxLength={1000}
                value={privacyDetails}
                disabled={privacySubmitting}
                onChange={(e) => setPrivacyDetails(e.target.value)}
              />
            </div>
            <button type="submit" data-testid="privacy-submit" disabled={privacySubmitting} className="btn bg-gray-700 hover:bg-gray-600 text-white border border-amber-900/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400">
              {privacySubmitting ? 'Enviando...' : 'Enviar solicitud para revisión'}
            </button>
          </form>
          {privacyError && <p role="alert" data-testid="privacy-error" className="text-sm text-red-300">{privacyError}</p>}
          {privacyNotice && <p role="status" data-testid="privacy-success" className="text-sm text-green-300">{privacyNotice}</p>}
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold text-gray-200">Estado de solicitudes</h3>
              <button type="button" onClick={() => { void fetchPrivacyRequests(); }} disabled={privacyLoading || privacySubmitting} className="text-sm underline text-amber-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400">
                Actualizar
              </button>
            </div>
            {privacyLoading ? <p role="status">Consultando solicitudes...</p> : privacyRequests.length === 0 ? (
              <p data-testid="privacy-empty" className="text-sm text-gray-400">No hay solicitudes registradas.</p>
            ) : (
              <ul className="space-y-2">
                {privacyRequests.map((item) => (
                  <li key={item.id} data-testid={`privacy-case-${item.id}`} className="border border-gray-700 rounded p-3 text-sm">
                    <span className="text-amber-200">{privacyLabels[item.kind] || 'Solicitud'}</span>
                    <span className="ml-3 text-gray-200">{privacyStatuses[item.status] || item.status}</span>
                    <span className="block text-xs text-gray-400">Caso #{item.id}</span>
                    {item.resolution && <p className="mt-2 text-gray-300">{item.resolution}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default ProfileView;
