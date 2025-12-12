import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { api } from '../api/axiosClient';

const VerifyEmail = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [status, setStatus] = useState('verifying'); // verifying, success, error

  useEffect(() => {
    if (!token) {
      setStatus('error');
      return;
    }

    api.verifyEmail(token)
      .then(() => setStatus('success'))
      .catch(() => setStatus('error'));
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-black text-gray-100 p-4">
      <div className="max-w-md w-full text-center space-y-6">
        {status === 'verifying' && (
          <>
            <h2 className="text-2xl font-bold text-yellow-500 animate-pulse">Verificando correo...</h2>
            <p className="text-gray-400">Por favor espera un momento.</p>
          </>
        )}
        
        {status === 'success' && (
          <>
            <h2 className="text-3xl font-bold text-green-500">¡Correo Verificado!</h2>
            <p className="text-gray-300">Tu cuenta ha sido activada correctamente.</p>
            <Link to="/login" className="btn-primary inline-block px-8 py-3 mt-4">
              Iniciar Sesión
            </Link>
          </>
        )}

        {status === 'error' && (
          <>
            <h2 className="text-3xl font-bold text-red-500">Error de Verificación</h2>
            <p className="text-gray-300">El enlace es inválido o ha expirado.</p>
            <Link to="/login" className="text-yellow-500 hover:underline mt-4 block">
              Volver al inicio
            </Link>
          </>
        )}
      </div>
    </div>
  );
};

export default VerifyEmail;
