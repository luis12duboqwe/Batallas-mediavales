import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useUserStore } from '../store/userStore';

const Register = () => {
  const [form, setForm] = useState({ username: '', email: '', password: '' });
  const { register, error, loading } = useUserStore();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await register(form);
      navigate('/');
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-midnight via-gray-950 to-black p-6">
      <div className="card w-full max-w-md p-8 space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-2xl">Forja tu reino</h1>
          <p className="text-gray-400">Crea una cuenta para empezar la conquista</p>
        </div>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="block text-sm mb-1">Usuario</label>
            <input
              className="input w-full"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
            />
          </div>
          <div>
            <label className="block text-sm mb-1">Email</label>
            <input
              type="email"
              className="input w-full"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
          </div>
          <div>
            <label className="block text-sm mb-1">Contraseña</label>
            <input
              type="password"
              className="input w-full"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? 'Creando...' : 'Crear cuenta'}
          </button>
        </form>
        <p className="text-sm text-center text-gray-400">
          ¿Ya tienes cuenta? <Link to="/login" className="text-yellow-400">Inicia sesión</Link>
        </p>
      </div>
    </div>
  );
};

export default Register;
